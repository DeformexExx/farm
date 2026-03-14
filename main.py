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
import logging
import psutil
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# Aegis v7 Overlord Modules
from hardware_monitor import HardwareMonitor
from memory_manager import MemoryManager
from server_engine import ServerEngine
from watchdog_pro import WatchdogPro
from sheet_manager import SheetManager
from cookie_injector import CookieInjector

# Constants
LOG_FILE = "aegis.log"
SCREENSHOT_PATH = "/data/local/tmp/s.png"
CREDS_FILE = "creds.json"
SHEET_NAME = "AegisFarmOS"

# Global Identity Context (v7 Switching)
ACTIVE_DEVICE_ID = sys.argv[1] if len(sys.argv) > 1 else "MASTER"

# Logging pipeline
logging.basicConfig(
    level=logging.INFO,
    format=f'%(asctime)s [{ACTIVE_DEVICE_ID}] [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger("AegisV7")

class AegisOverlordOrchestrator:
    def __init__(self):
        self.device_id = ACTIVE_DEVICE_ID
        self.config = self.load_local_config()
        self.sheet = SheetManager(CREDS_FILE, SHEET_NAME)
        self.injector = CookieInjector(self.safe_print)
        self.clones_data = {} # pkg -> data from sheet
        self.watchdogs = {}
        self.app = None
        self.loop = None
        self.selected_users = {} # user_id -> boolean (is this device selected for this user)
        
        # Persistence for Cookies
        self.cookie_cache = {} # pkg -> last_cookie_value
        
        self.purge_ghosts()

    def load_local_config(self):
        if os.path.exists("config.json"):
            with open("config.json", "r") as f:
                return json.load(f)
        return {"bot_token": "", "admin_ids": []}

    def purge_ghosts(self):
        try:
            curr_pid = os.getpid()
            cmd = f"su -c \"ps -ef | grep main.py | grep -v grep | grep -v {curr_pid} | awk '{{print $2}}' | xargs kill -9\""
            subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"Identity: {self.device_id} | Ghosts purged.")
        except: pass

    def safe_print(self, text):
        prefixed = f"[{self.device_id}] {text}"
        logger.info(text)
        if self.app:
            asyncio.run_coroutine_threadsafe(self.broadcast(prefixed), self.loop)

    async def broadcast(self, text):
        for admin_id in self.config.get("admin_ids", []):
            try: await self.app.bot.send_message(chat_id=admin_id, text=text)
            except: pass

    def get_main_keyboard(self):
        """v7 Overlord UI Grid."""
        keyboard = [
            [KeyboardButton("📊 Мониторинг"), KeyboardButton("🔄 Синхронизация")],
            [KeyboardButton("🖼 Скриншот"), KeyboardButton("🛠 Админка")],
            [KeyboardButton("📱 Выбрать девайс"), KeyboardButton("❓ Помощь")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    async def start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in self.config.get("admin_ids", []): return
        # Auto-select on start if it's the only one or default
        self.selected_users[update.effective_user.id] = True
        await update.message.reply_text(
            f"👑 *Aegis Commander v7: Overlord Interface*\nУстройство: `{self.device_id}`\nСинхронизация: `Google Sheets (Active)`",
            reply_markup=self.get_main_keyboard(),
            parse_mode='Markdown'
        )

    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in self.config.get("admin_ids", []): return
        help_text = (
            "📖 *Справка Aegis Commander v7*\n\n"
            "📊 *Мониторинг* — Полный статус всех клонов устройства с кнопками управления.\n"
            "🔄 *Синхронизация* — Принудительное обновление данных из Google Таблицы.\n"
            "🖼 *Скриншот* — Моментальный снимок экрана устройства.\n"
            "🛠 *Админка* — Системные команды: Очистка RAM, Reboot, Master Re-Inject.\n"
            "📱 *Выбрать девайс* — Переключение контекста между вашими устройствами.\n\n"
            "⌨️ *Консоль*: Отправьте сообщение с символом `$` в начале для выполнения Shell команд.\n"
            "🚀 *Auto-Repair*: Каждый запуск через кнопку автоматически проверяет куки и делает инъекцию."
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in self.config.get("admin_ids", []): return
        text = update.message.text
        
        # Check if selected
        is_selected = self.selected_users.get(user_id, False)

        if text == "📊 Мониторинг":
            if is_selected: await self.send_overlord_report(update)
            
        elif text == "🔄 Синхронизация":
            if is_selected:
                await update.message.reply_text(f"[{self.device_id}] Форсирую синхронизацию с Google Sheets...")
                threading.Thread(target=self.sync_loop_tick).start()

        elif text == "🛠 Админка":
            if is_selected:
                kb = [
                    [InlineKeyboardButton("🧹 Очистка RAM", callback_data="admin_clean")],
                    [InlineKeyboardButton("🚀 Master Re-Inject", callback_data="admin_reinject")],
                    [InlineKeyboardButton("🔄 Reboot Termux", callback_data="admin_reboot")]
                ]
                await update.message.reply_text(f"🛠 [{self.device_id}] Панель управления системой:", reply_markup=InlineKeyboardMarkup(kb))

        elif text == "🖼 Скриншот":
            if is_selected: await self.take_snap(update.message)

        elif text == "📱 Выбрать девайс":
            # All devices respond with a button to select THEM
            kb = [[InlineKeyboardButton(f"✅ Выбрать {self.device_id}", callback_data=f"select_{self.device_id}")]]
            await update.message.reply_text(f"📱 Доступно устройство: `{self.device_id}`", reply_markup=InlineKeyboardMarkup(kb))

        elif text == "❓ Помощь":
            if is_selected: await self.help_cmd(update, context)

        elif text.startswith("$") or text.lower().startswith("shell "):
            cmd = text[1:].strip() if text.startswith("$") else text[6:].strip()
            # Shell is local to selected OR if ID is in command
            if is_selected or self.device_id in cmd:
                await self.execute_shell(update, cmd)

    async def execute_shell(self, update: Update, cmd):
        # Filter for current device or global
        if not (cmd.startswith(self.device_id) or cmd.startswith("FLEET")):
            # If it doesn't specify, we only run if it's the active context
            pass 
        
        real_cmd = cmd.replace(self.device_id, "").replace("FLEET", "").strip()
        try:
            res = subprocess.run(f"su -c '{real_cmd}'", shell=True, capture_output=True, text=True, timeout=30)
            out = (res.stdout + res.stderr).strip() or "[Нет вывода]"
            await update.message.reply_text(f"```bash\n[{self.device_id}]\n{out[:3500]}\n```", parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"[{self.device_id}] Ошибка Shell: {e}")

    async def take_snap(self, message):
        try:
            subprocess.run(f"su -c 'screencap -p {SCREENSHOT_PATH}'", shell=True)
            if os.path.exists(SCREENSHOT_PATH):
                with open(SCREENSHOT_PATH, 'rb') as f:
                    await message.reply_photo(photo=f, caption=f"📸 Снимок: {self.device_id}")
                os.remove(SCREENSHOT_PATH)
        except: pass

    async def send_overlord_report(self, update: Update):
        if not self.clones_data:
            await update.message.reply_text(f"❌ *Ошибка*: Девайс `{self.device_id}` не найден в таблице или нет доступа!", parse_mode='Markdown')
            return

        active_count = 0
        clones_list = []
        keyboard = []
        
        stats = HardwareMonitor.get_dashboard_report(self.device_id, "")
        
        for pkg, data in self.clones_data.items():
            wd = self.watchdogs.get(pkg)
            is_alive = wd.get_pid() is not None if wd else False
            
            status_text = "🟢 В сети" if is_alive else "🔴 Оффлайн"
            if data['status'].startswith("❌"): status_text = "⚠️ Ошибка куки"
            
            clones_list.append(f"• `{data['instance']}`: {status_text} ({data['name']})")
            
            # Sub-menu for each clone: [clienb: ▶️ START] [clienb: ⏹ STOP] [clienb: 🌐 COOKIE]
            row_btns = [
                InlineKeyboardButton(f"▶️ {data['instance']}", callback_data=f"start_{pkg}"),
                InlineKeyboardButton(f"⏹ {data['instance']}", callback_data=f"stop_{pkg}"),
                InlineKeyboardButton(f"🌐 Куки", callback_data=f"check_{pkg}")
            ]
            keyboard.append(row_btns)
            if is_alive: active_count += 1

        report = f"🏰 *Overlord Monitoring: {self.device_id}*\n```\n{stats}\n```\n*Флот ({active_count}/{len(self.clones_data)}):*\n" + "\n".join(clones_list)
        await update.message.reply_text(report, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if query.from_user.id not in self.config.get("admin_ids", []): return
        data = query.data
        
        if data.startswith("select_"):
            target = data.replace("select_", "")
            user_id = query.from_user.id
            if target == self.device_id:
                self.selected_users[user_id] = True
                await query.edit_message_text(f"✅ Устройство `{self.device_id}` выбрано для управления.", parse_mode='Markdown')
            else:
                self.selected_users[user_id] = False
                # Silently unselect as others will handle the 'Selected' message
            await query.answer()

        elif data.startswith("start_"):
            pkg = data.replace("start_", "")
            self.safe_print(f"🚀 Auto-Repair & Launch: {pkg}")
            threading.Thread(target=self.surgical_launch, args=(pkg,)).start()
            await query.answer(f"Запуск {pkg}...")
            
        elif data.startswith("stop_"):
            pkg = data.replace("stop_", "")
            if pkg in self.watchdogs:
                self.watchdogs[pkg].force_stop()
                if pkg in self.clones_data:
                    self.sheet.update_status(self.clones_data[pkg]['row'], "🔴 Оффлайн")
            await query.answer(f"Остановлен {pkg}")

        elif data.startswith("check_"):
            pkg = data.replace("check_", "")
            cdata = self.clones_data.get(pkg)
            is_valid = self.injector.validate_cookie(cdata['cookie']) if cdata else False
            status = "✅ Живые" if is_valid else "❌ Мертвые"
            await query.answer(f"Статус куки для {pkg}: {status}", show_alert=True)

        elif data == "admin_clean":
            MemoryManager.system_deep_clean()
            await query.answer("RAM очищена")
            
        elif data == "admin_reinject":
            threading.Thread(target=self.master_reinject_sequence).start()
            await query.answer("Мастер-переинжект запущен")

        elif data == "admin_reboot":
            self.safe_print("Выполняю перезагрузку Termux...")
            os.execv(sys.executable, ['python'] + sys.argv)

    def sync_loop_tick(self):
        if not self.sheet.connect(): 
            self.safe_print("⚠️ Не удалось подключиться к Таблицам.")
            return

        clones = self.sheet.get_my_clones(self.device_id)
        if not clones:
            logger.warning(f"Девайс {self.device_id} не найден в базе.")
            return

        for c in clones:
            pkg = f"com.roblox.{c['instance']}"
            self.clones_data[pkg] = c
            if pkg not in self.watchdogs:
                self.watchdogs[pkg] = WatchdogPro(pkg, lambda x: logger.info(x))

            new_cookie = c['cookie']
            if self.cookie_cache.get(pkg) != new_cookie and new_cookie:
                self.safe_print(f"Обнаружен новый кук для {c['instance']}. Инжектирую...")
                self.cookie_cache[pkg] = new_cookie
                threading.Thread(target=self.surgical_launch, args=(pkg,)).start()
        
        # Cleanup
        current_pkgs = [f"com.roblox.{c['instance']}" for c in clones]
        removed = set(self.watchdogs.keys()) - set(current_pkgs)
        for r_pkg in removed:
            self.watchdogs[r_pkg].force_stop()
            del self.watchdogs[r_pkg]
            del self.clones_data[r_pkg]

    def surgical_launch(self, pkg):
        """v7 Surgical Auto-Repair: Validate -> Stop -> Inject -> Chown -> Monkey Launch."""
        data = self.clones_data.get(pkg)
        if not data: return

        # 1. Validate
        if not self.injector.validate_cookie(data['cookie']):
            self.safe_print(f"❌ КУКИ МЕРТВЫ для {data['name']}!")
            self.sheet.update_status(data['row'], "❌ Invalid")
            return

        # 2. Status Update
        self.sheet.update_status(data['row'], "⏳ Repairing")

        # 3. Inject (Includes Force-Stop and Chown in injector.py)
        if self.injector.inject(data['instance'], data['cookie']):
            # 4. Monkey Launch (Cold Start)
            self.safe_print(f"Холодный запуск {pkg}...")
            MemoryManager.v4_pre_launch_optimize()
            subprocess.run(f"su -c 'monkey -p {pkg} -c android.intent.category.LAUNCHER 1'", shell=True)
            
            # Wait for splash, then join server via Link
            time.sleep(15)
            link = ServerEngine.get_random_server() or self.config.get("default_link", "")
            subprocess.run(f"su -c 'am start -a android.intent.action.VIEW -d \"{link}\" {pkg}'", shell=True)
            
            self.watchdogs[pkg].last_launch_time = time.time()
            self.sheet.update_status(data['row'], "✅ Online")
            
            # Post-launch optimization
            time.sleep(10)
            pid = self.watchdogs[pkg].get_pid()
            if pid: subprocess.run(f"su -c 'renice -n -20 -p {pid}'", shell=True)
        else:
            self.sheet.update_status(data['row'], "⚠️ Inject Fail")

    def watchdog_loop(self):
        self.safe_print("Watchdog v7 Overlord активен.")
        while True:
            self.sync_loop_tick()
            for pkg, wd in self.watchdogs.items():
                if not wd.check_health():
                    threading.Thread(target=self.surgical_launch, args=(pkg,)).start()
            gc.collect()
            time.sleep(240)

    def master_reinject_sequence(self):
        pkgs = list(self.watchdogs.keys())
        for pkg in pkgs: self.watchdogs[pkg].force_stop()
        time.sleep(5)
        MemoryManager.system_deep_clean()
        for pkg in pkgs:
            threading.Thread(target=self.surgical_launch, args=(pkg,)).start()
            time.sleep(20)

    def run(self):
        async def post_init(application):
            self.app = application
            self.loop = asyncio.get_event_loop()
            await self.broadcast(f"🏰 Aegis Commander v7 Overlord Online: {self.device_id}")

        app = ApplicationBuilder().token(self.config["bot_token"]).post_init(post_init).build()
        app.add_handler(CommandHandler("start", self.start_cmd))
        app.add_handler(CommandHandler("help", self.help_cmd))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_text))
        app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        MemoryManager.setup_swap()
        threading.Thread(target=self.watchdog_loop, daemon=True).start()
        app.run_polling()

if __name__ == "__main__":
    time.sleep(5)
    AegisOverlordOrchestrator().run()
