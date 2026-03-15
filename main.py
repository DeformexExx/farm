# -*- coding: utf-8 -*-
import os
import sys

# AEGIS V3.0 ARCHITECTURE
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

VERSION = "3.0"

# IDENTITY
if len(sys.argv) < 2:
    print("❌ Укажите DEVICE_ID. Пример: python main.py DEV_2")
    sys.exit(1)

DEVICE_ID = sys.argv[1]
FARM_DIR = os.path.join(os.path.expanduser("~"), "farm")
if not os.path.exists(FARM_DIR):
    FARM_DIR = script_dir 

SCREENSHOT_PATH = "/data/local/tmp/s.png"

# Logger
logging.basicConfig(level=logging.INFO, format=f'%(asctime)s [{DEVICE_ID}] [%(levelname)s] %(message)s')
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
    def stop(self): self._is_running = False
    async def _send(self, text):
        try:
            for i in range(0, len(text), 3900):
                chunk = text[i:i+3900]
                full_msg = f"<code>┌─── 🖥 CONSOLE ───┐\n{chunk}\n└──────────────────┘</code>"
                await self.bot.send_message(chat_id=self.chat_id, text=full_msg, parse_mode='HTML')
        except: pass

class AegisNebulaBot:
    def __init__(self):
        self.device_id = DEVICE_ID
        self.config = ConfigManager(self.device_id, FARM_DIR)
        self.persistence = PersistenceManager(FARM_DIR)
        self.application = None
        # SAFE ACCESS V3.0
        p_targets = getattr(self.persistence, 'targets', {})
        self.active_clones = set(p_targets.keys()) if (self.persistence.auto_restore and isinstance(p_targets, dict)) else set()
        self._dashboard_msg = None
        self.console_mode = self.persistence.console_mode
        self._log_handler = None
        self._streamer = None

    async def _check_admin(self, user_id: int) -> bool:
        return user_id in self.config.admin_ids

    async def start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin(update.effective_user.id): return
        await update.message.reply_text(UIManager.get_welcome_text(self.device_id), reply_markup=UIManager.get_main_keyboard(), parse_mode='Markdown')

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin(update.effective_user.id): return
        text = update.message.text
        if text == "📱 DEVICE": await self.send_device_menu(update)
        elif text == "🤖 CLONES": await self.send_clones_menu(update)
        elif text == "⚙️ SYSTEM": await self.send_system_menu(update)

    async def send_device_menu(self, update: Update):
        ram, cpu, temp = await MonitorEngine.get_system_stats()
        await update.message.reply_text(UIManager.format_dashboard(self.device_id, ram, cpu, temp), reply_markup=UIManager.get_device_keyboard(), parse_mode='Markdown')

    async def send_clones_menu(self, update: Update):
        try:
            self.config.reload()
            status_map = {}
            for clone in self.config.clones_data:
                name = clone.get("name")
                if name: status_map[name] = await MonitorEngine.get_clone_status(name)
            targets = getattr(self.persistence, 'targets', {})
            text = UIManager.format_clones_hub(self.config.clones_data, status_map, targets)
            self._dashboard_msg = await update.message.reply_text(text, reply_markup=UIManager.get_clones_hub_keyboard(self.config.clones_data), parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Hub Render Error: {e}")
            await update.message.reply_text(f"❌ Критическая ошибка: {e}")

    async def update_dashboard(self):
        if not self._dashboard_msg: return
        try:
            status_map = {}
            for clone in self.config.clones_data: status_map[clone.get("name")] = await MonitorEngine.get_clone_status(clone.get("name"))
            text = UIManager.format_clones_hub(self.config.clones_data, status_map, getattr(self.persistence, 'targets', {}))
            await self._dashboard_msg.edit_text(text, reply_markup=UIManager.get_clones_hub_keyboard(self.config.clones_data), parse_mode='Markdown')
        except: pass

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not await self._check_admin(query.from_user.id): return
        data = query.data
        await query.answer()
        try:
            if data == "nav_home": await query.message.reply_text(UIManager.get_welcome_text(self.device_id), reply_markup=UIManager.get_main_keyboard(), parse_mode='Markdown')
            elif data == "toggle_restore": self.persistence.auto_restore = not self.persistence.auto_restore; await self.send_system_menu(query)
            elif data == "mass_start": await self.mass_start(query.message.chat_id)
            elif data == "mass_stop": await self.mass_stop(query.message.chat_id)
            elif data.startswith("start_"): await self._start_clone_logic(data.replace("start_", ""), query.message.chat_id)
            elif data.startswith("stop_"): await self._stop_clone_logic(data.replace("stop_", ""), query.message.chat_id)
        except Exception as e: await context.bot.send_message(chat_id=query.message.chat_id, text=f"❌ Callback ERR: {e}")

    async def mass_start(self, chat_id):
        await self.application.bot.send_message(chat_id=chat_id, text=f"🚀 Запуск {len(self.config.clones_data)} клонов...")
        for c in self.config.clones_data: await self._start_clone_logic(c.get("name"), chat_id)

    async def mass_stop(self, chat_id):
        for c in self.config.clones_data: await self._stop_clone_logic(c.get("name"), chat_id)

    async def _start_clone_logic(self, name, chat_id):
        cl_info = self.config.get_clone(name)
        if not cl_info: return
        self.persistence.add_target(name)
        self.active_clones.add(name)
        status_msg = None
        if chat_id and self.application:
            status_msg = await self.application.bot.send_message(chat_id=chat_id, text=f"⏳ [{name}] Запуск...")
        await InjectionEngine.inject_and_launch(name, cl_info.get("cookie"), None, status_msg)
        await asyncio.sleep(10)
        urls = self.config.servers_list
        await InjectionEngine.inject_and_launch(name, cl_info.get("cookie"), urls[0] if urls else None, status_msg)
        await self.update_dashboard()

    async def _stop_clone_logic(self, name, chat_id):
        self.persistence.remove_target(name)
        self.active_clones.discard(name)
        await InjectionEngine.stop(name)
        if chat_id and self.application: await self.application.bot.send_message(chat_id=chat_id, text=f"✅ {name} остановлен.")
        await self.update_dashboard()

    async def watchdog_task(self):
        while True:
            await asyncio.sleep(60)
            if not self.application: continue
            try:
                for name in list(self.active_clones):
                    st = await MonitorEngine.get_clone_status(name)
                    if "Offline" in st or ("Thr:" in st and int(st.split("Thr:")[1].split("|")[0].strip()) < 130):
                        logger.warning(f"Watchdog: {name} stuck. Restarting...")
                        # Notify Admin
                        admin_id = self.config.admin_ids[0] if self.config.admin_ids else None
                        if admin_id: await self.application.bot.send_message(chat_id=admin_id, text=f"🐕 Watchdog: {name} завис. Перезапуск...")
                        await self._start_clone_logic(name, 0)
                await self.update_dashboard()
            except Exception as e: logger.error(f"Watchdog error: {e}")

    async def setup_and_run(self):
        await run_bash(f"su -c 'pgrep python | grep -v {os.getpid()} | xargs kill -9' 2>/dev/null")
        self.application = ApplicationBuilder().token(self.config.bot_token).build()
        self.application.add_handler(CommandHandler("start", self.start_cmd))
        self.application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_text))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        await self.application.initialize()
        await self.application.start()
        asyncio.create_task(self.watchdog_task())
        logger.info(f"💎 PROJECT AEGIS V{VERSION} ONLINE")
        await self.application.updater.start_polling(drop_pending_updates=True)
        while True: await asyncio.sleep(3600)

    async def send_system_menu(self, update_or_query):
        text = "⚙️ *SYSTEM SETTINGS*"
        kb = UIManager.get_system_keyboard(self.console_mode, self.persistence.auto_restore)
        if hasattr(update_or_query, "edit_message_reply_markup"): await update_or_query.edit_message_reply_markup(reply_markup=kb)
        else: await update_or_query.message.reply_text(text, reply_markup=kb, parse_mode='Markdown')

if __name__ == "__main__":
    try: asyncio.run(AegisNebulaBot().setup_and_run())
    except: pass
