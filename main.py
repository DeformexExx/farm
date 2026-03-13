# -*- coding: utf-8 -*-
import os
import time
import asyncio
import threading
import subprocess
import sys
import json
import requests
import gc
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# Import Aegis v2.3 Modules
from hardware_monitor import HardwareMonitor
from memory_manager import MemoryManager
from server_engine import ServerEngine
from watchdog_pro import WatchdogPro

# Constants
REMOTE_CONFIG_URL = "https://raw.githubusercontent.com/DeformexExx/farm/refs/heads/main/config.json"
STATE_FILE = "state.json"
BOOT_TRACKER = "last_boot.txt"

def fetch_remote_config():
    """Strict remote fetch with retries."""
    for attempt in range(1, 6):
        try:
            print(f"Fetch config (Attempt {attempt}/5)...")
            resp = requests.get(REMOTE_CONFIG_URL, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                data["bot_token"] = data.get("bot_token", "").strip()
                data["admin_ids"] = [int(i) for i in data.get("admin_ids", [])]
                return data
        except Exception:
            pass
        if attempt < 5:
            time.sleep(10)
    # Final fallback to local
    if os.path.exists("config.json"):
        with open("config.json", "r") as f:
            return json.load(f)
    sys.exit(1)

class AegisFarmOSv2:
    def __init__(self, config):
        self.config = config
        self.clones = self.config.get("clones", [])
        self.watchdogs = {pkg: WatchdogPro(pkg, log_func=self.safe_print) for pkg in self.clones}
        self.last_msg_time = 0
        self.live_consoles = set() 
        self.state = self.load_state() 
        self.app = None 
        self.loop = None
        self.launch_lock = threading.Lock()

    def auth(self, user_id):
        return user_id in self.config.get("admin_ids", [])

    def load_state(self):
        """Load enabled/disabled state."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    return json.load(f)
            except: pass
        return {pkg: False for pkg in self.clones}

    def save_state(self):
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f)

    def safe_print(self, text):
        print(text)
        if self.app and self.live_consoles:
            clean_text = f"📟 [CONSOLE]: {text}"
            for admin_id in self.live_consoles:
                try:
                    asyncio.run_coroutine_threadsafe(
                        self.app.bot.send_message(chat_id=admin_id, text=clean_text),
                        self.loop
                    )
                except Exception: pass

    def get_main_keyboard(self):
        keyboard = [
            [KeyboardButton("\U0001F680 START ALL"), KeyboardButton("\U0001F6D1 STOP ALL")],
            [KeyboardButton("\U0001F3AE CLONES"), KeyboardButton("\U0001F4CA STATUS")],
            [KeyboardButton("\U0001F9F9 DEEP CLEAN"), KeyboardButton("\U0001F4DF CONSOLE")],
            [KeyboardButton("\U0001F504 UPDATE GITHUB"), KeyboardButton("\U00002699\U0000FE0F CONFIG")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_clones_keyboard(self):
        keyboard = []
        for pkg in self.clones:
            is_enabled = self.state.get(pkg, False)
            toggle_text = "\U0001F534 OFF" if not is_enabled else "\U0001F7E2 ON"
            row = [
                InlineKeyboardButton(f"{toggle_text} {pkg}", callback_data=f"toggle_{pkg}"),
                InlineKeyboardButton("\U000025B6\U0000FE0F Start", callback_data=f"start_{pkg}"),
                InlineKeyboardButton("\U000023F9\uFE0F Stop", callback_data=f"stop_{pkg}")
            ]
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("\U000021BB Refresh", callback_data="refresh")])
        return InlineKeyboardMarkup(keyboard)

    async def start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.auth(update.effective_user.id): return
        await update.message.reply_text(
            "\U0001F6E1 Aegis FarmOS v2.3 Active (Repair Mode)\nDirect launch logic restored.",
            reply_markup=self.get_main_keyboard()
        )

    async def handle_buttons(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.auth(user_id): return
        text = update.message.text
        
        if text == "\U0001F680 START ALL":
            self.safe_print("Master Start: Launching farm...")
            for pkg in self.clones:
                self.state[pkg] = True
            self.save_state()
            threading.Thread(target=self.launch_all_staggered).start()
            await update.message.reply_text("\U0001F680 Staggered launch initiated.")
            
        elif text == "\U0001F6D1 STOP ALL":
            self.safe_print("Master Stop: Killing all.")
            for pkg in self.clones:
                self.state[pkg] = False
                self.watchdogs[pkg].force_stop()
            self.save_state()
            await update.message.reply_text("\U0001F6D1 All clones killed and disabled.")
            
        elif text == "\U0001F3AE CLONES":
            await update.message.reply_text("🎮 *Clone Management:*", reply_markup=self.get_clones_keyboard(), parse_mode='Markdown')

        elif text == "\U0001F504 UPDATE GITHUB":
            self.safe_print("Updating code from GitHub...")
            await update.message.reply_text("🔄 Syncing... System will restart.")
            self.update_system()

        elif text == "\U0001F4CA STATUS":
            active_count = sum(1 for v in self.state.values() if v)
            dashboard = HardwareMonitor.get_dashboard_report(active_count)
            await update.message.reply_text(f"```\n{dashboard}\n```", parse_mode='Markdown')
            
        elif text == "\U0001F9F9 DEEP CLEAN":
            MemoryManager.system_deep_clean()
            await update.message.reply_text("\U0001F9F9 System flush dispatched.")

        elif text == "\U0001F4DF CONSOLE":
            if user_id in self.live_consoles: self.live_consoles.remove(user_id)
            else: self.live_consoles.add(user_id)
            await update.message.reply_text(f"📟 Console: {'ENABLED' if user_id in self.live_consoles else 'DISABLED'}")

        elif text == "\U00002699\U0000FE0F CONFIG":
            await update.message.reply_text(f"CONFIG (v2.3):\nClones: {len(self.clones)}")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not self.auth(query.from_user.id): return
        data = query.data

        if data == "refresh":
            await query.edit_message_reply_markup(reply_markup=self.get_clones_keyboard())
        elif data.startswith("toggle_"):
            pkg = data.replace("toggle_", "")
            self.state[pkg] = not self.state.get(pkg, False)
            self.save_state()
            await query.edit_message_reply_markup(reply_markup=self.get_clones_keyboard())
        elif data.startswith("start_"):
            pkg = data.replace("start_", "")
            self.state[pkg] = True
            self.save_state()
            threading.Thread(target=self.safe_launch, args=(pkg,)).start()
            await query.answer(f"▶️ Starting {pkg}...")
        elif data.startswith("stop_"):
            pkg = data.replace("stop_", "")
            self.state[pkg] = False
            self.save_state()
            self.watchdogs[pkg].force_stop()
            await query.answer(f"🛑 Stopped {pkg}.")
        await query.answer()

    def launch_all_staggered(self):
        with self.launch_lock:
            for pkg in self.clones:
                if self.state.get(pkg):
                    self.safe_launch(pkg)
                    time.sleep(5)

    def safe_launch(self, pkg):
        """v2.3 Clean + Direct Launch."""
        self.safe_print(f"Direct Launch: {pkg}")
        # Fast Clean
        subprocess.run(f"su -c 'pm trim-caches 999G'", shell=True)
        
        # Link Injection Fix
        link = ServerEngine.get_random_server() or self.config.get("default_link", "")
        # Command with properly quoted link and pkg
        cmd = f"su -c 'am start -a android.intent.action.VIEW -d \"{link}\" {pkg}'"
        
        # Trigger 15s Grace Period
        if pkg in self.watchdogs:
            self.watchdogs[pkg].last_launch_time = time.time()
            
        subprocess.Popen(
            cmd, shell=True, 
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=os.setpgrp
        )

    def update_system(self):
        try:
            files = ["main.py", "watchdog_pro.py", "memory_manager.py", "hardware_monitor.py", "server_engine.py", "config.json"]
            base_url = self.config.get("github_url", "https://raw.githubusercontent.com/DeformexExx/farm/refs/heads/main")
            for f in files:
                url = f"{base_url}/{f}"
                subprocess.run(f"curl -L {url} -o {f}", shell=True)
            os.execv(sys.executable, ['python'] + sys.argv)
        except Exception as e:
            self.safe_print(f"Update failed: {e}")

    def watchdog_thread(self):
        self.safe_print("v2.3 Watchdog active (15s grace period enabled).")
        time.sleep(10)
        while True:
            for pkg in self.clones:
                if self.state.get(pkg, False):
                    wd = self.watchdogs[pkg]
                    if not wd.is_alive():
                        self.safe_print(f"v2.3 Recovery: {pkg}")
                        self.safe_launch(pkg)
                        time.sleep(10)
            gc.collect()
            time.sleep(60)

    def run(self):
        async def post_init(application):
            self.app = application
            self.loop = asyncio.get_event_loop()
            for admin_id in self.config["admin_ids"]:
                try: await application.bot.send_message(admin_id, "Aegis v2.3 Online. System Repaired.")
                except: pass

        app = ApplicationBuilder().token(self.config["bot_token"]).post_init(post_init).build()
        app.add_handler(CommandHandler("start", self.start_cmd))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_buttons))
        app.add_handler(CallbackQueryHandler(self.handle_callback))

        MemoryManager.set_oom_priority()
        threading.Thread(target=self.watchdog_thread, daemon=True).start()
        app.run_polling()

if __name__ == "__main__":
    cfg = fetch_remote_config()
    time.sleep(5)
    AegisFarmOSv2(cfg).run()
