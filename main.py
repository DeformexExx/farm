import os
import time
import asyncio
import threading
import logging
import subprocess
import sys
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Import modules
from hardware_monitor import HardwareMonitor
from memory_manager import MemoryManager
from server_engine import ServerEngine
from watchdog_pro import WatchdogPro

# Configuration
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AUTH_USERS = [int(i.strip()) for i in os.getenv("AUTHORIZED_USER_IDS", "").split(",") if i.strip()]
CLONE_PACKAGES = [p.strip() for p in os.getenv("CLONE_PACKAGES", "").split(",") if p.strip()]

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("AegisFarmOS")

class AegisFarmOS:
    def __init__(self):
        self.watchdogs = {pkg: WatchdogPro(pkg) for pkg in CLONE_PACKAGES}
        self.active_clones = set(CLONE_PACKAGES) # By default all are enabled
        self.is_running = True

    def authenticated(self, user_id):
        return user_id in AUTH_USERS

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        await self.help_command(update, context)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        memo = (
            "🛡 *Aegis Farm OS - Command Memo*\n\n"
            "📊 *Monitoring:*\n"
            "/status - System stats & clone status\n"
            "/help - Show this message\n\n"
            "🤖 *Clone Control:*\n"
            "/enable [pkg] - Enable watchdog for clone\n"
            "/disable [pkg] - Disable watchdog & stop clone\n"
            "/restart - Force restart all active clones\n\n"
            "🔗 *Server Pool:*\n"
            "/add_server [url] - Add link to pool\n"
            "/clear_servers - Wipe pool (uses DEFAULT_LINK)\n\n"
            "⚙️ *System:*\n"
            "/update - Update modules from GitHub\n\n"
            "Pkg names: " + ", ".join(CLONE_PACKAGES)
        )
        await update.message.reply_text(memo, parse_mode='Markdown')

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        hw_report = HardwareMonitor.get_report()
        clone_status = ""
        for pkg, wd in self.watchdogs.items():
            pid = wd.get_pid()
            is_enabled = "🟢 Enabled" if pkg in self.active_clones else "⚪ Disabled"
            proc_status = f"✅ Running (PID {pid})" if pid else "❌ Stopped"
            clone_status += f"🤖 {pkg}: {is_enabled} | {proc_status}\n"
        
        await update.message.reply_text(f"📊 SYSTEM STATUS\n\n{hw_report}\n\n{clone_status}")

    async def enable_clone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        if not context.args: return
        pkg = context.args[0]
        if pkg in CLONE_PACKAGES:
            self.active_clones.add(pkg)
            await update.message.reply_text(f"✅ {pkg} enabled. Watchdog will start it soon.")
        else:
            await update.message.reply_text(f"❌ Unknown package: {pkg}")

    async def disable_clone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        if not context.args: return
        pkg = context.args[0]
        if pkg in CLONE_PACKAGES:
            if pkg in self.active_clones:
                self.active_clones.remove(pkg)
            self.watchdogs[pkg].force_stop()
            await update.message.reply_text(f"🛑 {pkg} disabled and stopped.")
        else:
            await update.message.reply_text(f"❌ Unknown package: {pkg}")

    async def add_server(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        if not context.args:
            await update.message.reply_text("Usage: /add_server [url]")
            return
        url = context.args[0]
        if ServerEngine.add_server(url):
            await update.message.reply_text(f"✅ Server added to pool.")
        else:
            await update.message.reply_text("ℹ️ Server already in pool.")

    async def clear_servers(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        ServerEngine.clear_servers()
        await update.message.reply_text("🗑 Server pool cleared. Using DEFAULT_LINK for now.")

    async def update_system(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        await update.message.reply_text("🔄 Updating modules via Requests...")
        
        base_url = os.getenv("GITHUB_RAW_BASE")
        files_to_update = {
            "main.py": f"{base_url}/main.py",
            "watchdog_pro.py": f"{base_url}/watchdog_pro.py",
            "memory_manager.py": f"{base_url}/memory_manager.py",
            "server_engine.py": f"{base_url}/server_engine.py",
            "hardware_monitor.py": f"{base_url}/hardware_monitor.py"
        }
        
        try:
            import requests
            for filename, url in files_to_update.items():
                logger.info(f"Downloading {filename} from {url}...")
                response = requests.get(url, timeout=15)
                if response.status_code == 200:
                    with open(filename, "wb") as f:
                        f.write(response.content)
                else:
                    await update.message.reply_text(f"❌ Failed to download {filename}: {response.status_code}")
                    return

            await update.message.reply_text("✅ All modules updated. Restarting...")
            os.execv(sys.executable, ['python'] + sys.argv)
        except Exception as e:
            logger.error(f"Update failed: {e}")
            await update.message.reply_text(f"❌ Update error: {e}")

    async def restart_clones(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.authenticated(update.effective_user.id): return
        await update.message.reply_text("🔄 Restarting all ENABLED clones...")
        for pkg in self.active_clones:
            self.launch_clone(pkg)
            await asyncio.sleep(25) # Staggered launch
        await update.message.reply_text("✅ Enabled clones restart command sent.")

    def launch_clone(self, pkg):
        logger.info(f"Launching {pkg}...")
        # 1. Deep Purge
        MemoryManager.deep_clean_clone(pkg)
        MemoryManager.drop_system_caches()
        
        # 2. Get Random Server
        link = ServerEngine.get_random_server()
        if not link:
            logger.error("No servers in pool!")
            return

        # 3. Secure Double-Escaped Link Armor Launch
        # Pattern: su -c "am start -a android.intent.action.VIEW -d \"{link}\" {pkg}"
        cmd = f'su -c "am start -a android.intent.action.VIEW -d \\"{link}\\" {pkg}"'
        subprocess.run(cmd, shell=True)

    def watchdog_loop(self):
        """Background thread for monitoring."""
        logger.info("Watchdog thread started.")
        while self.is_running:
            for pkg in CLONE_PACKAGES:
                if pkg in self.active_clones:
                    wd = self.watchdogs[pkg]
                    if not wd.is_alive():
                        logger.warning(f"Watchdog detected issue with {pkg}. Restarting...")
                        self.launch_clone(pkg)
                        time.sleep(30) # Delay between restarts to avoid intent overflow
            time.sleep(10)

    def run_bot(self):
        app = ApplicationBuilder().token(TOKEN).build()
        
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("status", self.status))
        app.add_handler(CommandHandler("enable", self.enable_clone))
        app.add_handler(CommandHandler("disable", self.disable_clone))
        app.add_handler(CommandHandler("add_server", self.add_server))
        app.add_handler(CommandHandler("clear_servers", self.clear_servers))
        app.add_handler(CommandHandler("update", self.update_system))
        app.add_handler(CommandHandler("restart", self.restart_clones))
        
        # Setup memory optimization
        MemoryManager.set_oom_priority()
        MemoryManager.setup_swap()

        # Start watchdog thread
        threading.Thread(target=self.watchdog_loop, daemon=True).start()
        
        logger.info("Bot starting...")
        app.run_polling()

if __name__ == "__main__":
    bot = AegisFarmOS()
    bot.run_bot()
