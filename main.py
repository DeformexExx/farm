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
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

# Import modules
from hardware_monitor import HardwareMonitor
from memory_manager import MemoryManager
from server_engine import ServerEngine
from watchdog_pro import WatchdogPro

REMOTE_CONFIG_URL = "https://raw.githubusercontent.com/DeformexExx/farm/refs/heads/main/config.json"
BOOT_TRACKER_FILE = "last_boot.txt"

def fetch_remote_config():
    """Fetches config directly from GitHub with 5 retries and 10s delay."""
    for attempt in range(1, 6):
        try:
            print(f"Fetching remote config (Attempt {attempt}/5)...")
            response = requests.get(REMOTE_CONFIG_URL, timeout=15)
            if response.status_code == 200:
                data = response.json()
                # Validation & Processing
                token = data.get("bot_token", "").strip()
                admins = [int(i) for i in data.get("admin_ids", [])]
                clones = data.get("clones", [])
                
                if not token or token == "your_bot_token_here":
                    print("CRITICAL: Remote config contains invalid/placeholder token!")
                    sys.exit(1)
                
                # Update data with processed values
                data["bot_token"] = token
                data["admin_ids"] = admins
                data["clones"] = clones
                print("Remote config loaded successfully.")
                return data
            else:
                print(f"Failed to fetch config: HTTP {response.status_code}")
        except Exception as e:
            print(f"Attempt {attempt} failed: {e}")
        
        if attempt < 5:
            print("Retrying in 10 seconds...")
            time.sleep(10)
    
    print("CRITICAL: Failed to fetch remote config after 5 attempts. Exiting.")
    sys.exit(1)

def kill_existing_instances():
    """PID Lock to avoid 409 Conflict."""
    try:
        current_pid = os.getpid()
        result = subprocess.run("ps -ef | grep python | grep main.py | grep -v grep", shell=True, capture_output=True, text=True)
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split()
                if len(parts) > 1:
                    pid = int(parts[1])
                    if pid != current_pid:
                        subprocess.run(f"kill -9 {pid}", shell=True)
                        print(f"Killed legacy instance (PID {pid})")
    except Exception as e:
        print(f"PID Lock error: {e}")

class AegisFarmOS:
    def __init__(self, config):
        self.config = config
        self.clones = self.config.get("clones", [])
        self.watchdogs = {pkg: WatchdogPro(pkg) for pkg in self.clones}
        self.active_clones = set(self.clones)
        self.is_running = True
        self.failure_counts = {pkg: 0 for pkg in self.clones}
        self.app = None

    def authenticated(self, user_id):
        return user_id in self.config.get("admin_ids", [])

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        await self.help_command(update, context)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        
        keyboard = [[InlineKeyboardButton("\U0001F4F8 Snapshot All Clones", callback_data='snap_all')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        memo = (
            "\U0001F6E1 *Aegis Farm OS - Direct Remote Mode*\n\n"
            "\U0001F4CA *Monitoring:*\n"
            "/status - System stats\n"
            "/screen [pkg] - Capture specific clone\n"
            "/help - This memo\n\n"
            "\U0001F916 *Control:*\n"
            "/enable [pkg] - Enable watchdog\n"
            "/disable [pkg] - Disable & stop\n"
            "/restart - Restart all active\n\n"
            "\U0001F517 *Pool:*\n"
            "/add_server [url] - Add link\n"
            "/clear_servers - Wipe pool\n\n"
            "\U00002699\U0000FE0F *System:*\n"
            "/update - Sync modules from GitHub\n"
            "\n*Clones Loaded:* " + ", ".join(self.clones)
        )
        await update.message.reply_text(memo, parse_mode='Markdown', reply_markup=reply_markup)

    async def screen(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        if not context.args:
            await update.message.reply_text("Usage: /screen [pkg]")
            return
            
        pkg = context.args[0]
        if pkg not in self.clones:
            await update.message.reply_text(f"\U0000274C Unknown package: {pkg}")
            return

        path = f"/sdcard/screen_{pkg}.png"
        try:
            await update.message.reply_text(f"\U0001F4F8 Capturing {pkg}...")
            subprocess.run(f"su -c 'screencap -p {path}'", shell=True)
            with open(path, 'rb') as f:
                await update.message.reply_photo(photo=f, caption=f"Snapshot: {pkg}")
        except Exception as e:
            await update.message.reply_text(f"\U0000274C Screenshot failed: {e}")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = query.from_user.id
        if not self.authenticated(user_id):
            await query.answer("Access Denied", show_alert=True)
            return

        if query.data == 'snap_all':
            await query.answer("Capturing all clones...")
            await query.edit_message_text("\U0001F4F8 Processing collective snapshot...")
            
            for pkg in self.clones:
                path = f"/sdcard/snap_all_{pkg}.png"
                try:
                    subprocess.run(f"su -c 'screencap -p {path}'", shell=True)
                    time.sleep(0.5)
                    with open(path, 'rb') as f:
                        await context.bot.send_photo(chat_id=user_id, photo=f, caption=f"Collective Snapshot: {pkg}")
                except Exception as e:
                    await context.bot.send_message(chat_id=user_id, text=f"\U0000274C Failed {pkg}: {e}")
            
            await context.bot.send_message(chat_id=user_id, text="\U00002705 Snapshot All sequence complete.")

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        report = HardwareMonitor.get_report() + "\n\n"
        for pkg, wd in self.watchdogs.items():
            pid = wd.get_pid()
            mark = "\U0001F7E2" if pkg in self.active_clones else "\U000026AA"
            state = f"\U00002705 PID {pid}" if pid else "\U0000274C Off"
            report += f"{mark} {pkg}: {state}\n"
        await update.message.reply_text(f"\U0001F4CA SYSTEM STATUS\n\n{report}")

    async def enable_clone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        if not context.args: return
        pkg = context.args[0]
        if pkg in self.clones:
            self.active_clones.add(pkg)
            await update.message.reply_text(f"\U00002705 {pkg} enabled.")
        else:
            await update.message.reply_text(f"\U0000274C Unknown package: {pkg}")

    async def disable_clone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        if not context.args: return
        pkg = context.args[0]
        if pkg in self.clones:
            self.active_clones.discard(pkg)
            self.watchdogs[pkg].force_stop()
            await update.message.reply_text(f"\U0001F6D1 {pkg} disabled.")
        else:
            await update.message.reply_text(f"\U0000274C Unknown package: {pkg}")

    async def restart_clones(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        await update.message.reply_text("\U0001F504 Restarting all active clones...")
        for pkg in self.active_clones:
            self.launch_clone(pkg)
            await asyncio.sleep(self.config.get("delays", {}).get("launch", 15))
        await update.message.reply_text("\U00002705 Restart command sequence sent.")

    async def update_system(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        await update.message.reply_text("\U0001F504 Downloading module updates...")
        
        base_url = "https://raw.githubusercontent.com/DeformexExx/farm/refs/heads/main"
        files = ["main.py", "watchdog_pro.py", "memory_manager.py", "server_engine.py", "hardware_monitor.py"]
        
        try:
            for filename in files:
                url = f"{base_url}/{filename}"
                success = False
                for _ in range(3):
                    try:
                        resp = requests.get(url, timeout=10)
                        if resp.status_code == 200:
                            with open(filename, "wb") as f:
                                f.write(resp.content)
                            success = True
                            break
                    except: time.sleep(1)
                if not success:
                    print(f"Failed to fetch {filename}")
            
            await update.message.reply_text("\U00002705 Modules updated. Restarting OS...")
            os.execv(sys.executable, ['python'] + sys.argv)
        except Exception as e:
            await update.message.reply_text(f"\U0000274C Update failed: {e}")

    def safe_launch(self, package_name):
        """Memory-safe non-blocking launch using monkey."""
        print(f"Safe launching {package_name}...")
        MemoryManager.deep_clean_clone(package_name)
        MemoryManager.drop_system_caches()
        
        # Detached launch to save RAM
        cmd = f"su -c 'monkey -p {package_name} -c android.intent.category.LAUNCHER 1'"
        time.sleep(0.5)
        
        subprocess.Popen(
            cmd, 
            shell=True, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL, 
            preexec_fn=os.setpgrp
        )

    def launch_clone(self, pkg):
        """Redirects to safe_launch for OOM prevention."""
        self.safe_launch(pkg)

    async def notify_failure(self, pkg):
        """Sends Telegram notification if 3 failed attempts reached."""
        for admin_id in self.config.get("admin_ids", []):
            try:
                await self.app.bot.send_message(
                    chat_id=admin_id, 
                    text=f"\U000026A0 *CLONE FAILURE*\nPackage: {pkg}\nAttempts: 3 failures in a row.",
                    parse_mode='Markdown'
                )
            except Exception as e:
                print(f"Notify failure error: {e}")

    def watchdog_loop(self):
        print("Delaying Watchdog loop post-boot...")
        time.sleep(10)
        
        while self.is_running:
            for pkg in self.clones:
                if pkg in self.active_clones:
                    wd = self.watchdogs[pkg]
                    if not wd.is_alive():
                        self.failure_counts[pkg] += 1
                        print(f"Watchdog: {pkg} failure ({self.failure_counts[pkg]}). Restoring...")
                        
                        if self.failure_counts[pkg] == 3:
                            # Trigger Telegram notification on 3rd failure
                            asyncio.run_coroutine_threadsafe(self.notify_failure(pkg), self.app.loop)
                        
                        self.launch_clone(pkg)
                        time.sleep(self.config.get("delays", {}).get("launch", 15))
                    else:
                        self.failure_counts[pkg] = 0
            
            # Memory Safe: Force garbage collection
            gc.collect()
            time.sleep(self.config.get("delays", {}).get("watchdog", 60))

    def run_bot(self):
        async def post_init(application):
            # Anti-Spam
            now = time.time()
            if os.path.exists(BOOT_TRACKER_FILE):
                try:
                    with open(BOOT_TRACKER_FILE, "r") as f:
                        last_boot = float(f.read().strip())
                        if now - last_boot < 120:
                            print("Restarting anti-spam: Skipping notification.")
                            return
                except: pass
            
            with open(BOOT_TRACKER_FILE, "w") as f:
                f.write(str(now))

            print("Broadcasting System Online...")
            for admin_id in self.config.get("admin_ids", []):
                try:
                    await application.bot.send_message(
                        chat_id=admin_id, 
                        text="\U0001F680 Aegis Farm OS: Online (OOM Protected)"
                    )
                except Exception as e:
                    print(f"Notify error: {e}")

        self.app = ApplicationBuilder().token(self.config["bot_token"]).post_init(post_init).build()
        
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("status", self.status))
        self.app.add_handler(CommandHandler("screen", self.screen))
        self.app.add_handler(CommandHandler("enable", self.enable_clone))
        self.app.add_handler(CommandHandler("disable", self.disable_clone))
        self.app.add_handler(CommandHandler("restart", self.restart_clones))
        self.app.add_handler(CommandHandler("update", self.update_system))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        MemoryManager.set_oom_priority()
        MemoryManager.setup_swap()
        threading.Thread(target=self.watchdog_loop, daemon=True).start()
        
        print("Aegis Heartbeat Active.")
        self.app.run_polling()

if __name__ == "__main__":
    kill_existing_instances()
    # Direct Remote Fetch
    final_cfg = fetch_remote_config()
    
    # Global delay to smooth CPU spike
    print("Smoothing CPU spike (5s delay)...")
    time.sleep(5)
    
    bot = AegisFarmOS(final_cfg)
    bot.run_bot()
