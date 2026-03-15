# -*- coding: utf-8 -*-
from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup

class UIManager:
    @staticmethod
    def get_main_keyboard() -> ReplyKeyboardMarkup:
        """Постоянное меню бота"""
        keyboard = [
            [KeyboardButton("📊 МОНИТОРИНГ"), KeyboardButton("🔄 GIT SYNC")],
            [KeyboardButton("🖼 СКРИНШОТ")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    @staticmethod
    def get_clone_inline_keyboard(clones, get_status_callback) -> InlineKeyboardMarkup:
        """Инлайн клавиатура для каждого клона. get_status_callback должен возвращать статистику (или 'Offline') по имени"""
        keyboard = []
        for clone in clones:
            name = clone.get("name", "Unknown")
            
            row = [
                InlineKeyboardButton(f"▶️ START", callback_data=f"start_{name}"),
                InlineKeyboardButton(f"⏹ STOP", callback_data=f"stop_{name}"),
                InlineKeyboardButton(f"🧹 CLEAN", callback_data=f"clean_{name}")
            ]
            keyboard.append(row)
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def format_dashboard(device_id: str, ram: str, cpu: str, temp: str, clones: list, status_map: dict) -> str:
        """
        Форматирует главное сообщение дашборда мониторинга.
        status_map: словарь {clone_name: 'статус строка (например: Mem: 120MB | Thr: 45)'}
        """
        msg = f"📱 Устройство: `{device_id}`\n🧠 RAM: {ram} | 🚀 CPU: {cpu} | 🌡 Temp: {temp}\n\n"
        
        for clone in clones:
            name = clone.get("name", "Unknown")
            status_str = status_map.get(name, "🔴 Offline")
            
            if "Offline" in status_str:
                msg += f"🔴 `{name}` | Offline\n"
            else:
                msg += f"🟢 `{name}` | {status_str}\n"
                
        return msg

    @staticmethod
    def get_welcome_text(device_id: str) -> str:
        return f"👑 *AEGIS NEBULA v20.0: FLEET CONTROL*\nУстройство: `{device_id}`"
