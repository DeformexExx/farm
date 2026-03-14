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

# Aegis v6.1 Core Modules
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

# Identifier (CLI Mode)
DEVICE_ID = sys.argv[1] if len(sys.argv) > 1 else "MASTER"

# Logging pipeline
logging.basicConfig(
    level=logging.INFO,
    format=f'%(asctime)s [{DEVICE_ID}] [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger("AegisV6.1")

class AegisV6Orchestrator:
    def __init__(self):
        self.device_id = DEVICE_ID
        self.config = self.load_local_config()
        self.sheet = SheetManager(CREDS_FILE, SHEET_NAME)
        self.injector = CookieInjector(self.safe_print)
        self.clones_data = {} # pkg -> data from sheet
        self.watchdogs = {}
        self.app = None
        self.loop = None
        
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
        """v6.1 Russian UI Grid."""
        keyboard = [
            [KeyboardButton("📊 Статус"), KeyboardButton("📸 Скриншот")],
            [KeyboardButton("🚀 Переинжект"), KeyboardButton("🛑 Стоп Все")],
            [KeyboardButton("🧹 Очистка"), KeyboardButton("💻 Консоль")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    async def start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in self.config.get("admin_ids", []): return
        await update.message.reply_text(
            f"🛡️ *Aegis OS v6.1: Russian Edition*\nУстройство: `{self.device_id}`\nИсточник: Google Sheets",
            reply_markup=self.get_main_keyboard(),
            parse_mode='Markdown'
        )

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in self.config.get("admin_ids", []): return
        text = update.message.text

        if text == "📊 Статус":
            await self.send_report(update)
            
        elif text == "🚀 Переинжект":
            self.safe_print("Запуск Мастер-Переинжекта (Стоп -> Инжект -> Очистка -> Старт)...")
            threading.Thread(target=self.master_reinject_sequence).start()

        elif text == "🛑 Стоп Все":
            self.safe_print("Жесткая остановка всех клонов.")
            for pkg in self.watchdogs:
                self.watchdogs[pkg].force_stop()
                if pkg in self.clones_data:
                    self.sheet.update_status(self.clones_data[pkg]['row'], "🛑 Останол")
            await update.message.reply_text(f"[{self.device_id}] Все клоны остановлены.")

        elif text == "📸 Скриншот":
            await self.take_snap(update.message)

        elif text == "🧹 Очистка":
            MemoryManager.system_deep_clean()
            await update.message.reply_text(f"[{self.device_id}] Очистка RAM и кэша выполнена.")

        elif text.startswith("$") or text.lower().startswith("shell "):
            cmd = text[1:].strip() if text.startswith("$") else text[6:].strip()
            if cmd.startswith(self.device_id) or cmd.startswith("FLEET"):
                real_cmd = cmd.replace(self.device_id, "").replace("FLEET", "").strip()
                await self.execute_shell(update, real_cmd)

    async def execute_shell(self, update: Update, cmd):
        try:
            res = subprocess.run(f"su -c '{cmd}'", shell=True, capture_output=True, text=True, timeout=30)
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

    async def send_report(self, update: Update):
        active_count = 0
        clones_list = []
        keyboard = []
        
        # System Stats
        stats = HardwareMonitor.get_dashboard_report(self.device_id, "")
        
        # Clone List & Inline Buttons
        for pkg, data in self.clones_data.items():
            wd = self.watchdogs.get(pkg)
            is_alive = wd.get_pid() is not None if wd else False
            
            status_emoji = "🟢 В сети" if is_alive else "🔴 Оффлайн"
            if data['status'] == "❌ Invalid": status_emoji = "⚠️ Ошибка куки"
            
            clones_list.append(f"• {data['instance']} ({data['name']}): {status_emoji}")
            
            # Start/Stop buttons for each
            row_btns = [
                InlineKeyboardButton(f"▶️ {data['instance']}", callback_data=f"start_{pkg}"),
                InlineKeyboardButton(f"🛑 {data['instance']}", callback_data=f"stop_{pkg}")
            ]
            keyboard.append(row_btns)
            if is_alive: active_count += 1

        report = f"```\n{stats}\n```\n*Список клонов ({active_count}/{len(self.clones_data)}):*\n" + "\n".join(clones_list)
        await update.message.reply_text(report, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if query.from_user.id not in self.config.get("admin_ids", []): return
        data = query.data
        
        if data.startswith("start_"):
            pkg = data.replace("start_", "")
            self.safe_print(f"Ручной запуск: {pkg}")
            threading.Thread(target=self.smart_launch, args=(pkg,)).start()
        elif data.startswith("stop_"):
            pkg = data.replace("stop_", "")
            self.safe_print(f"Ручная остановка: {pkg}")
            if pkg in self.watchdogs:
                self.watchdogs[pkg].force_stop()
                if pkg in self.clones_data:
                    self.sheet.update_status(self.clones_data[pkg]['row'], "🛑 Останол")
        
        await query.answer("Выполнено")

    def sync_loop_tick(self):
        if not self.sheet.connect(): return
        clones = self.sheet.get_my_clones(self.device_id)
        if not clones: return

        for c in clones:
            pkg = f"com.roblox.{c['instance']}"
            self.clones_data[pkg] = c
            if pkg not in self.watchdogs:
                self.watchdogs[pkg] = WatchdogPro(pkg, lambda x: logger.info(x))

            new_cookie = c['cookie']
            if self.cookie_cache.get(pkg) != new_cookie and new_cookie:
                self.safe_print(f"Обнаружен новый кук для {c['instance']}. Инжектирую...")
                self.cookie_cache[pkg] = new_cookie
                threading.Thread(target=self.smart_launch, args=(pkg,)).start()
        
        # Cleanup
        current_pkgs = [f"com.roblox.{c['instance']}" for c in clones]
        removed = set(self.watchdogs.keys()) - set(current_pkgs)
        for r_pkg in removed:
            self.watchdogs[r_pkg].force_stop()
            del self.watchdogs[r_pkg]
            del self.clones_data[r_pkg]

    def smart_launch(self, pkg):
        data = self.clones_data.get(pkg)
        if not data: return

        if not self.injector.validate_cookie(data['cookie']):
            self.safe_print(f"❌ КУКИ ПРОТУХЛИ для {data['name']}!")
            self.sheet.update_status(data['row'], "❌ Invalid")
            return

        self.sheet.update_status(data['row'], "⏳ Starting")
        if self.injector.inject(data['instance'], data['cookie']):
            self.safe_launch_command(pkg)
            time.sleep(12) 
            self.sheet.update_status(data['row'], "✅ Online")
        else:
            self.sheet.update_status(data['row'], "⚠️ Inject Error")

    def safe_launch_command(self, pkg):
        MemoryManager.v4_pre_launch_optimize()
        link = ServerEngine.get_random_server() or self.config.get("default_link", "")
        cmd = f"su -c 'am start -a android.intent.action.VIEW -d \"{link}\" {pkg}'"
        
        self.watchdogs[pkg].last_launch_time = time.time()
        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setpgrp)
        threading.Thread(target=self.renice_task, args=(pkg,)).start()

    def renice_task(self, pkg):
        time.sleep(10)
        pid = self.watchdogs[pkg].get_pid()
        if pid: subprocess.run(f"su -c 'renice -n -20 -p {pid}'", shell=True)

    def watchdog_loop(self):
        self.safe_print("Цикл синхронизации активен (4 мин).")
        while True:
            self.sync_loop_tick()
            for pkg, wd in self.watchdogs.items():
                if not wd.check_health():
                    threading.Thread(target=self.smart_launch, args=(pkg,)).start()
            gc.collect()
            time.sleep(240)

    def master_reinject_sequence(self):
        """Surgical Master Re-Inject: Stop -> Inject -> Clean -> Start All."""
        pkgs = list(self.watchdogs.keys())
        for pkg in pkgs: self.watchdogs[pkg].force_stop()
        time.sleep(5)
        
        MemoryManager.system_deep_clean()
        
        for pkg in pkgs:
            threading.Thread(target=self.smart_launch, args=(pkg,)).start()
            time.sleep(15)

    def run(self):
        async def post_init(application):
            self.app = application
            self.loop = asyncio.get_event_loop()
            await self.broadcast(f"🚢 Aegis v6.1 Russian UI Online: {self.device_id}")

        app = ApplicationBuilder().token(self.config["bot_token"]).post_init(post_init).build()
        app.add_handler(CommandHandler("start", self.start_cmd))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_text))
        app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        MemoryManager.setup_swap()
        threading.Thread(target=self.watchdog_loop, daemon=True).start()
        app.run_polling()

if __name__ == "__main__":
    time.sleep(5)
    AegisV6Orchestrator().run()
