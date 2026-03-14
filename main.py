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
import re
import psutil
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# Aegis v5 Core Modules
from hardware_monitor import HardwareMonitor
from memory_manager import MemoryManager
from server_engine import ServerEngine
from watchdog_pro import WatchdogPro

# Constants
REMOTE_CONFIG_URL = "https://raw.githubusercontent.com/DeformexExx/farm/refs/heads/main/config.json"
STATE_FILE = "state.json"
LOG_FILE = "aegis.log"
SCREENSHOT_PATH = "/data/local/tmp/s.png"

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger("AegisV5")

def fetch_remote_config():
    """Fetches config and extracts DEVICE_ID."""
    for attempt in range(1, 4):
        try:
            resp = requests.get(REMOTE_CONFIG_URL, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                data["bot_token"] = data.get("bot_token", "").strip()
                data["admin_ids"] = [int(i) for i in data.get("admin_ids", [])]
                # Default DEVICE_ID if missing from remote (user should set locally)
                if "DEVICE_ID" not in data:
                    if os.path.exists("config.json"):
                        with open("config.json", "r") as f:
                            local = json.load(f)
                            data["DEVICE_ID"] = local.get("DEVICE_ID", "DEV_UNDEF")
                return data
        except Exception: pass
        time.sleep(5)
    # Fallback fully local
    if os.path.exists("config.json"):
        with open("config.json", "r") as f:
            return json.load(f)
    sys.exit(1)

class AegisFleetOrchestrator:
    def __init__(self, config):
        self.config = config
        self.device_id = str(self.config.get("DEVICE_ID", "DEV_1"))
        self.clones = self.config.get("clones", [])
        self.watchdogs = {pkg: WatchdogPro(pkg, log_func=self.safe_print) for pkg in self.clones}
        self.state = self.load_state() 
        self.app = None 
        self.loop = None
        self.launch_lock = threading.Lock()
        self.active_contexts = {} # user_id -> focused_device_id
        
        # Ghost Purge
        self.purge_ghosts()

    def purge_ghosts(self):
        try:
            curr_pid = os.getpid()
            cmd = f"su -c \"ps -ef | grep main.py | grep -v grep | grep -v {curr_pid} | awk '{{print $2}}' | xargs kill -9\""
            subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"[{self.device_id}] Ghosts purged.")
        except: pass

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
        logger.info(f"[{self.device_id}] {text}")
        # Broadcast to admins if they have this device as active context
        if self.app:
            clean_text = f"📟 [{self.device_id}]: {text}"
            # For simplicity in v5, if user has this device selected, they get logs
            for user_id, context_id in self.active_contexts.items():
                if context_id == self.device_id:
                    try:
                        asyncio.run_coroutine_threadsafe(
                            self.app.bot.send_message(chat_id=user_id, text=clean_text),
                            self.loop
                        )
                    except: pass

    def auth(self, user_id):
        return user_id in self.config.get("admin_ids", [])

    def get_fleet_keyboard(self):
        """Selector for multi-device (example for 3 devices, dynamic in prod)."""
        keyboard = [
            [InlineKeyboardButton(f"\U0001F4F1 DEV 1", callback_data="select_DEV_1"),
             InlineKeyboardButton(f"\U0001F4F1 DEV 2", callback_data="select_DEV_2")],
            [InlineKeyboardButton(f"\U0001F4F1 DEV 3", callback_data="select_DEV_3")],
            [InlineKeyboardButton("\U0001F3E2 FLEET STATUS", callback_data="fleet_status")]
        ]
        return InlineKeyboardMarkup(keyboard)

    def get_focused_keyboard(self):
        keyboard = [
            [KeyboardButton("\U0001F3E0 FLEET STATUS")],
            [KeyboardButton("\u26A1 GLOBAL ACTIONS")],
            [KeyboardButton("\U0001F3AE CLONE MGMT")],
            [KeyboardButton("\u2699\uFE0F DEVICE TOOLS")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_clones_keyboard(self):
        keyboard = []
        for pkg in self.clones:
            is_enabled = self.state.get(pkg, False)
            sym = "\u2705" if is_enabled else "\u274C"
            keyboard.append([InlineKeyboardButton(f"{sym} {pkg}", callback_data=f"toggle_{pkg}")])
        keyboard.append([InlineKeyboardButton("\u2B05 Back", callback_data="back_to_device")])
        return InlineKeyboardMarkup(keyboard)

    def get_tools_keyboard(self):
        keyboard = [
            [InlineKeyboardButton("\U0001F4F8 Snapshot", callback_data="snap"),
             InlineKeyboardButton("\U0001F9F9 Clean", callback_data="clean")],
            [InlineKeyboardButton("\U0001F4BB Shell", callback_data="shell_hint"),
             InlineKeyboardButton("\U0001F517 Edit Link", callback_data="link_hint")],
            [InlineKeyboardButton("\u2B05 Back", callback_data="back_to_device")]
        ]
        return InlineKeyboardMarkup(keyboard)

    def get_global_keyboard(self):
        keyboard = [
            [InlineKeyboardButton("\U0001F680 Global Start", callback_data="global_start"),
             InlineKeyboardButton("\U0001F6D1 Global Stop", callback_data="global_stop")],
            [InlineKeyboardButton("\U0001F504 Update All", callback_data="global_update"),
             InlineKeyboardButton("\U0001F4F8 Fleet Snap", callback_data="fleet_snap")],
            [InlineKeyboardButton("\u2B05 Back", callback_data="back_to_device")]
        ]
        return InlineKeyboardMarkup(keyboard)

    async def start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.auth(update.effective_user.id): return
        await update.message.reply_text(
            "\U0001F6E1 *Aegis Fleet Control v5*\nSelect a device to manage or view fleet status:",
            reply_markup=self.get_fleet_keyboard(),
            parse_mode='Markdown'
        )

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.auth(user_id): return
        text = update.message.text
        focused = self.active_contexts.get(user_id)

        if text == "\U0001F3E0 FLEET STATUS":
            await self.send_local_stats(update)
        elif text == "\u26A1 GLOBAL ACTIONS":
            await update.message.reply_text("\u26A1 *GLOBAL CONTROL*", reply_markup=self.get_global_keyboard(), parse_mode='Markdown')
        elif text == "\U0001F3AE CLONE MGMT":
            await update.message.reply_text(f"🎮 *{self.device_id} Clones:*", reply_markup=self.get_clones_keyboard(), parse_mode='Markdown')
        elif text == "\u2699\uFE0F DEVICE TOOLS":
            await update.message.reply_text(f"⚙️ *{self.device_id} Tools:*", reply_markup=self.get_tools_keyboard(), parse_mode='Markdown')
        
        # Shell logic (Global if no context or prefix)
        if text.startswith("$") or text.lower().startswith("shell "):
            cmd = text[1:].strip() if text.startswith("$") else text[6:].strip()
            # If we are the focused device, execute. Otherwise ignore (to avoid duplicates from all devices)
            if focused == self.device_id:
                await self.execute_shell(update, cmd)

    async def execute_shell(self, update: Update, cmd):
        try:
            res = subprocess.run(f"su -c '{cmd}'", shell=True, capture_output=True, text=True, timeout=30)
            out = (res.stdout + res.stderr).strip() or "[No output]"
            if len(out) > 3000: out = out[:3000] + "...[Truncated]"
            await update.message.reply_text(f"```bash\n{out}\n```", parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    async def send_local_stats(self, update: Update):
        active = sum(1 for v in self.state.values() if v)
        dis = len(self.clones) - active
        clones_str = f"{active}/{len(self.clones)} (Disabled: {dis})"
        report = HardwareMonitor.get_dashboard_report(self.device_id, clones_str)
        await update.message.reply_text(f"```\n{report}\n```", parse_mode='Markdown')

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = query.from_user.id
        if not self.auth(user_id): return
        data = query.data

        # Multi-Device Selection
        if data.startswith("select_"):
            dev = data.replace("select_", "")
            self.active_contexts[user_id] = dev
            if dev == self.device_id:
                await query.message.reply_text(f"\u2705 Switched context to {dev}", reply_markup=self.get_focused_keyboard())
            await query.answer()

        elif data == "fleet_status":
            await self.send_local_stats(update)
            await query.answer()

        elif data == "back_to_device":
            await query.edit_message_text(f"Managed Device: {self.device_id}", reply_markup=self.get_focused_keyboard())
            await query.answer()

        # Local Actions (only if focused)
        focused = self.active_contexts.get(user_id)
        if focused == self.device_id:
            if data.startswith("toggle_"):
                pkg = data.replace("toggle_", "")
                self.state[pkg] = not self.state.get(pkg, False)
                self.save_state()
                await query.edit_message_reply_markup(reply_markup=self.get_clones_keyboard())
            elif data == "snap":
                await self.take_snap(query.message)
            elif data == "clean":
                MemoryManager.system_deep_clean()
                await query.answer("\U0001F9F9 System cleaning...")

        # Global Actions (all devices respond)
        if data == "global_start":
            self.master_start()
            await query.answer("\u26A1 Fleet start sequence initiated.")
        elif data == "global_stop":
            for pkg in self.clones:
                self.state[pkg] = False
                self.watchdogs[pkg].force_stop()
            self.save_state()
            await query.answer("\U0001F6D1 Fleet stopped.")
        elif data == "fleet_snap":
            await self.take_snap(query.message)
            await query.answer()
        elif data == "global_update":
            self.update_system()

    async def take_snap(self, message):
        try:
            subprocess.run(f"su -c 'screencap -p {SCREENSHOT_PATH}'", shell=True)
            if os.path.exists(SCREENSHOT_PATH):
                with open(SCREENSHOT_PATH, 'rb') as f:
                    await message.reply_photo(photo=f, caption=f"\U0001F4F8 Snapshot: {self.device_id}")
                os.remove(SCREENSHOT_PATH)
        except: pass

    def parse_roblox_link(self, link):
        """Smart parser for roblox links (v5)."""
        if "privateServerLinkCode" in link:
            # Already a direct intent-ish link or raw URL
            return link
        if "roblox.com/games/" in link:
            # Extract ID and try to make direct roblox:// intent
            match = re.search(r'games/(\d+)', link)
            if match:
                game_id = match.group(1)
                return f"roblox://placeId={game_id}"
        return link

    def safe_launch(self, pkg):
        """v5 Optimized Launch with RAM Threshold."""
        logger.info(f"[{self.device_id}] Launching {pkg}")
        
        # RAM Threshold Check (400MB)
        mem = psutil.virtual_memory()
        if mem.available < 400 * 1024 * 1024:
            self.safe_print("\u26A0\uFE0F Low RAM (<400MB). Pausing launch 15s...")
            time.sleep(15)
            
        # I/O Relief
        subprocess.run("su -c 'sync; echo 3 > /proc/sys/vm/drop_caches'", shell=True)
        
        # Link Parsing
        raw_link = ServerEngine.get_random_server() or self.config.get("default_link", "")
        link = self.parse_roblox_link(raw_link)
        
        cmd = f"su -c 'am start -a android.intent.action.VIEW -d \"{link}\" {pkg}'"
        
        self.watchdogs[pkg].last_launch_time = time.time()
        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setpgrp)
        
        # Priority renice
        threading.Thread(target=self.wait_and_renice, args=(pkg,)).start()

    def wait_and_renice(self, pkg):
        time.sleep(10)
        pid = self.watchdogs[pkg].get_pid()
        if pid:
            subprocess.run(f"su -c 'renice -n -20 -p {pid}'", shell=True)
            self.safe_print(f"Priority -20 set for {pkg} (PID {pid})")

    def master_start(self):
        for pkg in self.clones: self.state[pkg] = True
        self.save_state()
        def sequence():
            for pkg in self.clones:
                if self.state.get(pkg):
                    self.safe_launch(pkg)
                    time.sleep(10) # v5 stagger
        threading.Thread(target=sequence).start()

    def maintenance_task(self):
        while True:
            time.sleep(1800)
            subprocess.run("su -c 'pm trim-caches 999G'", shell=True)

    def watchdog_thread(self):
        self.safe_print("v5 Watchdog Online (L1+L2).")
        time.sleep(60)
        while True:
            for pkg in self.clones:
                if self.state.get(pkg, False):
                    wd = self.watchdogs[pkg]
                    if not wd.is_alive():
                        self.safe_print(f"v5 Recovery: {pkg}")
                        self.safe_launch(pkg)
                        time.sleep(15)
            gc.collect()
            time.sleep(60)

    def update_system(self):
        try:
            files = ["main.py", "watchdog_pro.py", "memory_manager.py", "hardware_monitor.py", "server_engine.py", "config.json"]
            base_url = self.config.get("github_url", "https://raw.githubusercontent.com/DeformexExx/farm/refs/heads/main")
            for f in files:
                url = f"{base_url}/{f}"
                subprocess.run(f"curl -L {url} -o {f}", shell=True)
            os.execv(sys.executable, ['python'] + sys.argv)
        except Exception as e: self.safe_print(f"Update failed: {e}")

    def run(self):
        async def post_init(application):
            self.app = application
            self.loop = asyncio.get_event_loop()
            if self.config.get("global_auto_start"):
                threading.Timer(30.0, self.master_start).start()
            for admin_id in self.config["admin_ids"]:
                try: await application.bot.send_message(admin_id, f"🚢 Aegis v5 Fleet Control: {self.device_id} ONLINE.")
                except: pass

        app = ApplicationBuilder().token(self.config["bot_token"]).post_init(post_init).build()
        app.add_handler(CommandHandler("start", self.start_cmd))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_text))
        app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        MemoryManager.set_oom_priority()
        MemoryManager.setup_swap()
        threading.Thread(target=self.watchdog_thread, daemon=True).start()
        threading.Thread(target=self.maintenance_task, daemon=True).start()
        app.run_polling()

if __name__ == "__main__":
    cfg = fetch_remote_config()
    time.sleep(5)
    AegisFleetOrchestrator(cfg).run()
