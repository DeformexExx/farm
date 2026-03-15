# -*- coding: utf-8 -*-
import os
import sys
import json
import asyncio
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# DEVICE INIT
DEVICE_ID = sys.argv[1] if len(sys.argv) > 1 else "DEV_MASTER"
CONFIG_FILE = f"{DEVICE_ID}.json"
BOT_TOKEN_FILE = "config.json"
SCREENSHOT_PATH = "/data/local/tmp/s.png"

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format=f'%(asctime)s [{DEVICE_ID}] [%(levelname)s] %(message)s'
)
logger = logging.getLogger("AegisV13")

class AegisOverlordV13:
    def __init__(self):
        self.device_id = DEVICE_ID
        self.config_path = CONFIG_FILE
        self.bot_token = ""
        self.admin_ids = []
        self.clones_data = []
        
        self._load_local_config()
        self._load_clones_json()

    def _load_local_config(self):
        if os.path.exists(BOT_TOKEN_FILE):
            try:
                with open(BOT_TOKEN_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.bot_token = data.get("bot_token", "")
                    self.admin_ids = data.get("admin_ids", [])
            except Exception as e:
                logger.error(f"Failed to load bot config: {e}")

    def _load_clones_json(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.clones_data = json.load(f)
                logger.info(f"Loaded {len(self.clones_data)} clones from {self.config_path}")
            except Exception as e:
                logger.error(f"Failed to load JSON: {e}")
                self.clones_data = []
        else:
            logger.warning(f"Config file not found: {self.config_path}")
            self.clones_data = []

    def get_main_keyboard(self):
        keyboard = [
            [KeyboardButton("📊 Статус фермы"), KeyboardButton("🔄 Синхронизация с Git")],
            [KeyboardButton("🖼 Скриншот"), KeyboardButton("🛑 Стоп ВСЕ")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    async def start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in self.admin_ids: return
        await update.message.reply_text(
            f"👑 *AEGIS OVERLORD v13: MASTERPIECE EDITION*\nУстройство: `{self.device_id}`",
            reply_markup=self.get_main_keyboard(),
            parse_mode='Markdown'
        )

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in self.admin_ids: return
        text = update.message.text

        if text == "📊 Статус фермы":
            await self.send_status_report(update)
            
        elif text == "🔄 Синхронизация с Git":
            await self.sync_git(update)

        elif text == "🖼 Скриншот":
            await self.take_screenshot(update.message)

        elif text == "🛑 Стоп ВСЕ":
            await self.stop_all(update)

    async def get_system_stats(self):
        ram = "N/A"
        temp = "N/A"
        try:
            import psutil
            mem = psutil.virtual_memory()
            ram = f"{mem.percent}%"
        except: pass
            
        try:
            paths = ["/sys/class/thermal/thermal_zone0/temp", "/sys/class/thermal/thermal_zone1/temp"]
            for path in paths:
                if os.path.exists(path):
                    with open(path, "r") as f:
                        temp = f"{int(int(f.read()) / 1000)}°C"
                    break
        except: pass
        return ram, temp

    async def run_bash(self, cmd):
        process = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        return process.returncode, stdout.decode(), stderr.decode()

    async def send_status_report(self, update: Update):
        self._load_clones_json()
        ram, temp = await self.get_system_stats()
        
        msg = f"📱 Device: `{self.device_id}`\n🧠 RAM: {ram} | 🌡 Temp: {temp}"
        
        keyboard = []
        for clone in self.clones_data:
            name = clone.get("name", "Unknown")
            row = [
                InlineKeyboardButton(f"▶️ Запуск {name}", callback_data=f"start_clone_{name}"),
                InlineKeyboardButton(f"⏹ Стоп {name}", callback_data=f"stop_clone_{name}"),
                InlineKeyboardButton(f"🧹 Кэш {name}", callback_data=f"clear_cache_{name}")
            ]
            keyboard.append(row)

        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def sync_git(self, update: Update):
        msg = await update.message.reply_text("⏳ Ожидание Git...")
        cmd = "cd ~/farm && git reset --hard origin/main && git pull"
        ret, stdout, stderr = await self.run_bash(cmd)
        
        self._load_clones_json()
        
        if ret == 0:
            await msg.edit_text("✅ Конфиги успешно загружены с GitHub. Нажмите [📊 Статус фермы] для обновления меню.")
        else:
            await msg.edit_text(f"❌ Ошибка Git:\n{stderr}")

    async def take_screenshot(self, message):
        await self.run_bash(f"su -c 'screencap -p {SCREENSHOT_PATH}'")
        if os.path.exists(SCREENSHOT_PATH):
            with open(SCREENSHOT_PATH, 'rb') as f:
                await message.reply_photo(photo=f, caption=f"📸 {self.device_id}")
            os.remove(SCREENSHOT_PATH)

    async def stop_all(self, update: Update):
        msg = await update.message.reply_text("⏳ Остановка всех клонов...")
        for clone in self.clones_data:
            name = clone.get("name")
            if name:
                await self.run_bash(f"su -c 'am force-stop com.roblox.{name}'")
        await msg.edit_text("✅ Все клоны остановлены.")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if query.from_user.id not in self.admin_ids: return
        data = query.data

        await query.answer()

        if data.startswith("start_clone_"):
            clone_name = data.replace("start_clone_", "")
            
            cookie = next((c.get("cookie") for c in self.clones_data if c.get("name") == clone_name), None)
            if not cookie:
                await context.bot.send_message(chat_id=query.message.chat_id, text=f"❌ Cookie для {clone_name} не найден в {self.config_path}.")
                return

            asyncio.create_task(self.execute_injection_sequence(query.message.chat_id, context.bot, clone_name, cookie))

        elif data.startswith("stop_clone_"):
            clone_name = data.replace("stop_clone_", "")
            await self.run_bash(f"su -c 'am force-stop com.roblox.{clone_name}'")
            await context.bot.send_message(chat_id=query.message.chat_id, text=f"✅ {clone_name} остановлен.")

        elif data.startswith("clear_cache_"):
            clone_name = data.replace("clear_cache_", "")
            await self.run_bash(f"su -c 'am force-stop com.roblox.{clone_name}'")
            await self.run_bash(f"su -c 'rm -rf /data/data/com.roblox.{clone_name}/cache/*'")
            await context.bot.send_message(chat_id=query.message.chat_id, text=f"✅ Кэш {clone_name} очищен.")

    async def execute_injection_sequence(self, chat_id, bot, clone_name, cookie):
        status_msg = await bot.send_message(chat_id=chat_id, text=f"⏳ Инъекция в {clone_name}...")
        
        try:
            # 1. Force Stop
            await self.run_bash(f"su -c 'am force-stop com.roblox.{clone_name}'")
            await asyncio.sleep(1)

            # 2. SQLite Injection
            db_path = f"/data/data/com.roblox.{clone_name}/app_webview/Default/Cookies"
            sql_query = f"DELETE FROM cookies WHERE host_key LIKE '%roblox.com%'; INSERT INTO cookies (host_key, name, value, path, expires_utc, is_secure, is_httponly, has_expires, is_persistent, samesite, source_port) VALUES ('.roblox.com', '.ROBLOSECURITY', '{cookie}', '/', 13333333333333333, 1, 1, 1, 1, -1, -1);"
            
            inj_cmd = f"su -c \"sqlite3 {db_path} \\\"{sql_query}\\\"\""
            await self.run_bash(inj_cmd)

            # 3. Fix Permissions
            chown_cmd = f"su -c \"chown \\$(stat -c %u:%g /data/data/com.roblox.{clone_name}) /data/data/com.roblox.{clone_name}/app_webview/Default/Cookies\""
            await self.run_bash(chown_cmd)

            # 4. Launch the Clone
            launch_cmd = f"su -c \"monkey -p com.roblox.{clone_name} -c android.intent.category.LAUNCHER 1\""
            await self.run_bash(launch_cmd)

            await status_msg.edit_text(f"✅ {clone_name} запущен.")
            
        except Exception as e:
            logger.error(f"Launch Sequence Error for {clone_name}: {e}")
            await status_msg.edit_text(f"❌ Ошибка запуска {clone_name}: {e}")

    def run(self):
        if not self.bot_token:
            logger.error("Bot token missing in config.json")
            return
            
        app = ApplicationBuilder().token(self.bot_token).build()
        app.add_handler(CommandHandler("start", self.start_cmd))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_text))
        app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        logger.info(f"Aegis Overlord v13 Masterpiece started for {self.device_id}")
        app.run_polling()

if __name__ == "__main__":
    AegisOverlordV13().run()
