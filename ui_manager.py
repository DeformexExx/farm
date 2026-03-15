# -*- coding: utf-8 -*-
from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup

class UIManager:
    @staticmethod
    def get_welcome_text(device_id: str) -> str:
        """Premium Liquid Glass Header - V3.0"""
        return (
            f"💎 *AEGIS OVERLORD v3.0* 💎\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡️ *SYSTEM STATUS:* [💠 ONLINE]\n"
            f"📱 *ACTIVE DEVICE:* `{device_id}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Добро пожаловать в панель управления ALPHA."
        )

    @staticmethod
    def get_main_keyboard() -> ReplyKeyboardMarkup:
        """Dashboard Main Menu"""
        return ReplyKeyboardMarkup([
            [KeyboardButton("📱 DEVICE"), KeyboardButton("🤖 CLONES")],
            [KeyboardButton("⚙️ SYSTEM")]
        ], resize_keyboard=True)

    @staticmethod
    def get_device_keyboard() -> InlineKeyboardMarkup:
        """Device Management Menu"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("♻️ GLOBAL SYNC", callback_data="sys_sync")],
            [InlineKeyboardButton("❄️ DROP CACHES", callback_data="sys_drop_caches")],
            [InlineKeyboardButton("🏠 BACK", callback_data="nav_home")]
        ])

    @staticmethod
    def get_clones_hub_keyboard(clones_data) -> InlineKeyboardMarkup:
        """Industrial Card Controls - V3.0 Hub"""
        keyboard = []
        keyboard.append([
            InlineKeyboardButton("⚡️ MASS START", callback_data="mass_start"),
            InlineKeyboardButton("❄️ MASS STOP", callback_data="mass_stop")
        ])
        for clone in clones_data:
            name = clone.get("name", "Unknown")
            keyboard.append([
                InlineKeyboardButton(f"⚡️ RE {name.upper()}", callback_data=f"start_{name}"),
                InlineKeyboardButton(f"❄️ STOP {name.upper()}", callback_data=f"stop_{name}")
            ])
        keyboard.append([InlineKeyboardButton("🏠 BACK TO HOME", callback_data="nav_home")])
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def get_system_keyboard(console_on: bool, restore_on: bool) -> InlineKeyboardMarkup:
        """System Tools Menu"""
        c_st = "🟢 ON" if console_on else "🔴 OFF"
        r_st = "🟢 ON" if restore_on else "🔴 OFF"
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📟 CONSOLE: {c_st}", callback_data="toggle_console")],
            [InlineKeyboardButton(f"🔄 AUTO-RESTORE: {r_st}", callback_data="toggle_restore")],
            [InlineKeyboardButton("🖼 SCREENSHOT", callback_data="sys_screenshot"), InlineKeyboardButton("❓ HELP", callback_data="sys_help")],
            [InlineKeyboardButton("🏠 BACK", callback_data="nav_home")]
        ])

    @staticmethod
    def format_dashboard(device_id: str, ram: str, cpu: str, temp: str) -> str:
        """Home Dashboard Text - V3.0"""
        return (
            f"💎 *PROJECT AEGIS V3.0* 💎\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📱 *DEVICE:* `{device_id}`\n"
            f"🐕 *WATCHDOG:* [💠 ACTIVE (THR)]\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🧠 *RAM:* `{ram}` | 🚀 *CPU:* `{cpu}`\n"
            f"🌡 *TEMP:* `{temp}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✨ _Industrial Stability Active_"
        )

    @staticmethod
    def format_clones_hub(clones_data: list, status_map: dict, targets: dict) -> str:
        """V3.0 Card UI: Threads + Real-time Status"""
        msg = "💎 *CLONE HUB v3.0* 💎\n"
        msg += "━━━━━━━━━━━━━━━━━━\n"
        for clone in clones_data:
            name = clone.get("name", "Unknown")
            st = status_map.get(name, "Offline")
            is_sync = name in targets
            
            # Icon logic
            if "Offline" in st: ico, thr = "🌑 OFFLINE", "N/A"
            elif "ERR" in st or "Error" in st: ico, thr = "⚠️ FAILED", "N/A"
            else:
                ico = "🟢 ONLINE"
                import re
                m = re.search(r"Thr:\s*(\d+)", st)
                thr = m.group(1) if m else "?"
            
            state = "👤 ON (Synced)" if is_sync else "🌑 OFF"
            msg += f"[🎮 *{name.upper()}*]\n"
            msg += f"STATUS: {ico}\n"
            msg += f"STATE: {state}\n"
            msg += f"WATCHDOG: 🧵 Threads: {thr}\n"
            msg += "━━━━━━━━━━━━━━━━━━\n"
        return msg

    @staticmethod
    def get_help_page() -> str:
        return ("🎮 *V3.0 INDUSTRIAL GUIDE*\n\n"
                "• /start - Главная панель\n"
                "• /console - Потоковые логи\n"
                "• Watchdog: Рестарт при < 130 потоков.\n"
                "• Single Master: Авто-убийство дубликатов.")
