# -*- coding: utf-8 -*-
from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup

class UIManager:
    @staticmethod
    def get_welcome_text(device_id: str) -> str:
        """Premium Liquid Glass Header"""
        return (
            f"💎 *AEGIS OVERLORD v2.0* 💎\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡️ *SYSTEM STATUS:* [💠 ONLINE]\n"
            f"📱 *ACTIVE DEVICE:* `{device_id}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Добро пожаловать в панель управления. Выберите раздел ниже:"
        )

    @staticmethod
    def get_main_keyboard() -> ReplyKeyboardMarkup:
        """Dashboard Main Menu"""
        keyboard = [
            [KeyboardButton("📱 DEVICE"), KeyboardButton("🤖 CLONES")],
            [KeyboardButton("⚙️ SYSTEM")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    @staticmethod
    def get_device_keyboard() -> InlineKeyboardMarkup:
        """Device Management Menu"""
        keyboard = [
            [InlineKeyboardButton("♻️ GLOBAL SYNC", callback_data="sys_sync")],
            [InlineKeyboardButton("❄️ DROP CACHES", callback_data="sys_drop_caches")],
            [InlineKeyboardButton("🏠 BACK", callback_data="nav_home")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def get_clones_hub_keyboard(clones_data) -> InlineKeyboardMarkup:
        """Sequential grid of controls for every clone card + Mass Controls"""
        keyboard = []
        # Mass Controls Block
        keyboard.append([
            InlineKeyboardButton("⚡️ MASS START", callback_data="mass_start"),
            InlineKeyboardButton("❄️ MASS STOP", callback_data="mass_stop")
        ])
        
        # Inline Controls per Clone Card
        # Layout: [⚡️ Relaunch NAME] [❄️ Stop NAME]
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
        con_status = "🟢 ON" if console_on else "🔴 OFF"
        res_status = "🟢 ON" if restore_on else "🔴 OFF"
        
        keyboard = [
            [InlineKeyboardButton(f"📟 CONSOLE: {con_status}", callback_data="toggle_console")],
            [InlineKeyboardButton(f"🔄 AUTO-RESTORE: {res_status}", callback_data="toggle_restore")],
            [InlineKeyboardButton("🖼 SCREENSHOT", callback_data="sys_screenshot"), InlineKeyboardButton("❓ HELP", callback_data="sys_help")],
            [InlineKeyboardButton("🏠 BACK", callback_data="nav_home")]
        ]
        return InlineKeyboardMarkup(keyboard)

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
            f"✨ _System Status: Stable_"
        )

    @staticmethod
    def format_clones_hub(clones_data: list, status_map: dict, persistence_targets: list) -> str:
        """High-density card blocks per clone - V3.0 Hub"""
        msg = "💎 *CLONE MANAGEMENT HUB*\n\n"
        
        for clone in clones_data:
            name = clone.get("name", "Unknown")
            raw_status = status_map.get(name, "Offline")
            is_target = name in persistence_targets
            
            # Status Indicator
            if "Offline" in raw_status:
                indicator = "🌑 OFFLINE"
                thr_count = "N/A"
            elif "Error" in raw_status or "ERR" in raw_status:
                indicator = "⚠️ FAILED"
                thr_count = "N/A"
            else:
                indicator = "🟢 ONLINE"
                # Extraction logic for Thr: count
                import re
                thr_match = re.search(r"Thr:\s*(\d+)", raw_status)
                thr_count = thr_match.group(1) if thr_match else "?"

            # State Label
            state_label = "👤 ON (Synced)" if is_target else "🌑 OFF"
            
            msg += "━━━━━━━━━━━━━━━━━━\n\n"
            msg += f"[🎮 *{name.upper()}*]\n"
            msg += f"STATUS: {indicator}\n"
            msg += f"STATE: {state_label}\n"
            msg += f"WATCHDOG: 🧵 Threads: {thr_count}\n\n"
                
        msg += "━━━━━━━━━━━━━━━━━━"
        return msg



    @staticmethod
    def get_help_page(page: int) -> str:
        pages = {
            1: "🎮 *COMMANDS*\n\n• /start - Open Dashboard\n• /console - Toggle Stream\n• /help - This Menu",
            2: "⚙️ *STRUCTURE*\n\nBot uses `/farm` directory.\nConfigs: `{DEVICE}.json`.\nGlobal: `servers.json`.",
            3: "🛠 *TROUBLESHOOTING*\n\n• No Root? Injection will fail.\n• Conflicts? Bot self-kills if multiple instances run."
        }
        return pages.get(page, "Help page not found.")

    @staticmethod
    def get_help_keyboard(current_page: int) -> InlineKeyboardMarkup:
        buttons = []
        if current_page > 1:
            buttons.append(InlineKeyboardButton("⬅️", callback_data=f"help_page_{current_page-1}"))
        if current_page < 3:
            buttons.append(InlineKeyboardButton("➡️", callback_data=f"help_page_{current_page+1}"))
        
        keyboard = [buttons] if buttons else []
        keyboard.append([InlineKeyboardButton("🏠 BACK", callback_data="nav_home")])
        return InlineKeyboardMarkup(keyboard)
