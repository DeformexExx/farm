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

# Import Aegis v2 Modules
from hardware_monitor import HardwareMonitor
from memory_manager import MemoryManager
from server_engine import ServerEngine
from watchdog_pro import WatchdogPro

# Constants
REMOTE_CONFIG_URL = "https://raw.githubusercontent.com/DeformexExx/farm/refs/heads/main/config.json"
BOOT_TRACKER = "last_boot.txt"
ACTIVE_CLONES_FILE = "active_clones.json"

def fetch_remote_config():
    """Strict remote fetch with retries."""
    for attempt in range(1, 6):
        try:
            print(f"Fetch config (Attempt {attempt}/5)...")
            resp = requests.get(REMOTE_CONFIG_URL, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("bot_token", "").strip()
                admins = [int(i) for i in data.get("admin_ids", [])]
                if not token or token == "your_bot_token_here":
                    sys.exit(1)
                data["bot_token"] = token
                data["admin_ids"] = admins
                data["clones"] = data.get("clones", [])
                return data
        except Exception:
            pass
        if attempt < 5:
            time.sleep(10)
    sys.exit(1)

class AegisFarmOSv2:
    def __init__(self, config):
        self.config = config
        self.clones = self.config.get("clones", [])
        self.watchdogs = {pkg: WatchdogPro(pkg, log_func=self.safe_print) for pkg in self.clones}
        self.is_farming = False 
        self.last_msg_time = 0
        self.live_consoles = set() 
        self.active_clones = self.load_active_clones() # Persistent state
        self.app = None 
        self.loop = None

    def auth(self, user_id):
        return user_id in self.config.get("admin_ids", [])

    def load_active_clones(self):
        """Load enabled clones from JSON."""
        if os.path.exists(ACTIVE_CLONES_FILE):
            try:
                with open(ACTIVE_CLONES_FILE, "r") as f:
                    data = json.load(f)
                    # Filter to ensure only valid clones from config are loaded
                    return set(pkg for pkg in data if pkg in self.clones)
            except:
                pass
        return set()

    def save_active_clones(self):
        """Save enabled clones to JSON."""
        with open(ACTIVE_CLONES_FILE, "w") as f:
            json.dump(list(self.active_clones), f)

    def safe_print(self, text):
        """Prints to terminal and broadcasts to active Telegram consoles."""
        print(text)
        if self.app and self.live_consoles:
            clean_text = f"📟 [CONSOLE]: {text}"
            for admin_id in self.live_consoles:
                try:
                    asyncio.run_coroutine_threadsafe(
                        self.app.bot.send_message(chat_id=admin_id, text=clean_text),
                        self.loop
                    )
                except Exception:
                    pass

    def get_main_keyboard(self):
        """Aegis v2.2 Reply Keyboard."""
        keyboard = [
            [KeyboardButton("\U0001F680 START ALL"), KeyboardButton("\U0001F6D1 STOP ALL")],
            [KeyboardButton("\U0001F3AE CLONES"), KeyboardButton("\U0001F4CA STATUS")],
            [KeyboardButton("\U0001F9F9 DEEP CLEAN"), KeyboardButton("\U0001F4DF CONSOLE")],
            [KeyboardButton("\U0001F4F8 SNAPSHOT"), KeyboardButton("\U00002699\U0000FE0F CONFIG")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_clones_keyboard(self):
        """Inline Keyboard for granular control."""
        keyboard = []
        for pkg in self.clones:
            status = "\U00002705" if pkg in self.active_clones else "\U0000274C"
            row = [
                InlineKeyboardButton(f"{status} {pkg}", callback_data="none"),
                InlineKeyboardButton("\U000025B6\U0000FE0F Start", callback_data=f"start_{pkg}"),
                InlineKeyboardButton("\U000023F9\uFE0F Stop", callback_data=f"stop_{pkg}")
            ]
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("\U000021BB Refresh", callback_data="refresh_clones")])
        return InlineKeyboardMarkup(keyboard)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.auth(update.effective_user.id): return
        await update.message.reply_text(
            "\U0001F6E1 Aegis FarmOS v2.2 Active\nGranular control enabled.",
            reply_markup=self.get_main_keyboard()
        )

    async def handle_buttons(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.auth(user_id): return
        
        text = update.message.text
        now = time.time()
        if now - self.last_msg_time < 0.5:
            return
        self.last_msg_time = now

        if text == "\U0001F680 START ALL":
            self.is_farming = True
            self.active_clones = set(self.clones)
            self.save_active_clones()
            self.safe_print("Master Start: All clones engaged.")
            for pkg in self.clones:
                self.safe_launch(pkg)
                await asyncio.sleep(0.5)
            await update.message.reply_text("\U0001F680 Master automation started. All clones engaged.")
            
        elif text == "\U0001F6D1 STOP ALL":
            self.is_farming = False
            self.active_clones = set()
            self.save_active_clones()
            self.safe_print("Master Stop: All clones terminated.")
            for pkg in self.clones:
                self.watchdogs[pkg].force_stop()
            await update.message.reply_text("\U0001F6D1 All automation stopped. Clones terminated.")
            
        elif text == "\U0001F3AE CLONES":
            await update.message.reply_text(
                "🎮 *Clone Management:*\nSelect a clone to override:",
                reply_markup=self.get_clones_keyboard(),
                parse_mode='Markdown'
            )

        elif text == "\U0001F4CA STATUS":
            dashboard = HardwareMonitor.get_dashboard_report(len(self.active_clones))
            await update.message.reply_text(f"```\n{dashboard}\n```", parse_mode='Markdown')
            
        elif text == "\U0001F9F9 DEEP CLEAN":
            self.safe_print("Manual deep clean dispatched.")
            MemoryManager.system_deep_clean()
            await update.message.reply_text("\U0001F9F9 Deep clean dispatched.")
            
        elif text == "\U0001F4F8 SNAPSHOT":
            path = "/sdcard/aegis_overview.png"
            subprocess.run(f"su -c 'screencap -p {path}'", shell=True)
            with open(path, 'rb') as f:
                await update.message.reply_photo(photo=f, caption="System Snapshot")

        elif text == "\U0001F4DF CONSOLE":
            if user_id in self.live_consoles:
                self.live_consoles.remove(user_id)
                await update.message.reply_text("📟 Console stream: DISABLED")
            else:
                self.live_consoles.add(user_id)
                await update.message.reply_text("📟 Console stream: ENABLED")

        elif text == "\U00002699\U0000FE0F CONFIG":
            clones_list = ", ".join(self.clones)
            await update.message.reply_text(f"CONFIG:\nClones: {clones_list}\nEnabled: {', '.join(self.active_clones) or 'None'}")

        gc.collect()

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Inline button callbacks for granular control."""
        query = update.callback_query
        user_id = query.from_user.id
        if not self.auth(user_id):
            await query.answer("Auth required.", show_alert=True)
            return

        data = query.data
        if data == "none":
            await query.answer()
            return
        
        if data == "refresh_clones":
            await query.edit_message_reply_markup(reply_markup=self.get_clones_keyboard())
            await query.answer("Refresh complete.")
            return

        if data.startswith("start_"):
            pkg = data.replace("start_", "")
            self.active_clones.add(pkg)
            self.save_active_clones()
            self.is_farming = True # Ensure watchdog is running if something is started
            self.safe_launch(pkg)
            await query.answer(f"▶️ Starting {pkg}...")
            await query.edit_message_reply_markup(reply_markup=self.get_clones_keyboard())
            
        elif data.startswith("stop_"):
            pkg = data.replace("stop_", "")
            self.active_clones.discard(pkg)
            self.save_active_clones()
            self.watchdogs[pkg].force_stop()
            await query.answer(f"🛑 Stopping {pkg}...")
            await query.edit_message_reply_markup(reply_markup=self.get_clones_keyboard())

    def safe_launch(self, pkg):
        self.safe_print(f"v2 granular launch: {pkg}")
        MemoryManager.deep_clean_clone(pkg)
        cmd = f"su -c 'monkey -p {pkg} -c android.intent.category.LAUNCHER 1'"
        subprocess.Popen(
            cmd, shell=True, 
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=os.setpgrp
        )

    def watchdog_thread(self, loop):
        print("Watchdog v2.2 active.")
        time.sleep(10)
        
        while True:
            # Watchdog only runs if Farming is enabled AND there are active clones
            if self.is_farming and self.active_clones:
                # Use list to avoid 'set changed size during iteration' errors
                for pkg in list(self.active_clones):
                    if pkg in self.clones:
                        wd = self.watchdogs[pkg]
                        if not wd.is_alive():
                            self.safe_launch(pkg)
                            time.sleep(30)
            
            gc.collect()
            time.sleep(60)

    def run(self):
        async def post_init(application):
            self.app = application
            self.loop = asyncio.get_event_loop()
            
            now = time.time()
            if os.path.exists(BOOT_TRACKER):
                try:
                    with open(BOOT_TRACKER, "r") as f:
                        if now - float(f.read().strip()) < 120: return
                except: pass
            with open(BOOT_TRACKER, "w") as f: f.write(str(now))
            
            for admin_id in self.config["admin_ids"]:
                try: 
                    await application.bot.send_message(admin_id, "Aegis v2.2 Online. Granular control ready.")
                except: pass

        app = ApplicationBuilder().token(self.config["bot_token"]).post_init(post_init).build()
        
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_buttons))
        app.add_handler(CallbackQueryHandler(self.handle_callback))

        MemoryManager.set_oom_priority()
        MemoryManager.setup_swap()

        threading.Thread(target=self.watchdog_thread, args=(asyncio.get_event_loop(),), daemon=True).start()
        
        print("v2.2 Polling Active.")
        app.run_polling()

if __name__ == "__main__":
    cfg = fetch_remote_config()
    time.sleep(5)
    AegisFarmOSv2(cfg).run()
