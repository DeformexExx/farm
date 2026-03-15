# -*- coding: utf-8 -*-
import os
import sys
import asyncio
import logging
import time
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

from config_manager import ConfigManager
from ui_manager import UIManager
from monitor import MonitorEngine
from injection_engine import InjectionEngine
from bash_utils import run_bash
from persistence_manager import PersistenceManager

# IDENTITY & PATHS
if len(sys.argv) < 2:
    print("❌ Укажите DEVICE_ID. Пример: python main.py DEV_2")
    sys.exit(1)

DEVICE_ID = sys.argv[1]
HOME_DIR = os.path.expanduser("~")
FARM_DIR = os.path.join(HOME_DIR, "farm")
if not os.path.exists(FARM_DIR):
    FARM_DIR = os.getcwd()  # Fallback

SCREENSHOT_PATH = "/data/local/tmp/s.png"

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format=f'%(asctime)s [{DEVICE_ID}] [%(levelname)s] %(message)s'
)
logger = logging.getLogger("AegisV20")

class TelegramLogHandler(logging.Handler):
    """Custom logging handler to buffer logs and send to LogStreamer."""
    def __init__(self, streamer):
        super().__init__()
        self.streamer = streamer

    def emit(self, record):
        log_entry = self.format(record)
        prefix = "[LOG]"
        if record.levelno >= logging.ERROR: prefix = "[ERR]"
        elif record.levelno >= logging.WARNING: prefix = "[WRN]"
        self.streamer.add_log(f"{prefix} {log_entry}")

class LogStreamer:
    """Buffers logs and sends to Telegram every T seconds."""
    def __init__(self, bot, chat_id, interval=2.0):
        self.bot = bot
        self.chat_id = chat_id
        self.interval = interval
        self.buffer = []
        self._lock = asyncio.Lock()
        self._is_running = False

    def add_log(self, text):
        self.buffer.append(text)

    async def start(self):
        if self._is_running: return
        self._is_running = True
        while self._is_running:
            await asyncio.sleep(self.interval)
            async with self._lock:
                if self.buffer:
                    logs = "\n".join(self.buffer)
                    self.buffer = []
                    await self._send(logs)

    def stop(self):
        self._is_running = False

    async def _send(self, text):
        # Monospace Code Block Terminal Aesthetic
        header = "┌─── 🖥 CONSOLE ───┐"
        footer = "└──────────────────┘"
        try:
            # Chunking for Telegram limits
            for i in range(0, len(text), 3900):
                chunk = text[i:i+3900]
                full_msg = f"<code>{header}\n{chunk}\n{footer}</code>"
                await self.bot.send_message(chat_id=self.chat_id, text=full_msg, parse_mode='HTML')
        except Exception:
            pass

class AegisNebulaBot:
    def __init__(self):
        self.device_id = DEVICE_ID
        self.config = ConfigManager(self.device_id, FARM_DIR)
        self.persistence = PersistenceManager(FARM_DIR)
        self.application = None
        self.active_clones = set(self.persistence.target_clones) if self.persistence.auto_restore else set()
        self._dashboard_msg = None
        self.console_mode = self.persistence.console_mode
        self._log_handler: logging.Handler | None = None
        self._streamer: LogStreamer | None = None
        self._loop = None

    async def sanity_check(self):
        """Clean slate: stop all clones and ensure no ghost pythons."""
        logger.info("⚙️ Performing Sanity Check...")
        # Get all clones to stop them
        for clone in self.config.clones_data:
            name = clone.get("name")
            if name:
                await run_bash(f"su -c 'am force-stop com.roblox.{name}'")
        
        # Kill other python instances except self
        my_pid = os.getpid()
        await run_bash(f"su -c 'pgrep python | grep -v {my_pid} | xargs kill -9'")
        logger.info("✅ Sanity Check complete.")

    async def _check_admin(self, user_id: int) -> bool:
        return user_id in self.config.admin_ids

    async def start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin(update.effective_user.id): return
        
        await update.message.reply_text(
            UIManager.get_welcome_text(self.device_id),
            reply_markup=UIManager.get_main_keyboard(),
            parse_mode='Markdown'
        )

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin(update.effective_user.id): return
        text = update.message.text

        if text == "📱 DEVICE":
            await self.send_device_menu(update)
        elif text == "🤖 CLONES":
            await self.send_clones_menu(update)
        elif text == "⚙️ SYSTEM":
            await self.send_system_menu(update)

    async def send_device_menu(self, update: Update):
        ram, cpu, temp = await MonitorEngine.get_system_stats()
        text = UIManager.format_dashboard(self.device_id, ram, cpu, temp)
        await update.message.reply_text(text, reply_markup=UIManager.get_device_keyboard(), parse_mode='Markdown')

    async def send_clones_menu(self, update: Update):
        self.config.reload()
        status_map = {}
        for clone in self.config.clones_data:
            name = clone.get("name")
            if name:
                status_map[name] = await MonitorEngine.get_clone_status(name)
        text = UIManager.format_clones_list(self.config.clones_data, status_map)
        self._dashboard_msg = await update.message.reply_text(text, reply_markup=UIManager.get_clones_keyboard(self.config.clones_data), parse_mode='Markdown')

    async def send_system_menu(self, update: Update):
        text = "⚙️ *SYSTEM SETTINGS*"
        await update.message.reply_text(
            text, 
            reply_markup=UIManager.get_system_keyboard(self.console_mode, self.persistence.auto_restore), 
            parse_mode='Markdown'
        )

    async def toggle_console(self, update: Update | None, context: ContextTypes.DEFAULT_TYPE, query=None):
        """Toggle console streaming and persistence."""
        self.console_mode = not self.console_mode
        self.persistence.console_mode = self.console_mode
        
        if self.console_mode:
            chat_id = query.message.chat_id if query else update.effective_chat.id
            self._streamer = LogStreamer(context.bot, chat_id)
            self._log_handler = TelegramLogHandler(self._streamer)
            self._log_handler.setFormatter(logging.Formatter('%(message)s'))
            logging.getLogger().addHandler(self._log_handler)
            asyncio.create_task(self._streamer.start())
            msg = "📟 Консоль-мод: *ВКЛЮЧЕН*"
        else:
            if self._log_handler:
                logging.getLogger().removeHandler(self._log_handler)
                self._log_handler = None
            if self._streamer:
                self._streamer.stop()
                self._streamer = None
            msg = "📟 Консоль-мод: *ВЫКЛЮЧЕН*"
            
        if query:
            # Update the menu
            await query.edit_message_reply_markup(reply_markup=UIManager.get_system_keyboard(self.console_mode, self.persistence.auto_restore))
        else:
            await update.message.reply_text(msg, parse_mode='Markdown')

    async def send_dashboard(self, update: Update):
        """Создает и отправляет новое сообщение дашборда"""
        self.config.reload()
        ram, cpu, temp = await MonitorEngine.get_system_stats()
        
        status_map = {}
        for clone in self.config.clones_data:
            name = clone.get("name")
            if name:
                status_map[name] = await MonitorEngine.get_clone_status(name)
        
        msg_text = UIManager.format_dashboard(
            self.device_id, ram, cpu, temp, self.config.clones_data, status_map
        )
        keyboard = UIManager.get_clone_inline_keyboard(self.config.clones_data, None)
        
        self._dashboard_msg = await update.message.reply_text(
            msg_text, reply_markup=keyboard, parse_mode='Markdown'
        )

    async def update_dashboard(self):
        """Updates the last sent clones menu if it exists."""
        if not self._dashboard_msg:
            return
            
        status_map = {}
        for clone in self.config.clones_data:
            name = clone.get("name")
            if name:
                status_map[name] = await MonitorEngine.get_clone_status(name)
        
        text = UIManager.format_clones_list(self.config.clones_data, status_map)
        keyboard = UIManager.get_clones_keyboard(self.config.clones_data)
        
        try:
            await self._dashboard_msg.edit_text(text, reply_markup=keyboard, parse_mode='Markdown')
        except Exception as e:
            logger.debug(f"Dashboard update skipped: {e}")

    async def sync_git(self, update: Update | None):
        target = update.message if update else None
        if not target and hasattr(update, "message"): target = update.message
        
        reply = await target.reply_text("⏳ AEGIS v2.0: Глобальная синхронизация...") if target else None
        
        # MASTER GIT SYNC: fetch, reset, clean
        cmd = f"cd {FARM_DIR} && git fetch --all && git reset --hard origin/main && git clean -fd"
        ret, stdout, stderr = await run_bash(cmd)
        
        if ret == 0:
            if reply: await reply.edit_text("✅ Sync завершен. Запуск hot-reload...")
            # Trigger restart.sh
            os.system(f"sh {os.path.join(FARM_DIR, 'restart.sh')} {self.device_id} &")
            sys.exit(0)
        else:
            if reply: await reply.edit_text(f"❌ Ошибка Git:\n{stderr}")

    async def take_screenshot(self, message):
        await run_bash(f"su -c 'screencap -p {SCREENSHOT_PATH}'")
        if os.path.exists(SCREENSHOT_PATH):
            with open(SCREENSHOT_PATH, 'rb') as f:
                await message.reply_photo(photo=f, caption=f"📸 {self.device_id}")
            os.remove(SCREENSHOT_PATH)
        else:
            await message.reply_text("❌ Ошибка: Скриншот не создан. Выдан ли root?")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not await self._check_admin(query.from_user.id): return
        data = query.data
        await query.answer()

        try:
            # Navigation
            if data == "nav_home":
                await query.message.reply_text(UIManager.get_welcome_text(self.device_id), reply_markup=UIManager.get_main_keyboard(), parse_mode='Markdown')
            elif data == "nav_clones":
                await self.send_clones_menu(query)
            
            # System Controls
            elif data == "toggle_console":
                await self.toggle_console(None, context, query)
            elif data == "toggle_restore":
                self.persistence.auto_restore = not self.persistence.auto_restore
                await query.edit_message_reply_markup(reply_markup=UIManager.get_system_keyboard(self.console_mode, self.persistence.auto_restore))
            elif data == "sys_sync":
                await self.sync_git(query)
            elif data == "sys_screenshot":
                await self.take_screenshot(query.message)
            elif data == "sys_help":
                await query.edit_message_text(UIManager.get_help_page(1), reply_markup=UIManager.get_help_keyboard(1), parse_mode='Markdown')
            elif data.startswith("help_page_"):
                p = int(data.replace("help_page_", ""))
                await query.edit_message_text(UIManager.get_help_page(p), reply_markup=UIManager.get_help_keyboard(p), parse_mode='Markdown')
            
            # Clone Management
            elif data.startswith("clone_menu_"):
                name = data.replace("clone_menu_", "")
                await query.edit_message_text(f"🎮 *Управление клоном:* `{name.upper()}`", reply_markup=UIManager.get_single_clone_keyboard(name), parse_mode='Markdown')
            
            elif data.startswith("start_"):
                clone_name = data.replace("start_", "")
                clone_info = self.config.get_clone(clone_name)
                if not clone_info or not clone_info.get("cookie"):
                    await context.bot.send_message(chat_id=query.message.chat_id, text=f"❌ Ошибка: Конфиг для {clone_name} не найден.")
                    return

                self.persistence.add_target(clone_name)
                clones_list = [c.get("name") for c in self.config.clones_data]
                try:
                    idx = clones_list.index(clone_name)
                except ValueError:
                    idx = 0
                
                servers_list = self.config.servers_list
                url = servers_list[idx] if idx < len(servers_list) else (servers_list[0] if servers_list else None)
                
                self.active_clones.add(clone_name)
                status_msg = await context.bot.send_message(
                    chat_id=query.message.chat_id, 
                    text=f"🎮 Запуск {clone_name}..."
                )
                asyncio.create_task(self._run_injection(clone_name, clone_info, url, status_msg))

            elif data.startswith("stop_"):
                clone_name = data.replace("stop_", "")
                self.active_clones.discard(clone_name)
                await InjectionEngine.stop(clone_name)
                await context.bot.send_message(chat_id=query.message.chat_id, text=f"✅ {clone_name} остановлен.")
                await self.update_dashboard()

            elif data.startswith("clean_"):
                clone_name = data.replace("clean_", "")
                self.active_clones.discard(clone_name)
                await InjectionEngine.clean(clone_name)
                await context.bot.send_message(chat_id=query.message.chat_id, text=f"✅ Кэш {clone_name} очищен.")
                await self.update_dashboard()
                
        except Exception as e:
            logger.error(f"Callback Exception: {e}", exc_info=True)
            await context.bot.send_message(chat_id=query.message.chat_id, text=f"❌ КРИТИЧЕСКАЯ ОШИБКА PYTHON: {e}")


    async def _run_injection(self, clone_name, clone_info, server_url, status_msg):
        success = await InjectionEngine.inject_and_launch(
            clone_name, 
            clone_info.get("cookie"), 
            server_url, 
            status_msg
        )
        if not success:
            self.active_clones.discard(clone_name)
        await self.update_dashboard()

    async def watchdog_task(self):
        """Smart Watchdog 2.0: 20s validation, Anti-Loop (3 fails), Auto-Cleanup."""
        fail_counts = {}
        last_cleanup = 0.0
        
        while True:
            await asyncio.sleep(60)
            try:
                self.config.reload()
                ram_val, _, _ = await MonitorEngine.get_system_stats()
                
                # RAM AUTO-CLEANUP (>90% or 30 mins)
                now = time.time()
                try: ram_pct = float(ram_val.replace('%',''))
                except: ram_pct = 0
                
                if ram_pct > 90 or (now - last_cleanup) > 1800:
                    logger.info(f"🧹 High RAM ({ram_val}) or 30m timeout: Dropping caches...")
                    await run_bash("su -c 'sync; echo 3 > /proc/sys/vm/drop_caches'")
                    await run_bash("su -c 'logcat -c'") # Clear logs
                    last_cleanup = now

                clones_list = [c.get("name") for c in self.config.clones_data]
                servers_list = self.config.servers_list

                for name in list(self.active_clones):
                    status = await MonitorEngine.get_clone_status(name)
                    
                    if status == "Offline":
                        # SMART VALIDATION: Wait 20s and check again
                        logger.warning(f"Watchdog: {name} might be dead. Double-checking in 20s...")
                        await asyncio.sleep(20)
                        status_retry = await MonitorEngine.get_clone_status(name)
                        
                        if status_retry == "Offline":
                            # ANTI-LOOP: Track fails
                            fail_counts[name] = fail_counts.get(name, 0) + 1
                            if fail_counts[name] > 3:
                                logger.error(f"Watchdog: {name} failed 3 times. Stopping to prevent loop.")
                                self.active_clones.discard(name)
                                for admin_id in self.config.admin_ids:
                                    try: await self.application.bot.send_message(chat_id=admin_id, text=f"⚠️ ERROR: {name} упал 3 раза подряд. Остановлен.")
                                    except: pass
                                continue

                            logger.warning(f"Watchdog: {name} is DEAD. Restarting ({fail_counts[name]}/3)...")
                            clone_info = self.config.get_clone(name)
                            if clone_info and clone_info.get("cookie"):
                                try: idx = clones_list.index(name)
                                except: idx = 0
                                url = servers_list[idx] if len(servers_list) > idx else (servers_list[0] if servers_list else None)
                                await InjectionEngine.inject_and_launch(name, clone_info.get("cookie"), url, None)
                        else:
                            logger.info(f"Watchdog: {name} recovered by itself.")
                    else:
                        fail_counts[name] = 0 # Reset fails on success
                
                if self._dashboard_msg: await self.update_dashboard()

            except Exception as e:
                logger.error(f"Watchdog error: {e}")

    def run(self):
        if not self.config.bot_token:
            logger.error(f"Bot token missing. Check {self.config.bot_token_file}")
            return
            
        self.application = ApplicationBuilder().token(self.config.bot_token).build()
        self.application.add_handler(CommandHandler("start", self.start_cmd))
        self.application.add_handler(CommandHandler("console", self.toggle_console))
        self.application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_text))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Start Watchdog Task
        loop = asyncio.get_event_loop()
        loop.create_task(self.watchdog_task())
        
        # Run Sanity Check on startup
        loop.create_task(self.sanity_check())
        
        logger.info(f"PROJECT AEGIS V2.0 started for {self.device_id}")
        
        # run_polling allows dropping pending updates, useful for preventing 'terminated by other getUpdates'
        self.application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    try:
        AegisNebulaBot().run()
    except Exception as e:
        logger.critical(f"Fatal crash: {e}")
