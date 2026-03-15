# -*- coding: utf-8 -*-
from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup

class UIManager:
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
    def get_clones_keyboard(clones_data) -> InlineKeyboardMarkup:
        """Clones Center Menu with Mass Controls"""
        keyboard = []
        # Mass Controls
        keyboard.append([
            InlineKeyboardButton("⚡️ MASS START", callback_data="mass_start"),
            InlineKeyboardButton("❄️ MASS STOP", callback_data="mass_stop")
        ])
        
        # Individual Clones
        for clone in clones_data:
            name = clone.get("name", "Unknown")
            keyboard.append([InlineKeyboardButton(f"🎮 {name.upper()}", callback_data=f"clone_menu_{name}")])
            
        keyboard.append([InlineKeyboardButton("🏠 BACK", callback_data="nav_home")])
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def get_single_clone_keyboard(name: str) -> InlineKeyboardMarkup:
        """Dedicated row of buttons for one clone"""
        keyboard = [
            [
                InlineKeyboardButton("▶️ START", callback_data=f"start_{name}"),
                InlineKeyboardButton("⏹ STOP", callback_data=f"stop_{name}"),
                InlineKeyboardButton("🧹 CLEAN", callback_data=f"clean_{name}")
            ],
            [InlineKeyboardButton("⬅️ BACK TO LIST", callback_data="nav_clones")]
        ]
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
        """Home Dashboard Text"""
        return (
            f"💎 *PROJECT AEGIS V2.0* 💎\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📱 *DEVICE:* `{device_id}`\n"
            f"🧠 *RAM:* `{ram}` | 🚀 *CPU:* `{cpu}`\n"
            f"🌡 *TEMP:* `{temp}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✨ _System Status: Optimal_"
        )

    @staticmethod
    def format_clones_list(clones_data: list, status_map: dict) -> str:
        """Clones Center Text"""
        msg = "🤖 *CLONE CENTER*\n━━━━━━━━━━━━━━━━━━\n"
        for clone in clones_data:
            name = clone.get("name", "Unknown")
            raw_status = status_map.get(name, "Offline")
            
            if "Offline" in raw_status:
                indicator = "🌑 [OFFLINE]"
            elif "Error" in raw_status:
                indicator = "⚠️ [ERROR]"
            else:
                indicator = "💠 [ONLINE]"
                
            msg += f"{indicator} `{name.upper()}`\n"
            if indicator == "💠 [ONLINE]":
                msg += f"└─ _{raw_status}_\n"
                
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
