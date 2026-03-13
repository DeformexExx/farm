import os
import time
import asyncio
import threading
import logging
import subprocess
import sys
import json
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Import modules
from hardware_monitor import HardwareMonitor
from memory_manager import MemoryManager
from server_engine import ServerEngine
from watchdog_pro import WatchdogPro

CONFIG_PATH = "config.json"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("AegisFarmOS")

def sync_config(base_url):
    """Attempts to download config.json from GitHub."""
    if not base_url: return None
    url = f"{base_url}/{CONFIG_PATH}"
    try:
        import requests
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            new_config = response.json()
            with open(CONFIG_PATH, "w") as f:
                json.dump(new_config, f, indent=2)
            logger.info("Config synced from GitHub.")
            return new_config
    except Exception as e:
        logger.warning(f"Failed to sync remote config: {e}")
    return None

def load_config():
    """Load local config.json and validate."""
    if not os.path.exists(CONFIG_PATH):
        logger.error(f"CRITICAL: {CONFIG_PATH} not found!")
        sys.exit(1)
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)
    # Strict validation
    config['admin_ids'] = [int(i) for i in config.get('admin_ids', [])]
    return config

def kill_existing_instances():
    """PID Lock to avoid 409 Conflict."""
    try:
        current_pid = os.getpid()
        # Find other python processes running main.py
        result = subprocess.run("ps -ef | grep python | grep main.py | grep -v grep", shell=True, capture_output=True, text=True)
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split()
                if len(parts) > 1:
                    pid = int(parts[1])
                    if pid != current_pid:
                        subprocess.run(f"kill -9 {pid}", shell=True)
                        logger.info(f"Killed existing instance (PID {pid})")
    except Exception as e:
        logger.error(f"PID Lock error: {e}")

class AegisFarmOS:
    def __init__(self, config):
        self.config = config
        self.clones = self.config.get("clones", [])
        self.watchdogs = {pkg: WatchdogPro(pkg) for pkg in self.clones}
        self.active_clones = set(self.clones)
        self.is_running = True

    def authenticated(self, user_id):
        return user_id in self.config.get("admin_ids", [])

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        await self.help_command(update, context)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        memo = (
            "🛡 *Aegis Farm OS - Ultimate Memo*\n\n"
            "📊 *Monitoring:*\n"
            "/status - System stats\n"
            "/screen [pkg] - Capture clone screeen\n"
            "/help - This memo\n\n"
            "🤖 *Control:*\n"
            "/enable [pkg] - Enable watchdog\n"
            "/disable [pkg] - Disable & stop\n"
            "/restart - Restart active clones\n\n"
            "🔗 *Pool:*\n"
            "/add_server [url] - Add link\n"
            "/clear_servers - Wipe pool\n\n"
            "⚙️ *System:*\n"
            "/update - Sync all files from GitHub\n"
        )
        await update.message.reply_text(memo, parse_mode='Markdown')

    async def screen(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        if not context.args:
            await update.message.reply_text("Usage: /screen [pkg]")
            return
        pkg = context.args[0]
        path = f"/sdcard/screen_{pkg}.png"
        try:
            await update.message.reply_text(f"📸 Capturing {pkg}...")
            subprocess.run(f"su -c 'screencap -p {path}'", shell=True)
            with open(path, 'rb') as f:
                await update.message.reply_photo(photo=f, caption=f"Snapshot: {pkg}")
        except Exception as e:
            await update.message.reply_text(f"❌ Screenshot failed: {e}")

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        report = HardwareMonitor.get_report() + "\n\n"
        for pkg, wd in self.watchdogs.items():
            pid = wd.get_pid()
            mark = "🟢" if pkg in self.active_clones else "⚪"
            state = f"✅ PID {pid}" if pid else "❌ Off"
            report += f"{mark} {pkg}: {state}\n"
        await update.message.reply_text(f"�    async def enable_clone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        if not context.args: return
        pkg = context.args[0]
        if pkg in self.clones:
            self.active_clones.add(pkg)
            await update.message.reply_text(f"✅ {pkg} enabled.")
        else:
            await update.message.reply_text(f"❌ Unknown package: {pkg}")

    async def disable_clone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        if not context.args: return
        pkg = context.args[0]
        if pkg in self.clones:
            self.active_clones.discard(pkg)
            self.watchdogs[pkg].force_stop()
            await update.message.reply_text(f"🛑 {pkg} disabled.")
        else:
            await update.message.reply_text(f"❌ Unknown package: {pkg}")

    async def add_server(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        if not context.args: return
        if ServerEngine.add_server(context.args[0]):
            await update.message.reply_text("✅ Server added.")
        else:
            await update.message.reply_text("ℹ️ Already in pool.")

    async def clear_servers(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        ServerEngine.clear_servers()
        await update.message.reply_text("🗑 Pool cleared.")

    async def restart_clones(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        await update.message.reply_text("🔄 Restarting active clones...")
        for pkg in self.active_clones:
            self.launch_clone(pkg)
            await asyncio.sleep(self.config.get("delays", {}).get("launch", 15))
        await update.message.reply_text("✅ Batch command sent.")

    def launch_clone(self, pkg):
        logger.info(f"Launching {pkg}...")
        MemoryManager.deep_clean_clone(pkg)
        MemoryManager.drop_system_caches()
        
        link = ServerEngine.get_random_server() or self.config.get("default_link")
        # Final escaping: su -c "am start ... -d '{link}' {pkg}"
        cmd = f'su -c "am start -a android.intent.action.VIEW -d \'{link}\' {pkg}"'
        time.sleep(0.5) # Stability delay
        subprocess.run(cmd, shell=True)

    def watchdog_loop(self):
        while self.is_running:
            for pkg in self.clones:
                if pkg in self.active_clones:
                    wd = self.watchdogs[pkg]
                    if not wd.is_alive():
                        logger.warning(f"Watchdog: {pkg} crashed. Restoring...")
                        self.launch_clone(pkg)
                        time.sleep(self.config.get("delays", {}).get("launch", 15))
            time.sleep(self.config.get("delays", {}).get("watchdog", 60))

    def run_bot(self):
        app = ApplicationBuilder().token(self.config.get("bot_token")).build()
        
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("status", self.status))
        app.add_handler(CommandHandler("screen", self.screen))
        app.add_handler(CommandHandler("enable", self.enable_clone))
        app.add_handler(CommandHandler("disable", self.disable_clone))
        app.add_handler(CommandHandler("add_server", self.add_server))
        app.add_handler(CommandHandler("clear_servers", self.clear_servers))
        app.add_handler(CommandHandler("update", self.update_system))
        app.add_handler(CommandHandler("restart", self.restart_clones))
        
        MemoryManager.set_oom_priority()
        MemoryManager.setup_swap()

        threading.Thread(target=self.watchdog_loop, daemon=True).start()
        
        logger.info("System Online. Notify admins...")
        
        # Proper startup notification
        async def post_init(application):
            for admin_id in self.config.get("admin_ids", []):
                try:
                    await application.bot.send_message(chat_id=admin_id, text="🚀 Aegis Farm OS: System Online & Config Loaded.")
                except Exception as e:
                    logger.error(f"Startup notify failed for {admin_id}: {e}")

        # Note: ApplicationBuilder.post_init is available in newer v20+
        # But we can also just run it after start
        
        app.run_polling()

if __name__ == "__main__":
n_polling()

if __name__ == "__main__":
    kill_existing_instances()
    initial_cfg = load_config()
    # Try remote sync on boot
    remote_cfg = sync_config(initial_cfg.get("github_url"))
    final_cfg = remote_cfg if remote_cfg else initial_cfg
    
    bot = AegisFarmOS(final_cfg)
    bot.run_bot()
