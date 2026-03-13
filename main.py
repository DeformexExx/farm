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

# Import Aegis v3.1 Modules
from hardware_monitor import HardwareMonitor
from memory_manager import MemoryManager
from server_engine import ServerEngine
from watchdog_pro import WatchdogPro

# Constants
REMOTE_CONFIG_URL = "https://raw.githubusercontent.com/DeformexExx/farm/refs/heads/main/config.json"
STATE_FILE = "state.json"
BOOT_TRACKER = "last_boot.txt"
SCREENSHOT_PATH = "/data/local/tmp/screen.png"

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
    if os.path.exists("config.json"):
        with open("config.json", "r") as f:
            return json.load(f)
    sys.exit(1)

class AegisFarmOSv3:
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
        
        # Ghost Process Cleanup (Anti-Phantom)
        self.kill_ghost_processes()

    def kill_ghost_processes(self):
        """Kills any previous main.py or phantom script instances."""
        try:
            print("Cleaning up ghost processes...")
            # Kill all instances of main.py except ourselves
            current_pid = os.getpid()
            cmd = f"su -c \"ps -ef | grep main.py | grep -v grep | grep -v {current_pid} | awk '{{print $2}}' | xargs kill -9\""
            subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def auth(self, user_id):
        return user_id in self.config.get("admin_ids", [])

    def load_state(self):
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
            [KeyboardButton("\U0001F4F8 SNAPSHOT"), KeyboardButton("\U0001F504 UPDATE")],
            [KeyboardButton("\U00002699\U0000FE0F CONFIG")]
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
            "\U0001F6E1 Aegis FarmOS v3.1 Ready\nAutomated and granular control enabled.",
            reply_markup=self.get_main_keyboard()
        )

    async def handle_buttons(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.auth(user_id): return
        text = update.message.text
        
        if text == "\U0001F680 START ALL":
            self.master_start()
            await update.message.reply_text("\U0001F680 Staggered master launch initiated.")
            
        elif text == "\U0001F6D1 STOP ALL":
            self.safe_print("Master Stop dispatched.")
            for pkg in self.clones:
                self.state[pkg] = False
                self.watchdogs[pkg].force_stop()
            self.save_state()
            await update.message.reply_text("\U0001F6D1 All automation stopped. All clones killed.")
            
        elif text == "\U0001F3AE CLONES":
            await update.message.reply_text("🎮 *Clone Management:*", reply_markup=self.get_clones_keyboard(), parse_mode='Markdown')

        elif text == "\U0001F4CA STATUS":
            active_count = sum(1 for v in self.state.values() if v)
            dashboard = HardwareMonitor.get_dashboard_report(active_count)
            await update.message.reply_text(f"```\n{dashboard}\n```", parse_mode='Markdown')

        elif text == "\U0001F4F8 SNAPSHOT":
            # Re-enabled Snapshot (v3.1)
            try:
                self.safe_print("Taking system snapshot...")
                subprocess.run(f"su -c 'screencap -p {SCREENSHOT_PATH}'", shell=True)
                if os.path.exists(SCREENSHOT_PATH):
                    with open(SCREENSHOT_PATH, 'rb') as f:
                        await update.message.reply_photo(photo=f, caption="\U0001F4F8 System Snapshot")
                    os.remove(SCREENSHOT_PATH)
                else:
                    await update.message.reply_text("\u274C Snapshot failed: File not found.")
            except Exception as e:
                await update.message.reply_text(f"\u274C Snapshot error: {e}")

        elif text == "\U0001F504 UPDATE":
            self.safe_print("GitHub Sync requested...")
            await update.message.reply_text("🔄 Syncing from GitHub... BOT WILL RESTART.")
            self.update_system()

        elif text == "\U0001F9F9 DEEP CLEAN":
            MemoryManager.system_deep_clean()
            await update.message.reply_text("\U0001F9F9 System flush dispatched.")

        elif text == "\U0001F4DF CONSOLE":
            if user_id in self.live_consoles: self.live_consoles.remove(user_id)
            else: self.live_consoles.add(user_id)
            await update.message.reply_text(f"📟 Console: {'ENABLED' if user_id in self.live_consoles else 'DISABLED'}")

        elif text == "\U00002699\U0000FE0F CONFIG":
            await update.message.reply_text(f"CONFIG (v3.1):\nAuto-Start: {self.config.get('global_auto_start', False)}")

        gc.collect()

    def master_start(self):
        self.safe_print("Master Start: Engaging sequences...")
        for pkg in self.clones:
            self.state[pkg] = True
        self.save_state()
        threading.Thread(target=self.launch_all_staggered).start()

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
            await query.answer(f"▶️ Starting {pkg}")
        elif data.startswith("stop_"):
            pkg = data.replace("stop_", "")
            self.state[pkg] = False
            self.save_state()
            self.watchdogs[pkg].force_stop()
            await query.answer(f"🛑 Stopped {pkg}")
        await query.answer()

    def launch_all_staggered(self):
        with self.launch_lock:
            for pkg in self.clones:
                if self.state.get(pkg):
                    self.safe_launch(pkg)
                    time.sleep(5)

    def safe_launch(self, pkg):
        """v3.1 Direct Launch + KSM + RAM Flush."""
        self.safe_print(f"Direct launch: {pkg}")
        # Kernel Optimization & Sync
        MemoryManager.optimize_for_launch()
        # Pre-flight Clean
        MemoryManager.deep_clean_clone(pkg)
        
        # Link Injection (Quoted)
        link = ServerEngine.get_random_server() or self.config.get("default_link", "")
        cmd = f"su -c 'am start -a android.intent.action.VIEW -d \"{link}\" {pkg}'"
        
        # 15s Grace Period
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
            self.safe_print("Restarting bot...")
            os.execv(sys.executable, ['python'] + sys.argv)
        except Exception as e:
            self.safe_print(f"Update error: {e}")

    def watchdog_thread(self):
        self.safe_print("v3.1 Watchdog active.")
        time.sleep(15)
        while True:
            for pkg in self.clones:
                if self.state.get(pkg, False):
                    wd = self.watchdogs[pkg]
                    if not wd.is_alive():
                        self.safe_print(f"Auto-recovery: {pkg}")
                        self.safe_launch(pkg)
                        time.sleep(10)
            gc.collect()
            time.sleep(60)

    def run(self):
        async def post_init(application):
            self.app = application
            self.loop = asyncio.get_event_loop()
            
            # Global Auto-Start (v3.1)
            if self.config.get("global_auto_start", False):
                self.safe_print("AUTO-START detected. Delaying 30s...")
                threading.Timer(30.0, self.master_start).start()

            for admin_id in self.config["admin_ids"]:
                try: await application.bot.send_message(admin_id, "Aegis v3.1 System Online.")
                except: pass

        app = ApplicationBuilder().token(self.config["bot_token"]).post_init(post_init).build()
        app.add_handler(CommandHandler("start", self.start_cmd))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_buttons))
        app.add_handler(CallbackQueryHandler(self.handle_callback))

        MemoryManager.set_oom_priority()
        MemoryManager.setup_swap()

        threading.Thread(target=self.watchdog_thread, daemon=True).start()
        app.run_polling()

if __name__ == "__main__":
    cfg = fetch_remote_config()
    time.sleep(5)
    AegisFarmOSv3(cfg).run()
