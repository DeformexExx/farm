# -*- coding: utf-8 -*-
# ui_manager.py — Project Aegis V4.0 Dark Premium
import re
from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup


def _fmt_uptime(seconds: float) -> str:
    """Format elapsed seconds as Xh Ym or Ym Zs."""
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {sec}s"
    return f"{sec}s"


class UIManager:

    # ── WELCOME ───────────────────────────────────────────────────────────
    @staticmethod
    def get_welcome_text(device_id: str) -> str:
        return (
            "💎 *AEGIS OVERLORD V4.0*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡️ SYSTEM : `[💠 ONLINE]`\n"
            f"📱 DEVICE : `{device_id}`\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )

    # ── MAIN KEYBOARD ─────────────────────────────────────────────────────
    @staticmethod
    def get_main_keyboard() -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup([
            [KeyboardButton("📱 DEVICE"), KeyboardButton("🤖 CLONES")],
            [KeyboardButton("⚙️ SYSTEM")],
        ], resize_keyboard=True)

    # ── DEVICE DASHBOARD ──────────────────────────────────────────────────
    @staticmethod
    def format_dashboard(device_id: str, ram: str, cpu: str, temp: str) -> str:
        return (
            "💎 *AEGIS V4.0 — DEVICE*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 DEVICE  : `{device_id}`\n"
            f"🐕 WATCHDOG: `[STATE-GATED 🔒]`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🧠 RAM: `{ram}` | 🚀 CPU: `{cpu}`\n"
            f"🌡 TEMP: `{temp}`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✨ _State Machine Active_"
        )

    @staticmethod
    def get_device_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("♻️ GIT SYNC",   callback_data="sys_sync")],
            [InlineKeyboardButton("🖼 SCREENSHOT", callback_data="sys_screenshot")],
            [InlineKeyboardButton("🏠 BACK",       callback_data="nav_home")],
        ])

    # ── SYSTEM ────────────────────────────────────────────────────────────
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

    # ── CLONE HUB TEXT — V4.0 State Machine Cards ─────────────────────────
    @staticmethod
    def format_clones_hub(clones_data: list, state_map: dict, uptime_map: dict) -> str:
        """
        state_map:  {clone_name: CloneState (str value)}
        uptime_map: {clone_name: start_timestamp (float) or None}
        """
        msg = "💎 *AEGIS OVERLORD V4.0*\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"

        if not clones_data:
            msg += "_No clones configured._"
            return msg

        import time as _time

        STATE_ICONS = {
            "STOPPED":  "🌑 STOPPED",
            "STARTING": "⏳ STARTING",
            "RUNNING":  "🟢 RUNNING",
            "COOLDOWN": "🔵 COOLDOWN",
        }

        for clone in clones_data:
            name  = clone.get("name", "Unknown")
            state = state_map.get(name, "STOPPED")
            icon  = STATE_ICONS.get(state, "❓ UNKNOWN")

            # Uptime
            ts = uptime_map.get(name)
            if state == "RUNNING" and ts:
                uptime = _fmt_uptime(_time.time() - ts)
            else:
                uptime = "—"

            # Thread info (from status_map, optional)
            thr_info = state_map.get(f"{name}:threads", "")
            thr_line = f"🧵 Threads: `{thr_info}`" if thr_info else "🧵 Threads: `—`"

            msg += (
                f"[🎮 *{name.upper()}*]\n"
                f"State: {icon}\n"
                f"{thr_line} | ⏱ Uptime: `{uptime}`\n"
                "╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
            )

        return msg.rstrip()

    # ── CLONE HUB KEYBOARD ────────────────────────────────────────────────
    @staticmethod
    def get_clones_hub_keyboard(clones_data: list) -> InlineKeyboardMarkup:
        """
        Row 0: [⚡️ Mass Start] [❄️ Mass Stop]
        Rows 1-N: [⚙️ CloneA] [⚙️ CloneB]  (2 per row)
        Last: [🏠 HOME]
        """
        rows = []
        rows.append([
            InlineKeyboardButton("⚡️ Mass Start", callback_data="mass_start"),
            InlineKeyboardButton("❄️ Mass Stop",  callback_data="mass_stop"),
        ])
        names = [c.get("name", "?") for c in clones_data]
        for i in range(0, len(names), 2):
            row = [
                InlineKeyboardButton(f"⚙️ {n.upper()}", callback_data=f"clone_{n}")
                for n in names[i:i+2]
            ]
            rows.append(row)
        rows.append([InlineKeyboardButton("🏠 HOME", callback_data="nav_home")])
        return InlineKeyboardMarkup(rows)

    # ── CLONE SUB-MENU ────────────────────────────────────────────────────
    @staticmethod
    def get_clone_submenu(name: str, state: str) -> InlineKeyboardMarkup:
        """Individual clone control keyboard."""
        rows = []
        if state in ("STOPPED", "COOLDOWN"):
            rows.append([InlineKeyboardButton("⚡️ Start",    callback_data=f"start_{name}")])
        elif state == "RUNNING":
            rows.append([InlineKeyboardButton("❄️ Stop",     callback_data=f"stop_{name}")])
            rows.append([InlineKeyboardButton("♻️ Relaunch", callback_data=f"start_{name}")])
        else:
            # STARTING — show abort
            rows.append([InlineKeyboardButton("❌ Abort",    callback_data=f"stop_{name}")])
        rows.append([InlineKeyboardButton("📸 Screenshot",   callback_data=f"shot_{name}")])
        rows.append([InlineKeyboardButton("🏠 Back to Hub",  callback_data="nav_home")])
        return InlineKeyboardMarkup(rows)

    # ── HELP ──────────────────────────────────────────────────────────────
    @staticmethod
    def get_help_text() -> str:
        return (
            "🎮 *AEGIS V4.0 GUIDE*\n\n"
            "State Machine:\n"
            "  🌑 STOPPED → ⏳ STARTING → 🟢 RUNNING\n"
            "  🔵 COOLDOWN → re-enters queue\n\n"
            "• Watchdog is *blind* to non-RUNNING clones\n"
            "• asyncio.Lock enforces single-clone startup\n"
            "• 45s sequential gap between clones\n"
            "• 5-min grace after Step 4/4 before monitoring"
        )
