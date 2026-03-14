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
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# Aegis v4 Core Modules
from hardware_monitor import HardwareMonitor
from memory_manager import MemoryManager
from server_engine import ServerEngine
from watchdog_pro import WatchdogPro

# Constants
REMOTE_CONFIG_URL = "https://raw.githubusercontent.com/DeformexExx/farm/refs/heads/main/config.json"
STATE_FILE = "state.json"
LOG_FILE = "aegis.log"
SCREENSHOT_PATH = "/data/local/tmp/s.png"

# Logger Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("AegisV4")

def fetch_remote_config():
    """Strict remote fetch with local fallback."""
    for attempt in range(1, 4):
        try:
            resp = requests.get(REMOTE_CONFIG_URL, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                data["bot_token"] = data.get("bot_token", "").strip()
                data["admin_ids"] = [int(i) for i in data.get("admin_ids", [])]
                return data
        except Exception:
            pass
        time.sleep(5)
    if os.path.exists("config.json"):
        with open("config.json", "r") as f:
            return json.load(f)
    sys.exit(1)

class AegisFarmOSv4:
    def __init__(self, config):
        self.config = config
        self.clones = self.config.get("clones", [])
        self.watchdogs = {pkg: WatchdogPro(pkg, log_func=self.safe_print) for pkg in self.clones}
        self.live_consoles = set() 
        self.state = self.load_state() 
        self.app = None 
        self.loop = None
        self.launch_lock = threading.Lock()
        
        # v4: Ghost Purge
        self.purge_ghosts()

    def purge_ghosts(self):
        """Kills any previous main.py phantom instances."""
        try:
            curr_pid = os.getpid()
            # Command to kill other main.py processes
            cmd = f"su -c \"ps -ef | grep main.py | grep -v grep | grep -v {curr_pid} | awk '{{print $2}}' | xargs kill -9\""
            subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("Ghost processes purged.")
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
        logger.info(text)
        if self.app and self.live_consoles:
            clean_text = f"📟 [AEGIS]: {text}"
            for admin_id in self.live_consoles:
                try:
                    asyncio.run_coroutine_threadsafe(
                        self.app.bot.send_message(chat_id=admin_id, text=clean_text),
                        self.loop
                    )
                except Exception: pass

    def get_grid_menu(self):
        """v4 Grid Menu (4 Rows)."""
        keyboard = [
            [KeyboardButton("\U0001F3AE CLONES CONTROL"), KeyboardButton("\U0001F4F8 SNAPSHOT")],
            [KeyboardButton("\u26A1 MASTER START"), KeyboardButton("\U0001F6D1 STOP ALL")],
            [KeyboardButton("\U0001F9F9 DEEP CLEAN"), KeyboardButton("\U0001F4BB SHELL CONSOLE")],
            [KeyboardButton("\u2699\uFE0F CONFIG"), KeyboardButton("\U0001F504 UPDATE FROM GIT")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_inline_clones(self):
        keyboard = []
        for pkg in self.clones:
            is_enabled = self.state.get(pkg, False)
            toggle_text = "\U0001F534 OFF" if not is_enabled else "\U0001F7E2 ON"
            row = [
                InlineKeyboardButton(f"{toggle_text} {pkg}", callback_data=f"toggle_{pkg}"),
                InlineKeyboardButton("\u25B6\uFE0F Start", callback_data=f"start_{pkg}"),
                InlineKeyboardButton("\u23F9\uFE0F Stop", callback_data=f"stop_{pkg}")
            ]
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("\u21BB Refresh List", callback_data="refresh")])
        return InlineKeyboardMarkup(keyboard)

    async def start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.auth(update.effective_user.id): return
        await update.message.reply_text(
            "\U0001F6E1 *Aegis OS v4: ULTIMATE STABILITY*\nGrid Menu Active. Shell Console Enabled.",
            reply_markup=self.get_grid_menu(),
            parse_mode='Markdown'
        )

    async def set_link_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.auth(update.effective_user.id): return
        if not context.args:
            await update.message.reply_text("Usage: /set_link <url>")
            return
        url = context.args[0]
        if ServerEngine.add_server(url):
            await update.message.reply_text(f"\u2705 Link added to servers.json:\n`{url}`", parse_mode='Markdown')
        else:
            await update.message.reply_text("\u26A0\uFE0F Link already exists or error.")

    async def handle_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.auth(user_id): return
        text = update.message.text

        # v4: Shell Console ($ or shell )
        if text.startswith("$") or text.lower().startswith("shell "):
            cmd = text[1:].strip() if text.startswith("$") else text[6:].strip()
            await self.execute_shell(update, cmd)
            return

        if text == "\U0001F3AE CLONES CONTROL":
            await update.message.reply_text("🎮 *Clone Management:*", reply_markup=self.get_inline_clones(), parse_mode='Markdown')

        elif text == "\u26A1 MASTER START":
            self.safe_print("v4 Master Start: Engaging staggered sequence...")
            for pkg in self.clones: self.state[pkg] = True
            self.save_state()
            threading.Thread(target=self.launch_all_staggered).start()
            await update.message.reply_text("\u26A1 Hard staggered launch initiated (10s intervals).")

        elif text == "\U0001F6D1 STOP ALL":
            self.safe_print("Master Stop dispatched.")
            for pkg in self.clones:
                self.state[pkg] = False
                self.watchdogs[pkg].force_stop()
            self.save_state()
            await update.message.reply_text("\U0001F6D1 All automation and clones stopped.")

        elif text == "\U0001F4F8 SNAPSHOT":
            await self.take_snapshot(update)

        elif text == "\U0001F9F9 DEEP CLEAN":
            MemoryManager.system_deep_clean()
            await update.message.reply_text("\U0001F9F9 System flush and trim dispatched.")

        elif text == "\U0001F4BB SHELL CONSOLE":
            if user_id in self.live_consoles: self.live_consoles.remove(user_id)
            else: self.live_consoles.add(user_id)
            await update.message.reply_text(f"💻 Shell Console Log: {'ENABLED' if user_id in self.live_consoles else 'DISABLED'}")

        elif text == "\u2699\uFE0F CONFIG":
            active_count = sum(1 for v in self.state.values() if v)
            report = HardwareMonitor.get_dashboard_report(active_count)
            await update.message.reply_text(f"```\n{report}\n```", parse_mode='Markdown')

        elif text == "\U0001F504 UPDATE FROM GIT":
            await update.message.reply_text("\U0001F504 Syncing from GitHub... SYSTEM REBOOT.")
            self.update_system()

    async def execute_shell(self, update: Update, cmd):
        """Executes direct su -c command (v4)."""
        self.safe_print(f"Shell Exec: {cmd}")
        try:
            result = subprocess.run(f"su -c '{cmd}'", shell=True, capture_output=True, text=True, timeout=120)
            output = result.stdout or ""
            error = result.stderr or ""
            combined = f"{output}\n{error}".strip()
            if not combined: combined = "[No output]"
            # Truncate if too long
            if len(combined) > 3900: combined = combined[:3900] + "\n...[Truncated]"
            await update.message.reply_text(f"```bash\n{combined}\n```", parse_mode='Markdown')
        except subprocess.TimeoutExpired:
            await update.message.reply_text("\u274C Command timed out (120s).")
        except Exception as e:
            await update.message.reply_text(f"\u274C Shell Error: {e}")

    async def take_snapshot(self, update: Update):
        try:
            self.safe_print("Taking system snapshot...")
            subprocess.run(f"su -c 'screencap -p {SCREENSHOT_PATH}'", shell=True)
            if os.path.exists(SCREENSHOT_PATH):
                with open(SCREENSHOT_PATH, 'rb') as f:
                    await update.message.reply_photo(photo=f, caption="\U0001F4F8 v4 Snapshot")
                os.remove(SCREENSHOT_PATH)
            else:
                await update.message.reply_text("\u274C Snapshot failed.")
        except Exception as e:
            await update.message.reply_text(f"\u274C Snapshot error: {e}")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not self.auth(query.from_user.id): return
        data = query.data

        if data == "refresh":
            await query.edit_message_reply_markup(reply_markup=self.get_inline_clones())
        elif data.startswith("toggle_"):
            pkg = data.replace("toggle_", "")
            self.state[pkg] = not self.state.get(pkg, False)
            self.save_state()
            await query.edit_message_reply_markup(reply_markup=self.get_inline_clones())
        elif data.startswith("start_"):
            pkg = data.replace("start_", "")
            self.state[pkg] = True
            self.save_state()
            threading.Thread(target=self.safe_launch, args=(pkg,)).start()
            await query.answer(f"\u25B6 Starting {pkg}")
        elif data.startswith("stop_"):
            pkg = data.replace("stop_", "")
            self.state[pkg] = False
            self.save_state()
            self.watchdogs[pkg].force_stop()
            await query.answer(f"\u23F9 Stopped {pkg}")
        await query.answer()

    def launch_all_staggered(self):
        """v4 10s staggered launch sequence."""
        with self.launch_lock:
            for pkg in self.clones:
                if self.state.get(pkg):
                    self.safe_launch(pkg)
                    time.sleep(10) # Hard 10s wait (Anti-Reboot)

    def safe_launch(self, pkg):
        """v4 Surgical Launch: drop_caches -> am start -> renice."""
        self.safe_print(f"v4 Launch: {pkg}")
        # Anti-Reboot Optimization
        MemoryManager.v4_pre_launch_optimize()
        
        # Intent Link Fix (Single Quotes)
        link = ServerEngine.get_random_server() or self.config.get("default_link", "")
        cmd = f"su -c 'am start -a android.intent.action.VIEW -d \"{link}\" {pkg}'"
        
        if pkg in self.watchdogs:
            self.watchdogs[pkg].last_launch_time = time.time()
            
        subprocess.Popen(
            cmd, shell=True, 
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=os.setpgrp
        )
        
        # Staggered renice priority
        threading.Thread(target=self.priority_waitlist, args=(pkg,)).start()

    def priority_waitlist(self, pkg):
        """Wait for PID and apply renice -20 (v4)."""
        time.sleep(5)
        for _ in range(10):
            pid = self.watchdogs[pkg].get_pid()
            if pid:
                MemoryManager.set_priority(pid)
                self.safe_print(f"Priority -20 applied to {pkg} (PID {pid})")
                return
            time.sleep(2)

    def maintenance_loop(self):
        """v4 background maintenance (30m trim)."""
        while True:
            time.sleep(1800) # 30 mins
            self.safe_print("Scheduled maintenance: Trimming caches...")
            MemoryManager.periodic_trim()

    def update_system(self):
        try:
            files = ["main.py", "watchdog_pro.py", "memory_manager.py", "hardware_monitor.py", "server_engine.py", "config.json"]
            base_url = self.config.get("github_url", "https://raw.githubusercontent.com/DeformexExx/farm/refs/heads/main")
            for f in files:
                url = f"{base_url}/{f}"
                subprocess.run(f"curl -L {url} -o {f}", shell=True)
            self.safe_print("Update complete. Re-executing...")
            os.execv(sys.executable, ['python'] + sys.argv)
        except Exception as e:
            self.safe_print(f"Update failed: {e}")

    def watchdog_thread(self):
        self.safe_print("v4 Smart Watchdog active (Thread-based 130-rule).")
        time.sleep(60)
        while True:
            for pkg in self.clones:
                if self.state.get(pkg, False):
                    wd = self.watchdogs[pkg]
                    if not wd.is_alive():
                        self.safe_print(f"v4 Recovery triggered for {pkg}")
                        self.safe_launch(pkg)
                        time.sleep(10)
            gc.collect()
            time.sleep(120) # 2 minute cycle for v4 checks

    def run(self):
        async def post_init(application):
            self.app = application
            self.loop = asyncio.get_event_loop()
            
            # Auto-Start logic (v4)
            if self.config.get("global_auto_start", False):
                self.safe_print("GLOBAL AUTO-BOOT. Starting in 30s...")
                threading.Timer(30.0, self.master_start).start()

            for admin_id in self.config["admin_ids"]:
                try: await application.bot.send_message(admin_id, "🚀 Aegis OS v4 Online. Grid Menu Ready.")
                except: pass

        app = ApplicationBuilder().token(self.config["bot_token"]).post_init(post_init).build()
        app.add_handler(CommandHandler("start", self.start_cmd))
        app.add_handler(CommandHandler("set_link", self.set_link_cmd))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_messages))
        app.add_handler(CallbackQueryHandler(self.handle_callback))

        MemoryManager.set_oom_priority()
        MemoryManager.setup_swap()

        # Threads
        threading.Thread(target=self.watchdog_thread, daemon=True).start()
        threading.Thread(target=self.maintenance_loop, daemon=True).start()
        
        logger.info("Aegis v4 starting polling.")
        app.run_polling()

if __name__ == "__main__":
    cfg = fetch_remote_config()
    time.sleep(5)
    AegisFarmOSv4(cfg).run()
