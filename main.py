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

# Aegis v7.1 Overlord: JSON Revolution
from hardware_monitor import HardwareMonitor
from memory_manager import MemoryManager
from server_engine import ServerEngine
from watchdog_pro import WatchdogPro
from config_manager import ConfigManager
from cookie_injector import CookieInjector

# Constants
LOG_FILE = "aegis.log"
SCREENSHOT_PATH = "/data/local/tmp/s.png"
LOCAL_CONFIG = "config.json"

# Global Identity Context (argv[1] is DEVICE_ID, e.g. DEV_2)
ACTIVE_DEVICE_ID = sys.argv[1] if len(sys.argv) > 1 else "MASTER"

# Logging pipeline
logging.basicConfig(
    level=logging.INFO,
    format=f'%(asctime)s [{ACTIVE_DEVICE_ID}] [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger("AegisV7.1")

class AegisJSONOverlord:
    def __init__(self):
        self.device_id = ACTIVE_DEVICE_ID
        self.bot_config = self.load_bot_config()
        self.dm = ConfigManager(self.device_id)
        self.injector = CookieInjector(self.safe_print)
        self.watchdogs = {}
        self.app = None
        self.loop = None
        self.selected_users = {} # user_id -> boolean
        
        # Load local clones from JSON
        self.dm.load()
        self.purge_ghosts()

    def load_bot_config(self):
        if os.path.exists(LOCAL_CONFIG):
            with open(LOCAL_CONFIG, "r") as f:
                return json.load(f)
        return {"bot_token": "", "admin_ids": []}

    def purge_ghosts(self):
        try:
            curr_pid = os.getpid()
            cmd = f"su -c \"ps -ef | grep main.py | grep -v grep | grep -v {curr_pid} | awk '{{print $2}}' | xargs kill -9\""
            subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("Ghosts purged.")
        except: pass

    def safe_print(self, text):
        prefixed = f"[{self.device_id}] {text}"
        logger.info(text)
        if self.app:
            asyncio.run_coroutine_threadsafe(self.broadcast(prefixed), self.loop)

    async def broadcast(self, text):
        for admin_id in self.bot_config.get("admin_ids", []):
            try: await self.app.bot.send_message(chat_id=admin_id, text=text)
            except: pass

    def get_main_keyboard(self):
        """v7.1 Russian UI Grid."""
        keyboard = [
            [KeyboardButton("📊 Мониторинг"), KeyboardButton("🔄 Обновить конфиг")],
            [KeyboardButton("🖼 Скриншот"), KeyboardButton("🛠 Админка")],
            [KeyboardButton("📱 Выбрать девайс")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    async def start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in self.bot_config.get("admin_ids", []): return
        self.selected_users[update.effective_user.id] = True
        await update.message.reply_text(
            f"🚀 *Aegis Overlord: JSON Revolution*\nДевайс: `{self.device_id}`\nИсточник: `{self.device_id}.json` (Local)",
            reply_markup=self.get_main_keyboard(),
            parse_mode='Markdown'
        )

    async def update_config_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in self.bot_config.get("admin_ids", []): return
        await update.message.reply_text("🔄 Обновление конфигов из Git...")
        try:
            res = subprocess.run("git pull", shell=True, capture_output=True, text=True)
            if self.dm.load():
                await update.message.reply_text(f"✅ Конфиг обновлен!\n```\n{res.stdout}\n```", parse_mode='Markdown')
            else:
                await update.message.reply_text("⚠️ Git обновлен, но файл конфига не найден или поврежден.")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка Git: {e}")

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in self.bot_config.get("admin_ids", []): return
        text = update.message.text
        is_selected = self.selected_users.get(user_id, False)

        if text == "📊 Мониторинг":
            if is_selected: await self.send_overlord_report(update)
            
        elif text == "🔄 Обновить конфиг":
            if is_selected: await self.update_config_cmd(update, context)

        elif text == "🛠 Админка":
            if is_selected:
                kb = [
                    [InlineKeyboardButton("🚀 Master Re-Inject", callback_data="admin_reinject")],
                    [InlineKeyboardButton("🔄 Reboot Bot", callback_data="admin_reboot")]
                ]
                await update.message.reply_text(f"🛠 [{self.device_id}] Админ-панель:", reply_markup=InlineKeyboardMarkup(kb))

        elif text == "🖼 Скриншот":
            if is_selected: await self.take_snap(update.message)

        elif text == "📱 Выбрать девайс":
            kb = [[InlineKeyboardButton(f"✅ Выбрать {self.device_id}", callback_data=f"select_{self.device_id}")]]
            await update.message.reply_text(f"📱 Устройство: `{self.device_id}`", reply_markup=InlineKeyboardMarkup(kb))

        elif text.startswith("$"):
            if is_selected:
                cmd = text[1:].strip()
                await self.execute_shell(update, cmd)

    async def execute_shell(self, update: Update, cmd):
        try:
            res = subprocess.run(f"su -c '{cmd}'", shell=True, capture_output=True, text=True, timeout=30)
            out = (res.stdout + res.stderr).strip() or "[No output]"
            await update.message.reply_text(f"```bash\n[{self.device_id}]\n{out[:3500]}\n```", parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"[{self.device_id}] Shell Error: {e}")

    async def take_snap(self, message):
        try:
            subprocess.run(f"su -c 'screencap -p {SCREENSHOT_PATH}'", shell=True)
            if os.path.exists(SCREENSHOT_PATH):
                with open(SCREENSHOT_PATH, 'rb') as f:
                    await message.reply_photo(photo=f, caption=f"📸 Снимок: {self.device_id}")
                os.remove(SCREENSHOT_PATH)
        except: pass

    async def send_overlord_report(self, update: Update):
        clones = self.dm.get_clones()
        if not clones:
            await update.message.reply_text(f"❌ *Ошибка*: Пустой конфиг для `{self.device_id}`!")
            return

        active_count = 0
        clones_list = []
        keyboard = []
        
        stats = HardwareMonitor.get_dashboard_report(self.device_id, "")
        
        for c in clones:
            pkg = f"com.roblox.{c['name']}"
            wd = self.watchdogs.get(pkg)
            is_alive = wd.get_pid() is not None if wd else False
            
            status_text = "🟢 OK" if is_alive else "🔴 OFF"
            if c.get('status') == "⚠️ Ошибка": status_text = "⚠️ ERR"
            
            clones_list.append(f"• `{c['name']}`: {status_text} ({c['nickname']})")
            
            row = [
                InlineKeyboardButton(f"▶️ Запуск", callback_data=f"start_{c['name']}"),
                InlineKeyboardButton(f"⏹ Стоп", callback_data=f"stop_{c['name']}"),
                InlineKeyboardButton(f"🧹 Очистка", callback_data=f"clean_{c['name']}")
            ]
            keyboard.append(row)
            if is_alive: active_count += 1

        report = f"🏰 *Overlord Monitor: {self.device_id}*\n```\n{stats}\n```\n*Аккаунты ({active_count}/{len(clones)}):*\n" + "\n".join(clones_list)
        await update.message.reply_text(report, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if query.from_user.id not in self.bot_config.get("admin_ids", []): return
        data = query.data
        
        if data.startswith("select_"):
            target = data.replace("select_", "")
            self.selected_users[query.from_user.id] = (target == self.device_id)
            if target == self.device_id:
                await query.edit_message_text(f"✅ Устройство `{self.device_id}` активировано.")
            await query.answer()

        elif data.startswith("start_"):
            instance = data.replace("start_", "")
            pkg = f"com.roblox.{instance}"
            self.safe_print(f"🚀 Surgical Launch: {instance}")
            threading.Thread(target=self.surgical_launch, args=(instance,)).start()
            await query.answer(f"Запуск {instance}...")
            
        elif data.startswith("stop_"):
            instance = data.replace("stop_", "")
            pkg = f"com.roblox.{instance}"
            if pkg in self.watchdogs: self.watchdogs[pkg].force_stop()
            self.dm.update_status(instance, "🔴 OFF")
            await query.answer(f"Остановлен {instance}")

        elif data.startswith("clean_"):
            instance = data.replace("clean_", "")
            subprocess.run(f"su -c 'am force-stop com.roblox.{instance}'", shell=True)
            subprocess.run(f"su -c 'rm -rf /data/data/com.roblox.{instance}/cache/*'", shell=True)
            await query.answer(f"Кэш {instance} очищен", show_alert=True)

        elif data == "admin_reinject":
            threading.Thread(target=self.master_reinject).start()
            await query.answer("Master Re-Inject запущен")

        elif data == "admin_reboot":
            os.execv(sys.executable, ['python'] + sys.argv)

    def surgical_launch(self, instance):
        """v7.1 Surgery: Stop -> Inject w/ Chown -> Monkey Launch."""
        pkg = f"com.roblox.{instance}"
        if pkg not in self.watchdogs:
            self.watchdogs[pkg] = WatchdogPro(pkg, lambda x: logger.info(x))

        clone = next((c for c in self.dm.get_clones() if c['name'] == instance), None)
        if not clone: return

        # 1. Inject (Refined with direct Owner discovery)
        self.dm.update_status(instance, "⏳ Injecting")
        if self.injector.inject(instance, clone['cookie']):
            # 2. Start
            self.safe_print(f"Запуск приложения {instance}...")
            MemoryManager.v4_pre_launch_optimize()
            subprocess.run(f"su -c 'monkey -p {pkg} 1'", shell=True)
            
            time.sleep(15)
            link = ServerEngine.get_random_server() or self.bot_config.get("default_link", "")
            subprocess.run(f"su -c 'am start -a android.intent.action.VIEW -d \"{link}\" {pkg}'", shell=True)
            
            self.watchdogs[pkg].last_launch_time = time.time()
            self.dm.update_status(instance, "✅ OK")
        else:
            self.dm.update_status(instance, "❌ ERR_INJECT")

    def monitoring_loop(self):
        self.safe_print("Monitoring Loop (JSON context) active.")
        while True:
            # Check Health for all clones in JSON
            for c in self.dm.get_clones():
                pkg = f"com.roblox.{c['name']}"
                if pkg not in self.watchdogs:
                    self.watchdogs[pkg] = WatchdogPro(pkg, lambda x: logger.info(x))
                
                wd = self.watchdogs[pkg]
                if not wd.check_health():
                    # Thread count < 130 or PID missing
                    if wd.get_pid():
                        self.safe_print(f"⚠️ {c['name']} Freeze detected (Low threads)!")
                        self.dm.update_status(c['name'], "⚠️ Ошибка")
                    threading.Thread(target=self.surgical_launch, args=(c['name'],)).start()
            
            gc.collect()
            time.sleep(240)

    def master_reinject(self):
        for c in self.dm.get_clones():
            pkg = f"com.roblox.{c['name']}"
            if pkg in self.watchdogs: self.watchdogs[pkg].force_stop()
        
        MemoryManager.system_deep_clean()
        for c in self.dm.get_clones():
            self.surgical_launch(c['name'])
            time.sleep(20)

    def run(self):
        async def post_init(application):
            self.app = application
            self.loop = asyncio.get_event_loop()
            await self.broadcast(f"🚀 Overlord JSON Revision Online: {self.device_id}")

        app = ApplicationBuilder().token(self.bot_config["bot_token"]).post_init(post_init).build()
        app.add_handler(CommandHandler("start", self.start_cmd))
        app.add_handler(CommandHandler("update_config", self.update_config_cmd))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_text))
        app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        threading.Thread(target=self.monitoring_loop, daemon=True).start()
        app.run_polling()

if __name__ == "__main__":
    time.sleep(2)
    AegisJSONOverlord().run()
