# -*- coding: utf-8 -*-
import os
import sys

# AEGIS V3.0: Absolute Path Lock
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.getcwd())

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

# GLOBAL VERSION - HARDCODED
VERSION = "3.0"

# IDENTITY
if len(sys.argv) < 2:
    print("❌ Укажите DEVICE_ID. Пример: python main.py DEV_2")
    sys.exit(1)

DEVICE_ID = sys.argv[1]
FARM_DIR = os.getcwd() 

# Logger
logging.basicConfig(level=logging.INFO, format=f'%(asctime)s [{DEVICE_ID}] [%(levelname)s] %(message)s')
logger = logging.getLogger(f"AegisV30")

class TelegramLogHandler(logging.Handler):
    def __init__(self, streamer):
        super().__init__()
        self.streamer = streamer
    def emit(self, record):
        self.streamer.add_log(f"[{record.levelname[:3].upper()}] {self.format(record)}")

class LogStreamer:
    def __init__(self, bot, chat_id):
        self.bot = bot
        self.chat_id = chat_id
        self.buffer = []
        self._is_running = False
    def add_log(self, text): self.buffer.append(text)
    async def start(self):
        self._is_running = True
        while self._is_running:
            await asyncio.sleep(2)
            if self.buffer:
                msg = "\n".join(self.buffer[-10:])
                self.buffer = []
                try: await self.bot.send_message(self.chat_id, f"<code>{msg}</code>", parse_mode='HTML')
                except: pass
    def stop(self): self._is_running = False

class AegisNebulaBot:
    def __init__(self):
        self.device_id = DEVICE_ID
        self.config = ConfigManager(self.device_id, FARM_DIR)
        self.persistence = PersistenceManager(FARM_DIR)
        self.application = None
        # SAFE INIT V3.0
        t = getattr(self.persistence, 'targets', {})
        self.active_clones = set(t.keys()) if self.persistence.auto_restore and isinstance(t, dict) else set()
        self._dashboard_msg = None
        self.console_mode = self.persistence.console_mode

    async def _check_admin(self, user_id: int) -> bool:
        return user_id in self.config.admin_ids

    async def start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin(update.effective_user.id): return
        await update.message.reply_text(UIManager.get_welcome_text(self.device_id), reply_markup=UIManager.get_main_keyboard(), parse_mode='Markdown')

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin(update.effective_user.id): return
        t = update.message.text
        if t == "📱 DEVICE": 
            ram, cpu, temp = await MonitorEngine.get_system_stats()
            await update.message.reply_text(UIManager.format_dashboard(self.device_id, ram, cpu, temp), reply_markup=UIManager.get_device_keyboard(), parse_mode='Markdown')
        elif t == "🤖 CLONES":
            await self.send_clones_menu(update)
        elif t == "⚙️ SYSTEM":
            await update.message.reply_text("⚙️ SYSTEM", reply_markup=UIManager.get_system_keyboard(self.console_mode, self.persistence.auto_restore), parse_mode='Markdown')

    async def send_clones_menu(self, update: Update):
        try:
            self.config.reload()
            status_map = {}
            for c in self.config.clones_data: status_map[c.get("name")] = await MonitorEngine.get_clone_status(c.get("name"))
            
            # SAFE GETATTR AT LINE 162
            targets = getattr(self.persistence, 'targets', {})
            
            text = UIManager.format_clones_hub(self.config.clones_data, status_map, targets)
            self._dashboard_msg = await update.message.reply_text(text, reply_markup=UIManager.get_clones_hub_keyboard(self.config.clones_data), parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Hub Err: {e}")
            await update.message.reply_text(f"❌ Ошибка меню: {e}")

    async def update_dashboard(self):
        if not self._dashboard_msg: return
        try:
            status_map = {}
            for c in self.config.clones_data: status_map[c.get("name")] = await MonitorEngine.get_clone_status(c.get("name"))
            text = UIManager.format_clones_hub(self.config.clones_data, status_map, getattr(self.persistence, 'targets', {}))
            await self._dashboard_msg.edit_text(text, reply_markup=UIManager.get_clones_hub_keyboard(self.config.clones_data), parse_mode='Markdown')
        except: pass

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        if not await self._check_admin(q.from_user.id): return
        await q.answer()
        d = q.data
        try:
            if d == "nav_home": await q.message.reply_text(UIManager.get_welcome_text(self.device_id), reply_markup=UIManager.get_main_keyboard(), parse_mode='Markdown')
            elif d == "toggle_restore": self.persistence.auto_restore = not self.persistence.auto_restore; await q.edit_message_reply_markup(UIManager.get_system_keyboard(self.console_mode, self.persistence.auto_restore))
            elif d == "mass_start":
                await context.bot.send_message(q.message.chat_id, "🚀 Запуск всех...")
                for c in self.config.clones_data: await self._start_clone(c.get("name"), q.message.chat_id)
            elif d == "mass_stop":
                for c in self.config.clones_data: await self._stop_clone(c.get("name"), q.message.chat_id)
            elif d.startswith("start_"): await self._start_clone(d.replace("start_", ""), q.message.chat_id)
            elif d.startswith("stop_"): await self._stop_clone(d.replace("stop_", ""), q.message.chat_id)
        except Exception as e: logger.error(f"CB Err: {e}")

    async def _start_clone(self, name, chat_id):
        ci = self.config.get_clone(name)
        if not ci: return
        self.persistence.add_target(name)
        self.active_clones.add(name)
        sm = await self.application.bot.send_message(chat_id, f"⏳ [{name}] Launch...")
        await InjectionEngine.inject_and_launch(name, ci.get("cookie"), None, sm)
        await asyncio.sleep(10)
        urls = self.config.servers_list
        await InjectionEngine.inject_and_launch(name, ci.get("cookie"), urls[0] if urls else None, sm)
        await self.update_dashboard()

    async def _stop_clone(self, name, chat_id):
        self.persistence.remove_target(name)
        self.active_clones.discard(name)
        await InjectionEngine.stop(name)
        await self.application.bot.send_message(chat_id, f"✅ {name} Stopped.")
        await self.update_dashboard()

    async def watchdog_task(self):
        while True:
            await asyncio.sleep(60)
            if not self.application: continue
            try:
                for n in list(self.active_clones):
                    st = await MonitorEngine.get_clone_status(n)
                    if "Offline" in st or ("Thr:" in st and int(st.split("Thr:")[1].split("|")[0].strip()) < 130):
                        logger.warning(f"Watchdog: {n} restarting...")
                        aid = self.config.admin_ids[0] if self.config.admin_ids else None
                        if aid: await self.application.bot.send_message(aid, f"🐕 Watchdog: {n} завис. Перезапуск...")
                        await self._start_clone(n, aid)
                await self.update_dashboard()
            except Exception as e: logger.error(f"WD Err: {e}")

    async def setup_and_run(self):
        # 1. HARD PKILL
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

if __name__ == "__main__":
    try: asyncio.run(AegisNebulaBot().setup_and_run())
    except: pass
