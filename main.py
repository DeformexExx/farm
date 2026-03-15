# -*- coding: utf-8 -*-
import os
import sys
import asyncio
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

from config_manager import ConfigManager
from ui_manager import UIManager
from monitor import MonitorEngine
from injection_engine import InjectionEngine
from bash_utils import run_bash

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
    """Custom logging handler to send logs to Telegram chat."""
    def __init__(self, bot, chat_id):
        super().__init__()
        self.bot = bot
        self.chat_id = chat_id
        self.loop = asyncio.get_event_loop()

    def emit(self, record):
        log_entry = self.format(record)
        # Check if the event loop is running and we can schedule a task
        if self.loop.is_running():
            self.loop.create_task(self.send_log(log_entry))

    async def send_log(self, text):
        try:
            # Simple chunking if log is too long
            if len(text) > 4000: text = text[:4000] + "..."
            await self.bot.send_message(chat_id=self.chat_id, text=f"<code>{text}</code>", parse_mode='HTML')
        except Exception:
            pass

class AegisNebulaBot:
    def __init__(self):
        self.device_id = DEVICE_ID
        self.config = ConfigManager(self.device_id, FARM_DIR)
        self.application = None
        self.active_clones = set()  # Names of clones intended to be running
        self._dashboard_msg = None
        self.console_mode = False
        self._log_handler = None

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

        if text == "📊 МОНИТОРИНГ":
            await self.send_dashboard(update)
            
        elif text == "🔄 GIT SYNC":
            await self.sync_git(update)

        elif text == "🖼 СКРИНШОТ":
            await self.take_screenshot(update.message)

    async def toggle_console(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Hidden command to toggle console streaming: /console"""
        if not await self._check_admin(update.effective_user.id): return
        
        self.console_mode = not self.console_mode
        state = "ВКЛЮЧЕН" if self.console_mode else "ВЫКЛЮЧЕН"
        
        if self.console_mode:
            self._log_handler = TelegramLogHandler(context.bot, update.effective_chat.id)
            self._log_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
            logging.getLogger().addHandler(self._log_handler)
        else:
            if self._log_handler:
                logging.getLogger().removeHandler(self._log_handler)
                self._log_handler = None
                
        await update.message.reply_text(f"📟 Консоль-мод: <b>{state}</b>", parse_mode='HTML')

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
        """Обновляет существующее сообщение дашборда, если оно есть"""
        if not self._dashboard_msg:
            return
            
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
        
        if self._dashboard_msg:
            try:
                await self._dashboard_msg.edit_text(msg_text, reply_markup=keyboard, parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Failed to update dashboard: {e}")

    async def sync_git(self, update: Update):
        msg = await update.message.reply_text("⏳ Ожидание Git...")
        cmd = f"cd {FARM_DIR} && git fetch --all && git reset --hard origin/main && git clean -fd"
        ret, stdout, stderr = await run_bash(cmd)
        
        if ret == 0:
            self.config.reload()
            await msg.edit_text("✅ Глобальная синхронизация завершена. Все файлы обновлены до последней версии.")
        else:
            await msg.edit_text(f"❌ Ошибка Git:\n{stderr}")

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
            if data.startswith("start_"):
                clone_name = data.replace("start_", "")
                clone_info = self.config.get_clone(clone_name)
                
                if not clone_info or not clone_info.get("cookie"):
                    await context.bot.send_message(chat_id=query.message.chat_id, text=f"❌ Ошибка: Конфиг/Cookie для {clone_name} не найден.")
                    return

                # Index based distribution logic
                clones_list = [c.get("name") for c in self.config.clones_data]
                try:
                    idx = clones_list.index(clone_name)
                except ValueError:
                    idx = 0
                
                # Universal Link Distribution
                servers_list = self.config.servers_list
                if not servers_list:
                    await context.bot.send_message(chat_id=query.message.chat_id, text="⚠️ Ошибка: servers.json пуст!")
                    return

                # Safely get URL by index, fallback to index 0
                url = servers_list[idx] if idx < len(servers_list) else servers_list[0]
                
                # Safe Extraction (Regex)
                import re
                match = re.search(r"code=([a-zA-Z0-9]+)", str(url))
                if not match:
                    await context.bot.send_message(chat_id=query.message.chat_id, text=f"⚠️ Ошибка: Не удалось найти 'code=' в ссылке {url}")
                    return
                
                share_code = match.group(1)
                await context.bot.send_message(chat_id=query.message.chat_id, text=f"🔍 Ссылка обработана, код: {share_code}. Начинаю запуск...")

                self.active_clones.add(clone_name)
                
                # Create a temporary status message for injection logs
                status_msg = await context.bot.send_message(
                    chat_id=query.message.chat_id, 
                    text=f"🎮 Запуск {clone_name} на сервер №{idx+1}..."
                )
                
                # Start Injection
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
        """Фоновый процесс: если активный клон пропал, перезапускает его."""
        while True:
            await asyncio.sleep(60)
            try:
                self.config.reload()
                
                clones_list = [c.get("name") for c in self.config.clones_data]
                servers_list = self.config.servers_list

                # Copy set to avoid size change issues during iteration
                for name in list(self.active_clones):
                    status = await MonitorEngine.get_clone_status(name)
                    
                    if status == "Offline":
                        logger.warning(f"Watchdog: {name} is DEAD. Auto-restarting...")
                        
                        clone_info = self.config.get_clone(name)
                        if clone_info and clone_info.get("cookie"):
                            # Index logic for watchdog too
                            try:
                                idx = clones_list.index(name)
                            except ValueError:
                                idx = 0
                            
                            server_url = servers_list[idx] if len(servers_list) > idx else (servers_list[0] if servers_list else clone_info.get("placeId"))

                            # Notify Admins about the restart
                            for admin_id in self.config.admin_ids:
                                try:
                                    if self.application and self.application.bot:
                                        await self.application.bot.send_message(
                                            chat_id=admin_id,
                                            text=f"⚠️ Watchdog: Процесс '{name}' упал. Перезапуск на сервер №{idx+1}..."
                                        )
                                except Exception: pass
                            
                            # Run Injection (no dedicated status updating message here)
                            await InjectionEngine.inject_and_launch(
                                name, 
                                clone_info.get("cookie"), 
                                server_url, 
                                None
                            )
                
                # Update dashboard silently if running (checks clones stats again)
                if self._dashboard_msg:
                    await self.update_dashboard()

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
        
        logger.info(f"AEGIS NEBULA v20.0 started for {self.device_id}")
        
        # run_polling allows dropping pending updates, useful for preventing 'terminated by other getUpdates'
        self.application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    try:
        AegisNebulaBot().run()
    except Exception as e:
        logger.critical(f"Fatal crash: {e}")
