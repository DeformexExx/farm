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
import logging
import psutil
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# Aegis v6 Core Modules
from hardware_monitor import HardwareMonitor
from memory_manager import MemoryManager
from server_engine import ServerEngine
from watchdog_pro import WatchdogPro
from sheet_manager import SheetManager
from cookie_injector import CookieInjector

# Constants
STATE_FILE = "state.json"
LOG_FILE = "aegis.log"
SCREENSHOT_PATH = "/data/local/tmp/s.png"
CREDS_FILE = "creds.json"
SHEET_NAME = "AegisFarmOS"

# Identifier (CLI Mode)
DEVICE_ID = sys.argv[1] if len(sys.argv) > 1 else "MASTER"

# Logging pipeline
logging.basicConfig(
    level=logging.INFO,
    format=f'%(asctime)s [{DEVICE_ID}] [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger("AegisV6")

class AegisV6Orchestrator:
    def __init__(self):
        self.device_id = DEVICE_ID
        self.config = self.load_local_config()
        self.sheet = SheetManager(CREDS_FILE, SHEET_NAME)
        self.injector = CookieInjector(self.safe_print)
        self.clones_data = {} # pkg -> data from sheet
        self.watchdogs = {}
        self.app = None
        self.loop = None
        
        # Persistence for Cookies (to detect changes)
        self.cookie_cache = {} # pkg -> last_cookie_value
        
        self.purge_ghosts()

    def load_local_config(self):
        if os.path.exists("config.json"):
            with open("config.json", "r") as f:
                return json.load(f)
        return {"bot_token": "", "admin_ids": []}

    def purge_ghosts(self):
        try:
            curr_pid = os.getpid()
            cmd = f"su -c \"ps -ef | grep main.py | grep -v grep | grep -v {curr_pid} | awk '{{print $2}}' | xargs kill -9\""
            subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"Identity: {self.device_id} | v6 Ghosts purged.")
        except: pass

    def safe_print(self, text):
        prefixed = f"[{self.device_id}] {text}"
        logger.info(text)
        if self.app:
            asyncio.run_coroutine_threadsafe(self.broadcast(prefixed), self.loop)

    async def broadcast(self, text):
        for admin_id in self.config.get("admin_ids", []):
            try: await self.app.bot.send_message(chat_id=admin_id, text=text)
            except: pass

    def get_main_keyboard(self):
        keyboard = [
            [KeyboardButton("📊 REFRESH SHEET"), KeyboardButton("📸 SCREENSHOT")],
            [KeyboardButton("🚀 MASTER RE-INJECT"), KeyboardButton("🛑 STOP FLEET")],
            [KeyboardButton("🧹 SYSTEM CLEAN"), KeyboardButton("💻 SHELL CONSOLE")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    async def start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in self.config.get("admin_ids", []): return
        await update.message.reply_text(
            f"🛡️ *Aegis OS v6: Injection Edition*\nDevice: `{self.device_id}`\nSource of Truth: Google Sheets",
            reply_markup=self.get_main_keyboard(),
            parse_mode='Markdown'
        )

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in self.config.get("admin_ids", []): return
        text = update.message.text

        if text == "📊 REFRESH SHEET":
            await update.message.reply_text(f"[{self.device_id}] Syncing rows with Sheet...")
            threading.Thread(target=self.sync_loop_tick).start()
            
        elif text == "🚀 MASTER RE-INJECT":
            self.safe_print("Forcing fleet re-injection...")
            threading.Thread(target=self.master_relaunch, args=(True,)).start()

        elif text == "🛑 STOP FLEET":
            self.safe_print("Stopping all local clones.")
            for pkg in self.watchdogs:
                self.watchdogs[pkg].force_stop()
            await update.message.reply_text(f"[{self.device_id}] All clones stopped.")

        elif text == "📸 SCREENSHOT":
            await self.take_snap(update.message)

        elif text == "🧹 SYSTEM CLEAN":
            MemoryManager.system_deep_clean()
            await update.message.reply_text(f"[{self.device_id}] Deep clean dispatched.")

        elif text.startswith("$") or text.lower().startswith("shell "):
            cmd = text[1:].strip() if text.startswith("$") else text[6:].strip()
            # Basic context check: if cmd starts with ID or "FLEET"
            if cmd.startswith(self.device_id) or cmd.startswith("FLEET"):
                real_cmd = cmd.replace(self.device_id, "").replace("FLEET", "").strip()
                await self.execute_shell(update, real_cmd)

    async def execute_shell(self, update: Update, cmd):
        try:
            res = subprocess.run(f"su -c '{cmd}'", shell=True, capture_output=True, text=True, timeout=30)
            out = (res.stdout + res.stderr).strip() or "[No output]"
            await update.message.reply_text(f"```bash\n[{self.device_id}]\n{out[:3500]}\n```", parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"[{self.device_id}] Shell Err: {e}")

    async def take_snap(self, message):
        try:
            subprocess.run(f"su -c 'screencap -p {SCREENSHOT_PATH}'", shell=True)
            if os.path.exists(SCREENSHOT_PATH):
                with open(SCREENSHOT_PATH, 'rb') as f:
                    await message.reply_photo(photo=f, caption=f"📸 Snapshot: {self.device_id}")
                os.remove(SCREENSHOT_PATH)
        except: pass

    def sync_loop_tick(self):
        """Single tick of the sheet sync loop."""
        if not self.sheet.connect(): return
        
        clones = self.sheet.get_my_clones(self.device_id)
        for c in clones:
            pkg = f"com.roblox.{c['instance']}"
            self.clones_data[pkg] = c
            
            # Watchdog initialization
            if pkg not in self.watchdogs:
                self.watchdogs[pkg] = WatchdogPro(pkg, self.safe_print)

            # Cookie Change Detection
            new_cookie = c['cookie']
            if self.cookie_cache.get(pkg) != new_cookie:
                self.safe_print(f"Cookie change detected for {c['instance']}. Injecting...")
                self.cookie_cache[pkg] = new_cookie
                threading.Thread(target=self.smart_launch, args=(pkg,)).start()
        
        # Cleanup watchdogs for clones removed from sheet
        current_pkgs = [f"com.roblox.{c['instance']}" for c in clones]
        removed = set(self.watchdogs.keys()) - set(current_pkgs)
        for r_pkg in removed:
            self.watchdogs[r_pkg].force_stop()
            del self.watchdogs[r_pkg]
            del self.clones_data[r_pkg]

    def smart_launch(self, pkg):
        """v6 Smart Launch: Validate -> Status: Starting -> Inject -> Start -> Status: Online."""
        data = self.clones_data.get(pkg)
        if not data: return

        # 1. API Validation
        if not self.injector.validate_cookie(data['cookie']):
            self.safe_print(f"❌ INVALID COOKIE for {data['name']}. Notifying owner.")
            self.sheet.update_status(data['row'], "❌ Invalid")
            return

        # 2. Status: Starting
        self.sheet.update_status(data['row'], "⏳ Starting")

        # 3. Inject
        if self.injector.inject(data['instance'], data['cookie']):
            # 4. Launch (Staggered)
            self.safe_launch_command(pkg)
            # 5. Status: Online
            time.sleep(10) # Wait for start to settle
            self.sheet.update_status(data['row'], "✅ Online")
        else:
            self.safe_print(f"Injection failed for {pkg}")
            self.sheet.update_status(data['row'], "⚠️ Inject Error")

    def safe_launch_command(self, pkg):
        """Executes the am start command."""
        self.safe_print(f"Starting {pkg}...")
        MemoryManager.v4_pre_launch_optimize()
        link = ServerEngine.get_random_server() or self.config.get("default_link", "")
        cmd = f"su -c 'am start -a android.intent.action.VIEW -d \"{link}\" {pkg}'"
        
        self.watchdogs[pkg].last_launch_time = time.time()
        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setpgrp)
        
        # Priority renice
        threading.Thread(target=self.renice_task, args=(pkg,)).start()

    def renice_task(self, pkg):
        time.sleep(10)
        pid = self.watchdogs[pkg].get_pid()
        if pid:
            subprocess.run(f"su -c 'renice -n -20 -p {pid}'", shell=True)

    def watchdog_loop(self):
        self.safe_print("Watchdog & Sync Loop active (3-5 min cycles).")
        while True:
            # Sync with Sheet
            self.sync_loop_tick()
            
            # Local Health Check
            for pkg, wd in self.watchdogs.items():
                if not wd.check_health():
                    self.safe_print(f"Recovery Triggered for {pkg}")
                    threading.Thread(target=self.smart_launch, args=(pkg,)).start()
            
            gc.collect()
            time.sleep(240) # 4 minutes cycle

    def master_relaunch(self, force=False):
        for pkg in self.watchdogs:
            threading.Thread(target=self.smart_launch, args=(pkg,)).start()
            time.sleep(15)

    def run(self):
        async def post_init(application):
            self.app = application
            self.loop = asyncio.get_event_loop()
            await self.broadcast(f"🚢 Aegis v6 Injection Online: {self.device_id}")

        app = ApplicationBuilder().token(self.config["bot_token"]).post_init(post_init).build()
        app.add_handler(CommandHandler("start", self.start_cmd))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_text))
        
        MemoryManager.setup_swap()
        threading.Thread(target=self.watchdog_loop, daemon=True).start()
        app.run_polling()

if __name__ == "__main__":
    time.sleep(5)
    AegisV6Orchestrator().run()
