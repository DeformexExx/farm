# -*- coding: utf-8 -*-
import os
import sys
import json
import asyncio
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# IDENTITY & PATHS
if len(sys.argv) < 2:
    print("❌ Укажите DEVICE_ID. Пример: python main.py DEV_2")
    sys.exit(1)

DEVICE_ID = sys.argv[1]
# Assume we are running in ~/farm, so config is in the same dir
HOME_DIR = os.path.expanduser("~")
FARM_DIR = os.path.join(HOME_DIR, "farm")
if not os.path.exists(FARM_DIR):
    FARM_DIR = os.getcwd() # Fallback

CONFIG_FILE = os.path.join(FARM_DIR, f"{DEVICE_ID}.json")
BOT_TOKEN_FILE = os.path.join(FARM_DIR, "config.json")
SCREENSHOT_PATH = "/data/local/tmp/s.png"

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format=f'%(asctime)s [{DEVICE_ID}] [%(levelname)s] %(message)s'
)
logger = logging.getLogger("AegisV15")

class AegisOverlordV15:
    def __init__(self):
        self.device_id = DEVICE_ID
        self.bot_token = ""
        self.admin_ids = []
        self.clones_data = []
        self.servers = []
        
        self._load_local_config()
        self._load_clones_json()
        self._load_servers_json()

    def _load_servers_json(self):
        servers_file = os.path.join(FARM_DIR, "servers.json")
        if os.path.exists(servers_file):
            try:
                with open(servers_file, "r", encoding="utf-8") as f:
                    self.servers = json.load(f)
                logger.info(f"Loaded {len(self.servers)} servers from {servers_file}")
            except Exception as e:
                logger.error(f"Failed to load servers.json: {e}")
        else:
            logger.warning(f"Servers file not found: {servers_file}")

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
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self.clones_data = json.load(f)
                logger.info(f"Loaded {len(self.clones_data)} clones from {CONFIG_FILE}")
            except Exception as e:
                logger.error(f"Failed to parse JSON: {e}")
        else:
            logger.warning(f"Config file not found: {CONFIG_FILE}")
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
            f"👑 *AEGIS OVERLORD v15: ULTIMATE FLEET CONTROL*\nУстройство: `{self.device_id}`",
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
        ram, temp, cpu = "N/A", "N/A", "N/A"
        try:
            import psutil
            mem = psutil.virtual_memory()
            ram = f"{mem.percent}%"
            cpu = f"{psutil.cpu_percent()}%"
        except: pass
            
        try:
            paths = ["/sys/class/thermal/thermal_zone0/temp", "/sys/class/thermal/thermal_zone1/temp"]
            for path in paths:
                if os.path.exists(path):
                    with open(path, "r") as f:
                        temp = f"{int(int(f.read()) / 1000)}°C"
                    break
        except: pass
        return ram, cpu, temp

    async def run_bash(self, cmd):
        process = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        return process.returncode, stdout.decode().strip(), stderr.decode().strip()

    async def send_status_report(self, update: Update):
        self._load_clones_json()
        ram, cpu, temp = await self.get_system_stats()
        
        msg = f"📱 Device: `{self.device_id}`\n🧠 RAM: {ram} | 🚀 CPU: {cpu} | 🌡 Temp: {temp}"
        
        keyboard = []
        for clone in self.clones_data:
            name = clone.get("name", "Unknown")
            # 3 buttons per row natively per user request
            row = [
                InlineKeyboardButton(f"▶️ Start {name}", callback_data=f"start_clone_{name}"),
                InlineKeyboardButton(f"⏹ Stop {name}", callback_data=f"stop_clone_{name}"),
                InlineKeyboardButton(f"🧹 Clean {name}", callback_data=f"clear_cache_{name}")
            ]
            keyboard.append(row)

        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def sync_git(self, update: Update):
        msg = await update.message.reply_text("⏳ Ожидание Git...")
        cmd = f"cd {FARM_DIR} && git reset --hard origin/main && git pull"
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
        else:
            await message.reply_text("❌ Ошибка: Скриншот не создан. Выдан ли root?")

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
            
            clone_info = next((c for c in self.clones_data if c.get("name") == clone_name), None)
            if not clone_info or not clone_info.get("cookie"):
                await context.bot.send_message(chat_id=query.message.chat_id, text=f"❌ Ошибка: Cookie для {clone_name} не найден.")
                return

            asyncio.create_task(self.holy_grail_injection(
                query.message.chat_id, 
                context.bot, 
                clone_name, 
                clone_info.get("cookie"),
                clone_info.get("placeId")
            ))

        elif data.startswith("stop_clone_"):
            clone_name = data.replace("stop_clone_", "")
            await self.run_bash(f"su -c 'am force-stop com.roblox.{clone_name}'")
            await context.bot.send_message(chat_id=query.message.chat_id, text=f"✅ {clone_name} остановлен.")

        elif data.startswith("clear_cache_"):
            clone_name = data.replace("clear_cache_", "")
            await self.run_bash(f"su -c 'am force-stop com.roblox.{clone_name}'")
            await self.run_bash(f"su -c 'rm -rf /data/data/com.roblox.{clone_name}/cache/*'")
            await context.bot.send_message(chat_id=query.message.chat_id, text=f"✅ Кэш {clone_name} очищен.")

    async def holy_grail_injection(self, chat_id, bot, clone_name, cookie, place_id=None):
        """The strictly ordered, pure-bash injection mechanism."""
        status_msg = await bot.send_message(chat_id=chat_id, text=f"⏳ Holy Grail Injection: `{clone_name}`...", parse_mode='Markdown')
        
        try:
            # 1. Force Stop
            await self.run_bash(f"su -c 'am force-stop com.roblox.{clone_name}'")
            await asyncio.sleep(1)

            # 2. SQLite Injection
            db_path = f"/data/data/com.roblox.{clone_name}/app_webview/Default/Cookies"
            
            # The exact SQL specified
            sql_del = "DELETE FROM cookies WHERE host_key LIKE '%roblox.com%';"
            sql_ins = f"INSERT INTO cookies (host_key, name, value, path, expires_utc, is_secure, is_httponly, has_expires, is_persistent, samesite, source_port) VALUES ('.roblox.com', '.ROBLOSECURITY', '{cookie}', '/', 253402300799000000, 1, 1, 1, 1, -1, -1);"
            
            inj_cmd = f"su -c \"sqlite3 {db_path} \\\"{sql_del} {sql_ins}\\\"\""
            ret, stdout, stderr = await self.run_bash(inj_cmd)
            
            if ret != 0:
                await status_msg.edit_text(f"❌ SQLite Ошибка ({clone_name}):\n{stderr}")
                return

            # 3. Permissions Fix (CRITICAL)
            chown_cmd = f"su -c \"chown \\$(stat -c %u:%g /data/data/com.roblox.{clone_name}) /data/data/com.roblox.{clone_name}/app_webview/Default/Cookies\""
            ret, stdout, stderr = await self.run_bash(chown_cmd)
            
            if ret != 0:
                if "Permission denied" in stderr or "not found" in stderr:
                    await status_msg.edit_text(f"❌ Root Error ({clone_name}): Устройство без Root или tsu не установлен.\n{stderr}")
                else:
                    await status_msg.edit_text(f"❌ Chown Ошибка ({clone_name}):\n{stderr}")
                return

            # 4. Launch (Monkey / Intent)
            await self.run_bash(f"su -c 'monkey -p com.roblox.{clone_name} -c android.intent.category.LAUNCHER 1'")
            
            # 5. Server Entry Logic
            if self.servers:
                import random
                server_url = random.choice(self.servers)
                await asyncio.sleep(8) # Wait for initial app load (increased slightly for stability)
                join_cmd = f"su -c 'am start -a android.intent.action.VIEW -d \"{server_url}\" com.roblox.{clone_name}'"
                await self.run_bash(join_cmd)
                await status_msg.edit_text(f"✅ `{clone_name}` подключен к серверу из пула (servers.json).", parse_mode='Markdown')
            elif place_id:
                await asyncio.sleep(8) # Wait for initial app load
                join_cmd = f"su -c 'am start -a android.intent.action.VIEW -d \"roblox://placeId={place_id}\" com.roblox.{clone_name}'"
                await self.run_bash(join_cmd)
                await status_msg.edit_text(f"✅ `{clone_name}` подключен к серверу (PlaceId: {place_id}).", parse_mode='Markdown')
            else:
                await status_msg.edit_text(f"✅ `{clone_name}` запущен (Главное меню).", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Launch Sequence Error for {clone_name}: {e}")
            await status_msg.edit_text(f"❌ Критическая ошибка ({clone_name}): {e}")

    async def watchdog_task(self):
        """Monitors clones in 'Enabled' state. If process is dead, auto-restart."""
        while True:
            await asyncio.sleep(120)  # Wait 2 minutes
            try:
                self._load_clones_json()
                for clone in self.clones_data:
                    status = clone.get("status", "").lower()
                    
                    if "enabled" in status or "online" in status:
                        name = clone.get("name")
                        
                        # Check process
                        ret, stdout, _ = await self.run_bash(f"su -c 'pidof com.roblox.{name}'")
                        
                        # Process is dead
                        if ret != 0 or not stdout.strip():
                            logger.warning(f"Watchdog: {name} is DEAD. Auto-restarting...")
                            
                            # Grab cookie and placeId
                            cookie = clone.get("cookie")
                            place_id = clone.get("placeId")
                            
                            if cookie and getattr(self, "application", None):
                                # Notify Admins
                                for admin_id in self.admin_ids:
                                    try:
                                        await self.application.bot.send_message(
                                            chat_id=admin_id,
                                            text=f"⚠️ Watchdog: Процесс '{name}' не найден. Выполняю авторестарт..."
                                        )
                                    except: pass
                                
                                # Launch
                                await self.holy_grail_injection(
                                    self.admin_ids[0] if self.admin_ids else 0, # Send status to primary admin
                                    self.application.bot,
                                    name,
                                    cookie,
                                    place_id
                                )
            except Exception as e:
                logger.error(f"Watchdog error: {e}")

    def run(self):
        if not self.bot_token:
            logger.error(f"Bot token missing. Check {BOT_TOKEN_FILE}")
            return
            
        self.application = ApplicationBuilder().token(self.bot_token).build()
        self.application.add_handler(CommandHandler("start", self.start_cmd))
        self.application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_text))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Start Watchdog Task
        loop = asyncio.get_event_loop()
        loop.create_task(self.watchdog_task())
        
        logger.info(f"Aegis Overlord v15: Ultimate Fleet Control started for {self.device_id}")
        self.application.run_polling()

if __name__ == "__main__":
    AegisOverlordV15().run()
