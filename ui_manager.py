# -*- coding: utf-8 -*-
# ui_manager.py — Project Aegis V3.0 Card UI
import re
from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup


class UIManager:

    # ── WELCOME ───────────────────────────────────────────────────────────
    @staticmethod
    def get_welcome_text(device_id: str) -> str:
        return (
            "💎 *AEGIS OVERLORD v3.0* 💎\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡️ SYSTEM: `[💠 ONLINE]`\n"
            f"📱 DEVICE: `{device_id}`\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )

    # ── KEYBOARDS ─────────────────────────────────────────────────────────
    @staticmethod
    def get_main_keyboard() -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup([
            [KeyboardButton("📱 DEVICE"), KeyboardButton("🤖 CLONES")],
            [KeyboardButton("⚙️ SYSTEM")],
        ], resize_keyboard=True)

    @staticmethod
    def get_device_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("♻️ GLOBAL SYNC", callback_data="sys_sync")],
            [InlineKeyboardButton("🖼 SCREENSHOT",  callback_data="sys_screenshot")],
            [InlineKeyboardButton("🏠 BACK",        callback_data="nav_home")],
        ])

    @staticmethod
    def get_system_keyboard(console_on: bool, restore_on: bool) -> InlineKeyboardMarkup:
        c = "🟢 ON" if console_on  else "🔴 OFF"
        r = "🟢 ON" if restore_on else "🔴 OFF"
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📟 CONSOLE: {c}",      callback_data="toggle_console")],
            [InlineKeyboardButton(f"🔄 AUTO-RESTORE: {r}", callback_data="toggle_restore")],
            [InlineKeyboardButton("❓ HELP",                callback_data="sys_help")],
            [InlineKeyboardButton("🏠 BACK",               callback_data="nav_home")],
        ])

    # ── DASHBOARD TEXT ─────────────────────────────────────────────────────
    @staticmethod
    def format_dashboard(device_id: str, ram: str, cpu: str, temp: str) -> str:
        return (
            "💎 *PROJECT AEGIS V3.0* 💎\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 DEVICE : `{device_id}`\n"
            f"🐕 WATCHDOG: `[💠 ACTIVE – Thread Monitor]`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🧠 RAM: `{ram}` | 🚀 CPU: `{cpu}`\n"
            f"🌡 TEMP: `{temp}`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✨ _Industrial Stability Active_"
        )

    # ── CLONE HUB TEXT (Card System) ──────────────────────────────────────
    @staticmethod
    def format_clones_hub(clones_data: list, status_map: dict, targets: dict) -> str:
        """
        Generates one TEXT block with one card per clone.
        status_map: {name: "Mem: X | Thr: Y"  or  "Offline"}
        targets:    {name: True} — names of auto-managed clones
        """
        msg = "💎 *CLONE HUB V3.0*\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"

        if not clones_data:
            msg += "_No clones configured._"
            return msg

        for clone in clones_data:
            name = clone.get("name", "Unknown")
            st   = status_map.get(name, "Offline")

            # ── Status icon + thread count ──────────────────────────────
            if "Offline" in st:
                icon, thr = "🌑 OFFLINE", "—"
            elif "ERR" in st or "Error" in st:
                icon, thr = "⚠️ FAILED", "—"
            else:
                icon = "🟢 ONLINE"
                m = re.search(r"Thr:\s*(\d+)", st)
                thr = m.group(1) if m else "?"

            # ── Watchdog threshold warning ──────────────────────────────
            thr_warn = ""
            if thr.isdigit():
                t = int(thr)
                if   t < 130: thr_warn = " ⚠️ FROZEN"
                elif t > 500: thr_warn = " 🔴 LEAK"

            # ── Sync state ──────────────────────────────────────────────
            state = "👤 Synced" if name in targets else "🌑 Manual"

            msg += (
                f"[🎮 *{name.upper()}*] | {icon}\n"
                f"🧵 Threads: `{thr}`{thr_warn}\n"
                f"State: {state}\n"
                "╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            )

        return msg

    # ── CLONE HUB KEYBOARD ────────────────────────────────────────────────
    @staticmethod
    def get_clones_hub_keyboard(clones_data: list) -> InlineKeyboardMarkup:
        """
        Top row: MASS controls.
        One row per clone: [⚡️ Relaunch] [❄️ Stop]
        Bottom row: back.
        """
        rows = []
        # Mass controls
        rows.append([
            InlineKeyboardButton("⚡️ MASS START", callback_data="mass_start"),
            InlineKeyboardButton("❄️ MASS STOP",  callback_data="mass_stop"),
        ])
        # Per-clone controls
        for clone in clones_data:
            n = clone.get("name", "?")
            rows.append([
                InlineKeyboardButton(f"⚡️ {n.upper()}", callback_data=f"start_{n}"),
                InlineKeyboardButton(f"❄️ {n.upper()}", callback_data=f"stop_{n}"),
            ])
        rows.append([InlineKeyboardButton("🏠 HOME", callback_data="nav_home")])
        return InlineKeyboardMarkup(rows)

    # ── HELP ──────────────────────────────────────────────────────────────
    @staticmethod
    def get_help_text() -> str:
        return (
            "🎮 *V3.0 INDUSTRIAL GUIDE*\n\n"
            "• /start — Dashboard\n"
            "• /console — Last 10 boot log lines\n"
            "• Watchdog: auto-restart if Thr < 130\n"
            "• Single Master: kills duplicate python processes on boot\n"
            "• Targets saved to `persistence.json`"
        )
