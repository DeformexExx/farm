# -*- coding: utf-8 -*-
import os
import sys

# AEGIS V3.0: Absolute Path Fix (CRITICAL)
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.getcwd())
script_dir = os.getcwd()

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

# GLOBAL VERSIONING
VERSION = "3.0"

# IDENTITY & PATHS
if len(sys.argv) < 2:
    print("❌ Укажите DEVICE_ID. Пример: python main.py DEV_2")
    sys.exit(1)

DEVICE_ID = sys.argv[1]
FARM_DIR = os.path.join(os.path.expanduser("~"), "farm")
if not os.path.exists(FARM_DIR):
    FARM_DIR = script_dir 

SCREENSHOT_PATH = "/data/local/tmp/s.png"

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format=f'%(asctime)s [{DEVICE_ID}] [%(levelname)s] %(message)s'
)
logger = logging.getLogger(f"AegisV{VERSION.replace('.', '')}")

class TelegramLogHandler(logging.Handler):
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
        header = "┌─── 🖥 CONSOLE ───┐"
        footer = "└──────────────────┘"
        try:
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
        # SAFE ACCESS: Ensure targets exists (V3.0 Critical)
        p_targets = getattr(self.persistence, 'targets', {})
        self.active_clones = set(p_targets.keys()) if (self.persistence.auto_restore and isinstance(p_targets, dict)) else set()
        self._dashboard_msg = None
        self.console_mode = self.persistence.console_mode
        self._log_handler: logging.Handler | None = None
        self._streamer: LogStreamer | None = None

    async def sanity_check(self):
        """Clean slate: stop all clones and ensure no ghost pythons (Delayed for Stability)."""
        logger.info(f"⏳ AEGIS V{VERSION}: Delaying Sanity Check for 30s...")
        await asyncio.sleep(30)
        
        logger.info("⚙️ Performing Sanity Check...")
        for clone in self.config.clones_data:
            name = clone.get("name")
            if name:
                await run_bash(f"su -c 'am force-stop com.roblox.{name}'")
        
        my_pid = os.getpid()
        await run_bash(f"su -c 'pgrep python | grep -v {my_pid} | xargs kill -9' 2>/dev/null")
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
        if text == "📱 DEVICE": await self.send_device_menu(update)
        elif text == "🤖 CLONES": await self.send_clones_menu(update)
        elif text == "⚙️ SYSTEM": await self.send_system_menu(update)

    async def send_device_menu(self, update: Update):
        ram, cpu, temp = await MonitorEngine.get_system_stats()
        text = UIManager.format_dashboard(self.device_id, ram, cpu, temp)
        await update.message.reply_text(text, reply_markup=UIManager.get_device_keyboard(), parse_mode='Markdown')

    async def send_clones_menu(self, update: Update):
        try:
            self.config.reload()
            status_map = {}
            for clone in self.config.clones_data:
                name = clone.get("name")
                if name: status_map[name] = await MonitorEngine.get_clone_status(name)
            
            # SAFE ACCESS: Ensure targets exists (V3.0 Critical - Line 162 fix)
            targets = getattr(self.persistence, 'targets', {})
            
            text = UIManager.format_clones_hub(self.config.clones_data, status_map, targets)
            self._dashboard_msg = await update.message.reply_text(
                text, 
                reply_markup=UIManager.get_clones_hub_keyboard(self.config.clones_data), 
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error rendering Clones Menu: {e}")
            await update.message.reply_text(f"❌ Критическая ошибка меню: {e}")

    async def update_dashboard(self):
        if not self._dashboard_msg: return
        try:
            self.config.reload()
            status_map = {}
            for clone in self.config.clones_data:
                name = clone.get("name")
                if name: status_map[name] = await MonitorEngine.get_clone_status(name)
            
            p_targets = getattr(self.persistence, 'targets', {})
            text = UIManager.format_clones_hub(self.config.clones_data, status_map, p_targets)
            await self._dashboard_msg.edit_text(text, reply_markup=UIManager.get_clones_hub_keyboard(self.config.clones_data), parse_mode='Markdown')
        except Exception as e:
            logger.debug(f"Dashboard update failed: {e}")

    async def toggle_console(self, update: Update | None, context: ContextTypes.DEFAULT_TYPE, query=None):
        self.console_mode = not self.console_mode
        self.persistence.console_mode = self.console_mode
        if self.console_mode:
            chat_id = query.message.chat_id if query else update.effective_chat.id
            self._streamer = LogStreamer(context.bot, chat_id)
            self._log_handler = TelegramLogHandler(self._streamer)
            logging.getLogger().addHandler(self._log_handler)
            asyncio.create_task(self._streamer.start())
            msg = "📟 Консоль-мод: *ВКЛЮЧЕН*"
        else:
            if self._log_handler: logging.getLogger().removeHandler(self._log_handler); self._log_handler = None
            if self._streamer: self._streamer.stop(); self._streamer = None
            msg = "📟 Консоль-мод: *ВЫКЛЮЧЕН*"
        if query: await query.edit_message_reply_markup(reply_markup=UIManager.get_system_keyboard(self.console_mode, self.persistence.auto_restore))
        else: await update.message.reply_text(msg, parse_mode='Markdown')

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not await self._check_admin(query.from_user.id): return
        data = query.data
        await query.answer()
        try:
            if data == "nav_home": await query.message.reply_text(UIManager.get_welcome_text(self.device_id), reply_markup=UIManager.get_main_keyboard(), parse_mode='Markdown')
            elif data == "nav_clones": await self.send_clones_menu(query)
            elif data == "toggle_console": await self.toggle_console(None, context, query)
            elif data == "toggle_restore": self.persistence.auto_restore = not self.persistence.auto_restore; await query.edit_message_reply_markup(reply_markup=UIManager.get_system_keyboard(self.console_mode, self.persistence.auto_restore))
            elif data == "sys_sync": await self.sync_git(query)
            elif data == "sys_screenshot": await self.take_screenshot(query.message)
            elif data == "sys_help": await query.edit_message_text(UIManager.get_help_page(1), reply_markup=UIManager.get_help_keyboard(1), parse_mode='Markdown')
            elif data.startswith("help_page_"): p = int(data.replace("help_page_", "")); await query.edit_message_text(UIManager.get_help_page(p), reply_markup=UIManager.get_help_keyboard(p), parse_mode='Markdown')
            elif data == "mass_start": await self.mass_start(query.message.chat_id, context)
            elif data == "mass_stop": await self.mass_stop(query.message.chat_id, context)
            elif data.startswith("start_"): await self._start_clone_logic(data.replace("start_", ""), query.message.chat_id, context)
            elif data.startswith("stop_"): await self._stop_clone_logic(data.replace("stop_", ""), query.message.chat_id, context)
        except Exception as e:
            logger.error(f"Callback Exception: {e}")
            await context.bot.send_message(chat_id=query.message.chat_id, text=f"❌ ОШИБКА: {e}")

    async def mass_start(self, chat_id, context):
        clones = self.config.clones_data
        await context.bot.send_message(chat_id=chat_id, text=f"🚀 Массовый запуск {len(clones)} клонов (V{VERSION})...")
        await run_bash("su -c 'sync; echo 3 > /proc/sys/vm/drop_caches'")
        for clone in clones:
            name = clone.get("name")
            if name: await self._start_clone_logic(name, chat_id, context)
        await context.bot.send_message(chat_id=chat_id, text="✅ Массовый запуск завершен!")

    async def mass_stop(self, chat_id, context):
        clones = self.config.clones_data
        await context.bot.send_message(chat_id=chat_id, text=f"❄️ Массовая остановка {len(clones)} клонов...")
        for clone in clones:
            name = clone.get("name")
            if name: await self._stop_clone_logic(name, chat_id, context); await asyncio.sleep(1)
        await context.bot.send_message(chat_id=chat_id, text="✅ Массовая остановка завершена!")

    async def _start_clone_logic(self, name, chat_id, context):
        cl_info = self.config.get_clone(name)
        if not cl_info: return
        self.persistence.add_target(name)
        self.active_clones.add(name)
        if chat_id: status_msg = await context.bot.send_message(chat_id=chat_id, text=f"⏳ [{name}] 1/2: Запуск...")
        await InjectionEngine.inject_and_launch(name, cl_info.get("cookie"), None, status_msg)
        await asyncio.sleep(15)
        if status_msg: await status_msg.edit_text(f"⏳ [{name}] 2/2: Вход на сервер...")
        urls = self.config.servers_list
        url = urls[0] if urls else None # Simplified for V3
        await InjectionEngine.inject_and_launch(name, cl_info.get("cookie"), url, status_msg)
        await asyncio.sleep(10)
        await self.update_dashboard()

    async def _stop_clone_logic(self, name, chat_id, context):
        self.persistence.remove_target(name)
        self.active_clones.discard(name)
        await InjectionEngine.stop(name)
        if chat_id: await context.bot.send_message(chat_id=chat_id, text=f"✅ {name} остановлен.")
        await self.update_dashboard()

    async def watchdog_task(self):
        while True:
            await asyncio.sleep(60)
            try:
                for name in list(self.active_clones):
                    st = await MonitorEngine.get_clone_status(name)
                    if "Offline" in st or ( "Thr:" in st and int(st.split("Thr:")[1].split("|")[0].strip()) < 130):
                        logger.warning(f"Watchdog: {name} stuck. Restarting...")
                        await self._start_clone_logic(name, 0, None)
                await self.update_dashboard()
            except Exception as e: logger.error(f"Watchdog error: {e}")

    async def setup_and_run(self):
        if not self.config.bot_token: return
        await run_bash(f"su -c 'pgrep python | grep -v {os.getpid()} | xargs kill -9' 2>/dev/null")
        self.application = ApplicationBuilder().token(self.config.bot_token).build()
        self.application.add_handler(CommandHandler("start", self.start_cmd))
        self.application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_text))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        await self.application.initialize()
        await self.application.start()
        asyncio.create_task(self.watchdog_task())
        asyncio.create_task(self.sanity_check())
        logger.info(f"💎 PROJECT AEGIS V{VERSION} ONLINE")
        await self.application.updater.start_polling(drop_pending_updates=True)
        while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    try: asyncio.run(AegisNebulaBot().setup_and_run())
    except KeyboardInterrupt: pass
    except Exception as e: logger.critical(f"Fatal crash: {e}")
