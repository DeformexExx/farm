# -*- coding: utf-8 -*-
# main.py — Project Aegis V3.0 Industrial Rebuild
import os
import sys

# ── ABSOLUTE PATH LOCK ─────────────────────────────────────────────────────
_bot_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(_bot_dir)
sys.path.insert(0, _bot_dir)

import asyncio
import logging
import time
from typing import Optional
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler,
    ContextTypes, MessageHandler, filters, CallbackQueryHandler
)
from telegram.error import TelegramError

from config_manager     import ConfigManager
from ui_manager         import UIManager
from monitor            import MonitorEngine
from injection_engine   import InjectionEngine
from bash_utils         import run_bash
from persistence_manager import PersistenceManager

# ── VERSION (HARDCODED — DO NOT CHANGE) ────────────────────────────────────
VERSION = "3.0"

# ── DEVICE ID ──────────────────────────────────────────────────────────────
if len(sys.argv) < 2:
    print("❌  Usage: python main.py <DEVICE_ID>")
    sys.exit(1)

DEVICE_ID = sys.argv[1]
FARM_DIR  = _bot_dir

BOOT_LOG  = os.path.join(FARM_DIR, "boot_log.txt")

# ── LOGGING ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format=f"%(asctime)s [{DEVICE_ID}] [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BOOT_LOG, encoding="utf-8"),
    ]
)
logger = logging.getLogger("AegisV30")

# Version integrity check
if VERSION != "3.0":
    logger.critical(f"⚠️  VERSION MISMATCH: expected 3.0, got {VERSION}")

# ═══════════════════════════════════════════════════════════════════════════
# LOG STREAMER
# ═══════════════════════════════════════════════════════════════════════════
class TelegramLogHandler(logging.Handler):
    def __init__(self, streamer):
        super().__init__()
        self.streamer = streamer

    def emit(self, record):
        self.streamer.add_line(f"[{record.levelname[:3]}] {self.format(record)}")


class LogStreamer:
    def __init__(self, bot, chat_id: int):
        self.bot     = bot
        self.chat_id = chat_id
        self.buffer  = []
        self._running = False

    def add_line(self, text: str):
        self.buffer.append(text)

    async def start(self):
        self._running = True
        while self._running:
            await asyncio.sleep(2)
            if self.buffer:
                batch = "\n".join(self.buffer[-30:])
                self.buffer.clear()
                try:
                    await self.bot.send_message(
                        self.chat_id,
                        f"<code>{batch}</code>",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

    def stop(self):
        self._running = False


# ═══════════════════════════════════════════════════════════════════════════
# WATCHDOG — stand-alone coroutine (receives application explicitly)
# ═══════════════════════════════════════════════════════════════════════════
async def watchdog_loop(application: Application, bot_instance: "AegisBot"):
    """
    Runs forever. Checks every 60s.
    Uses application.bot — no NoneType risk.

    Anti-restart-loop rules:
      1. GRACE PERIOD: Skip any clone started within the last 300s.
      2. 3-STRIKE OFFLINE: Only restart after 3 consecutive Offline checks.
      3. TIMED COOLDOWN:   After a restart, ignore the clone for 300s.
    """
    import re

    # {clone_name: timestamp_of_last_restart}
    last_restart: dict[str, float] = {}
    # {clone_name: consecutive_offline_count}
    offline_strikes: dict[str, int] = {}

    while True:
        await asyncio.sleep(60)
        try:
            now = time.time()

            for name in list(bot_instance.active_clones):

                # ── 1. STARTUP GRACE PERIOD (300s) ──────────────────────────
                last_start = bot_instance.startup_times.get(name, 0)
                if now - last_start < 300:
                    logger.info(f"Watchdog: [{name}] in grace period ({int(300 - (now - last_start))}s left). Skip.")
                    offline_strikes[name] = 0  # reset strikes during grace
                    continue

                # ── 2. POST-RESTART COOLDOWN (300s) ─────────────────────────
                last_rst = last_restart.get(name, 0)
                if now - last_rst < 300:
                    continue

                # ── 3. STATUS CHECK ──────────────────────────────────────────
                st = await MonitorEngine.get_clone_status(name)
                needs_restart = False
                reason = ""

                if "Offline" in st:
                    offline_strikes[name] = offline_strikes.get(name, 0) + 1
                    if offline_strikes[name] >= 3:
                        reason = f"Offline x{offline_strikes[name]}"
                        needs_restart = True
                    else:
                        logger.info(f"Watchdog: [{name}] Offline strike {offline_strikes[name]}/3. Waiting…")
                else:
                    # Reset strike counter when online
                    offline_strikes[name] = 0
                    m = re.search(r"Thr:\s*(\d+)", st)
                    if m:
                        thr = int(m.group(1))
                        if thr < 130:
                            reason = f"Frozen (Thr:{thr})"
                            needs_restart = True
                        elif thr > 500:
                            reason = f"Leaking (Thr:{thr})"
                            needs_restart = True

                # ── 4. RESTART ───────────────────────────────────────────────
                if needs_restart:
                    last_restart[name] = now
                    offline_strikes[name] = 0
                    logger.warning(f"Watchdog: [{name}] {reason}. Restarting…")
                    admin_id = bot_instance.config.admin_ids[0] if bot_instance.config.admin_ids else None
                    if admin_id:
                        try:
                            await application.bot.send_message(
                                admin_id,
                                f"🐕 *Watchdog*: `{name}` → {reason}\n⚡️ Перезапуск…",
                                parse_mode="Markdown"
                            )
                        except TelegramError:
                            pass
                    await bot_instance._launch_clone(name, admin_id)

            await bot_instance.refresh_dashboard()

        except Exception as e:
            logger.error(f"watchdog_loop error: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# BOT CLASS
# ═══════════════════════════════════════════════════════════════════════════
class AegisBot:
    def __init__(self):
        self.config      = ConfigManager(DEVICE_ID, FARM_DIR)
        self.persistence = PersistenceManager(FARM_DIR)
        self.application: Optional[Application] = None
        self._dash_msg   = None      # last dashboard message (for edit)
        self._streamer   = None
        self._log_handler = None
        self._console_on: bool = self.persistence.console_mode

        # startup_times: {clone_name: timestamp} — watchdog skips for 300s
        self.startup_times: dict[str, float] = {}

        # Auto-resume: restore active_clones from persistence
        # Uses active_clones list (richer than targets dict)
        if self.persistence.auto_restore:
            saved = getattr(self.persistence, "active_clones", [])
            self.active_clones: set[str] = set(saved) if saved else set(getattr(self.persistence, "targets", {}).keys())
        else:
            self.active_clones = set()

    # ── Admin guard ────────────────────────────────────────────────────────
    async def _is_admin(self, uid: int) -> bool:
        return uid in self.config.admin_ids

    # ─────────────────────────────────────────────────────────────────────
    # Command / Text handlers
    # ─────────────────────────────────────────────────────────────────────
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._is_admin(update.effective_user.id):
            return
        await update.message.reply_text(
            UIManager.get_welcome_text(DEVICE_ID),
            reply_markup=UIManager.get_main_keyboard(),
            parse_mode="Markdown"
        )

    async def cmd_console(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display last 15 lines of boot_log.txt in a code block."""
        if not await self._is_admin(update.effective_user.id):
            return
        try:
            if os.path.exists(BOOT_LOG):
                with open(BOOT_LOG, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                tail = "".join(lines[-15:]).strip() or "(empty)"
            else:
                tail = "(boot_log.txt not found)"
            await update.message.reply_text(f"```\n{tail}\n```", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Console error: {e}")

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._is_admin(update.effective_user.id):
            return
        t = update.message.text
        if   t == "📱 DEVICE": await self._open_device(update)
        elif t == "🤖 CLONES": await self.open_clones_hub(update)
        elif t == "⚙️ SYSTEM": await self._open_system(update)

    # ─────────────────────────────────────────────────────────────────────
    # Menu openers
    # ─────────────────────────────────────────────────────────────────────
    async def _open_device(self, update: Update):
        ram, cpu, temp = await MonitorEngine.get_system_stats()
        await update.message.reply_text(
            UIManager.format_dashboard(DEVICE_ID, ram, cpu, temp),
            reply_markup=UIManager.get_device_keyboard(),
            parse_mode="Markdown"
        )

    async def _open_system(self, update: Update):
        cons = getattr(self, "_console_on", False)
        await update.message.reply_text(
            "⚙️ *SYSTEM*",
            reply_markup=UIManager.get_system_keyboard(cons, self.persistence.auto_restore),
            parse_mode="Markdown"
        )

    async def open_clones_hub(self, update: Update):
        try:
            self.config.reload()
            status_map = {}
            for c in self.config.clones_data:
                n = c.get("name")
                if n:
                    status_map[n] = await MonitorEngine.get_clone_status(n)

            # ── SAFE GETATTR FIX (Line 162 equivalent) ──────────────────
            targets = getattr(self.persistence, "targets", {})

            text = UIManager.format_clones_hub(self.config.clones_data, status_map, targets)
            kb   = UIManager.get_clones_hub_keyboard(self.config.clones_data)
            self._dash_msg = await update.message.reply_text(
                text, reply_markup=kb, parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"open_clones_hub error: {e}")
            await update.message.reply_text(f"❌ Ошибка Hub: {e}")

    async def refresh_dashboard(self):
        """Edit the last Hub message in-place."""
        if not self._dash_msg:
            return
        try:
            status_map = {}
            for c in self.config.clones_data:
                n = c.get("name")
                if n:
                    status_map[n] = await MonitorEngine.get_clone_status(n)

            targets = getattr(self.persistence, "targets", {})
            text = UIManager.format_clones_hub(self.config.clones_data, status_map, targets)
            kb   = UIManager.get_clones_hub_keyboard(self.config.clones_data)
            await self._dash_msg.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        except Exception:
            pass  # Message too old / unchanged → ignore silently

    # ─────────────────────────────────────────────────────────────────────
    # Callback handler
    # ─────────────────────────────────────────────────────────────────────
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        if not await self._is_admin(q.from_user.id):
            return
        await q.answer()
        d = q.data
        chat = q.message.chat_id

        try:
            if d == "nav_home":
                await q.message.reply_text(
                    UIManager.get_welcome_text(DEVICE_ID),
                    reply_markup=UIManager.get_main_keyboard(),
                    parse_mode="Markdown"
                )

            elif d == "toggle_restore":
                self.persistence.auto_restore = not self.persistence.auto_restore
                self.persistence.save()
                cons = getattr(self, "_console_on", False)
                await q.edit_message_reply_markup(
                    UIManager.get_system_keyboard(cons, self.persistence.auto_restore)
                )

            elif d == "toggle_console":
                await self._toggle_console(context, chat)
                cons = getattr(self, "_console_on", False)
                await q.edit_message_reply_markup(
                    UIManager.get_system_keyboard(cons, self.persistence.auto_restore)
                )

            elif d == "sys_sync":
                await self._git_sync(chat)

            elif d == "sys_screenshot":
                await self._take_screenshot(q.message)

            elif d == "sys_help":
                await q.message.reply_text(UIManager.get_help_text(), parse_mode="Markdown")

            elif d == "mass_start":
                await context.bot.send_message(chat, "🚀 Mass Start…")
                for c in self.config.clones_data:
                    await self._launch_clone(c.get("name"), chat)

            elif d == "mass_stop":
                for c in self.config.clones_data:
                    await self._kill_clone(c.get("name"), chat)
                await context.bot.send_message(chat, "❄️ Mass Stop done.")

            elif d.startswith("start_"):
                await self._launch_clone(d[6:], chat)

            elif d.startswith("stop_"):
                await self._kill_clone(d[5:], chat)

            elif d.startswith("clone_"):
                # Per-clone sub-menu
                name = d[6:]
                st = await MonitorEngine.get_clone_status(name)
                is_on = name in self.active_clones
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"⚡️ Relaunch {name}", callback_data=f"start_{name}"),
                     InlineKeyboardButton(f"❄️ Stop {name}",     callback_data=f"stop_{name}")],
                    [InlineKeyboardButton("🏠 Back to Hub", callback_data="nav_home")],
                ])
                is_active = "🟢" if "Online" in st or "Mem:" in st else "🌑"
                await context.bot.send_message(
                    chat,
                    f"⚙️ *{name.upper()} Controls*\n{is_active} Status: `{st}`",
                    reply_markup=kb,
                    parse_mode="Markdown"
                )

        except Exception as e:
            logger.error(f"Callback [{d}] error: {e}")
            try:
                await context.bot.send_message(chat, f"❌ Error: {e}")
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────
    # Clone logic
    # ─────────────────────────────────────────────────────────────────────
    async def _launch_clone(self, name: Optional[str], chat_id: Optional[int]):
        if not name:
            return
        ci = self.config.get_clone(name)
        if not ci:
            return
        self.persistence.add_target(name)
        self.active_clones.add(name)
        sm = None
        if chat_id and self.application:
            try:
                sm = await self.application.bot.send_message(chat_id, f"⏳ `{name}` — Запуск…", parse_mode="Markdown")
            except Exception:
                pass
        await InjectionEngine.inject_and_launch(name, ci.get("cookie"), None, sm)
        await asyncio.sleep(10)
        urls = self.config.servers_list
        await InjectionEngine.inject_and_launch(name, ci.get("cookie"), urls[0] if urls else None, sm)
        # ── STARTUP GRACE: Watchdog ignores this clone for 300s ─────────
        self.startup_times[name] = time.time()
        logger.info(f"_launch_clone: [{name}] grace period started (300s).")
        await self.refresh_dashboard()

    async def _kill_clone(self, name: Optional[str], chat_id: Optional[int]):
        if not name:
            return
        self.persistence.remove_target(name)
        self.active_clones.discard(name)
        await InjectionEngine.stop(name)
        if chat_id and self.application:
            try:
                await self.application.bot.send_message(chat_id, f"✅ `{name}` остановлен.", parse_mode="Markdown")
            except Exception:
                pass
        await self.refresh_dashboard()

    # ─────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────
    async def _toggle_console(self, context, chat_id: int):
        self._console_on = not getattr(self, "_console_on", False)
        if self._console_on:
            self._streamer    = LogStreamer(context.bot, chat_id)
            self._log_handler = TelegramLogHandler(self._streamer)
            logging.getLogger().addHandler(self._log_handler)
            asyncio.create_task(self._streamer.start())
        else:
            if self._log_handler:
                logging.getLogger().removeHandler(self._log_handler)
                self._log_handler = None
            if self._streamer:
                self._streamer.stop()
                self._streamer = None

    async def _take_screenshot(self, message):
        """Safe screenshot with absolute path and try-except."""
        buf = "/data/local/tmp/aegis_shot.png"
        try:
            ret, _, err = await run_bash(
                f"su -c 'screencap -p {buf} && chmod 644 {buf}'"
            )
            if ret != 0:
                await message.reply_text(f"❌ screencap failed: {err}")
                return
            with open(buf, "rb") as f:
                await message.reply_photo(photo=f, caption=f"📸 {DEVICE_ID}")
        except Exception as e:
            logger.error(f"Screenshot error: {e}")
            await message.reply_text(f"❌ Screenshot Exception: {e}")

    async def _git_sync(self, chat_id: int):
        try:
            if self.application:
                await self.application.bot.send_message(chat_id, "♻️ Git Sync…")
            ret, out, err = await run_bash("git -C " + _bot_dir + " pull --rebase 2>&1")
            result = out or err or "(no output)"
            # Version check post-sync
            ver_check = f"\n✅ Local VERSION confirmed: {VERSION}" if VERSION == "3.0" else f"\n⚠️ VERSION MISMATCH: {VERSION}"
            if self.application:
                await self.application.bot.send_message(chat_id, f"```\n{result[:3000]}\n```{ver_check}", parse_mode="Markdown")
        except Exception as e:
            logger.error(f"git_sync error: {e}")

    # ─────────────────────────────────────────────────────────────────────
    # Global error handler
    # ─────────────────────────────────────────────────────────────────────
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Unhandled exception: {context.error}", exc_info=context.error)
        admin_id = self.config.admin_ids[0] if self.config.admin_ids else None
        if admin_id:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"🚨 *Global Error*\n`{context.error}`",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────
    # Entry-point
    # ─────────────────────────────────────────────────────────────────────
    async def run(self):
        # 1. Kill duplicate python processes
        await run_bash(
            f"su -c 'pgrep -f \"python.*main.py\" | grep -v {os.getpid()} | xargs kill -9' 2>/dev/null"
        )

        # 2. Build application
        self.application = ApplicationBuilder().token(self.config.bot_token).build()

        # 3. Register handlers
        app = self.application
        app.add_handler(CommandHandler("start",   self.cmd_start))
        app.add_handler(CommandHandler("console", self.cmd_console))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        app.add_handler(CallbackQueryHandler(self.handle_callback))
        app.add_error_handler(self.error_handler)  # Global error handler

        # 4. Start
        await app.initialize()
        await app.start()

        # 5. Launch Watchdog with explicit application reference (fix NoneType)
        asyncio.create_task(watchdog_loop(app, self))

        # 5b. Auto-resume: relaunch all saved active clones after 5s
        if self.active_clones:
            async def _auto_resume():
                await asyncio.sleep(5)
                admin_id = self.config.admin_ids[0] if self.config.admin_ids else None
                if admin_id:
                    names = ", ".join(sorted(self.active_clones))
                    try:
                        await app.bot.send_message(admin_id, f"♻️ Auto-resume: запускаю `{names}`…", parse_mode="Markdown")
                    except Exception:
                        pass
                for n in list(self.active_clones):
                    await self._launch_clone(n, admin_id)
            asyncio.create_task(_auto_resume())

        logger.info(f"💎 PROJECT AEGIS V{VERSION} ONLINE — {DEVICE_ID}")

        # 6. Poll (drop stale messages)
        await app.updater.start_polling(drop_pending_updates=True)

        # 7. Block forever
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await app.stop()
            await app.shutdown()


# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        asyncio.run(AegisBot().run())
    except Exception as e:
        logger.critical(f"Fatal startup error: {e}")
