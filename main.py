# -*- coding: utf-8 -*-
# main.py — Project Aegis V4.0 State Machine Edition
import os
import sys
import enum
import asyncio
import logging
import time
from typing import Optional, Dict

# ── ABSOLUTE PATH LOCK ─────────────────────────────────────────────────────
_bot_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(_bot_dir)
sys.path.insert(0, _bot_dir)

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler,
    ContextTypes, MessageHandler, filters, CallbackQueryHandler
)
from telegram.error import TelegramError

from config_manager      import ConfigManager
from ui_manager          import UIManager
from monitor             import MonitorEngine
from injection_engine    import InjectionEngine
from bash_utils          import run_bash
from persistence_manager import PersistenceManager

# ═══════════════════════════════════════════════════════════════════════════
# VERSION
# ═══════════════════════════════════════════════════════════════════════════
VERSION = "5.0"

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
    format=f"%(asctime)s [{DEVICE_ID}/V{VERSION}] [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BOOT_LOG, encoding="utf-8"),
    ]
)
logger = logging.getLogger("AegisV40")

# ═══════════════════════════════════════════════════════════════════════════
# STATE MACHINE ENUM
# ═══════════════════════════════════════════════════════════════════════════
class CloneState(str, enum.Enum):
    STOPPED  = "STOPPED"   # Not running
    STARTING = "STARTING"  # 1/4 - 4/4 + 300s grace window
    RUNNING  = "RUNNING"   # Fully online, monitored by Watchdog

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
        self.bot      = bot
        self.chat_id  = chat_id
        self.buffer   = []
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
                    await self.bot.send_message(self.chat_id, f"<code>{batch}</code>", parse_mode="HTML")
                except Exception:
                    pass

    def stop(self):
        self._running = False


# ═══════════════════════════════════════════════════════════════════════════
# WATCHDOG — state-gated: only monitors RUNNING clones
# ═══════════════════════════════════════════════════════════════════════════
async def watchdog_loop(application: Application, bot_instance: "AegisBot"):
    """
    CRITICAL RULE: Watchdog is LEGALLY BLIND to any clone not in RUNNING state.
    Only RUNNING clones are checked for Frozen/Leaking conditions.
    """
    import re

    offline_strikes: Dict[str, int]   = {}
    last_action:     Dict[str, float] = {}

    # SILENT START: Skip everything for first 10 minutes
    boot_time = time.time()
    
    while True:
        await asyncio.sleep(60)
        
        # ══ 10-MINUTE TOTAL SILENCE ════════════════════════════════════
        if time.time() - boot_time < 600:
            logger.info(f"Watchdog: Silent Mode Active ({int(600 - (time.time() - boot_time))}s remaining)")
            continue
        try:
            now = time.time()

            for name, state in list(bot_instance.clone_states.items()):

                # ══ STATE GATE — The core fix ══════════════════════════════
                if state != CloneState.RUNNING:
                    # Log why we're skipping
                    if state == CloneState.STARTING:
                        logger.debug(f"Watchdog: [{name}] STARTING — ignored.")
                    continue

                # ── Post-action cooldown 60s ────────────────────────────
                if now - last_action.get(name, 0) < 60:
                    continue

                # ── Get status ──────────────────────────────────────────
                st = await MonitorEngine.get_clone_status(name)
                needs_action = False
                reason       = ""

                if "Offline" in st:
                    offline_strikes[name] = offline_strikes.get(name, 0) + 1
                    if offline_strikes[name] >= 3:
                        reason       = f"Offline ×{offline_strikes[name]}"
                        needs_action = True
                    else:
                        logger.info(f"Watchdog [{name}]: Offline strike {offline_strikes[name]}/3")
                else:
                    offline_strikes[name] = 0
                    m = re.search(r"Thr:\s*(\d+)", st)
                    if m:
                        thr = int(m.group(1))
                        if thr < 130:
                            reason       = f"Frozen (Thr:{thr})"
                            needs_action = True
                        elif thr > 500:
                            reason       = f"Leaking (Thr:{thr})"
                            needs_action = True

                if needs_action:
                    last_action[name]       = now
                    offline_strikes[name]   = 0
                    # Transition back to STOPPED first
                    bot_instance.set_state(name, CloneState.STOPPED)
                    logger.warning(f"Watchdog: [{name}] {reason}. Queueing restart…")
                    admin = bot_instance.config.admin_ids[0] if bot_instance.config.admin_ids else None
                    if admin:
                        try:
                            await application.bot.send_message(
                                admin,
                                f"🐕 *Watchdog*: `{name}` → {reason}\n🌑 STOPPED → queued relaunch…",
                                parse_mode="Markdown"
                            )
                        except TelegramError:
                            pass
                    # Kick into startup queue via background task
                    asyncio.create_task(bot_instance._enqueue_start(name, admin))

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
        self._dash_msg   = None
        self._streamer   = None
        self._log_handler = None
        self._console_on: bool = self.persistence.console_mode
        self._last_ui_update: float = 0.0

        # ── STATE MACHINE ─────────────────────────────────────────────────
        # {clone_name: CloneState}
        self.clone_states: Dict[str, CloneState] = {}

        # Uptime tracking: {clone_name: timestamp when RUNNING reached}
        self.running_since: Dict[str, float] = {}

        # asyncio.Lock — only ONE clone in STARTING state at a time
        self._start_lock = asyncio.Lock()

        # Initialize all known clones to STOPPED
        for c in self.config.clones_data:
            n = c.get("name")
            if n:
                self.clone_states[n] = CloneState.STOPPED

    # ── State helpers ─────────────────────────────────────────────────────
    def set_state(self, name: str, state: CloneState):
        old = self.clone_states.get(name, CloneState.STOPPED)
        self.clone_states[name] = state
        if state == CloneState.RUNNING:
            self.running_since[name] = time.time()
        elif old == CloneState.RUNNING:
            self.running_since.pop(name, None)
        logger.info(f"State [{name}]: {old.value} → {state.value}")

    # ── Admin guard ───────────────────────────────────────────────────────
    async def _is_admin(self, uid: int) -> bool:
        return uid in self.config.admin_ids

    # ─────────────────────────────────────────────────────────────────────
    # Handlers
    # ─────────────────────────────────────────────────────────────────────
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._is_admin(update.effective_user.id): return
        await update.message.reply_text(
            UIManager.get_welcome_text(DEVICE_ID),
            reply_markup=UIManager.get_main_keyboard(),
            parse_mode="Markdown"
        )

    async def cmd_console(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Last 15 lines of boot_log.txt."""
        if not await self._is_admin(update.effective_user.id): return
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
        if not await self._is_admin(update.effective_user.id): return
        t = update.message.text
        if   t == "📱 DEVICE": await self._open_device(update)
        elif t == "🤖 CLONES": await self.open_clones_hub(update)
        elif t == "⚙️ SYSTEM": await self._open_system(update)

    async def _open_device(self, update: Update):
        ram, cpu, temp = await MonitorEngine.get_system_stats()
        await update.message.reply_text(
            UIManager.format_dashboard(DEVICE_ID, ram, cpu, temp),
            reply_markup=UIManager.get_device_keyboard(),
            parse_mode="Markdown"
        )

    async def _open_system(self, update: Update):
        await update.message.reply_text(
            "⚙️ *SYSTEM*",
            reply_markup=UIManager.get_system_keyboard(self._console_on, self.persistence.auto_restore),
            parse_mode="Markdown"
        )

    async def open_clones_hub(self, update: Update):
        try:
            self.config.reload()
            text = self._build_hub_text()
            kb   = UIManager.get_clones_hub_keyboard(self.config.clones_data)
            self._dash_msg = await update.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"open_clones_hub error: {e}")
            await update.message.reply_text(f"❌ Hub error: {e}")

    def _build_hub_text(self) -> str:
        state_map  = {n: s.value for n, s in self.clone_states.items()}
        return UIManager.format_clones_hub(self.config.clones_data, state_map, self.running_since)

    async def refresh_dashboard(self, force=False):
        if not self._dash_msg: return
        now = time.time()
        # UI Throttle: 60 seconds unless forced
        if not force and (now - self._last_ui_update < 60):
            return
            
        try:
            text = self._build_hub_text()
            kb   = UIManager.get_clones_hub_keyboard(self.config.clones_data)
            await self._dash_msg.edit_text(text, reply_markup=kb, parse_mode="Markdown")
            self._last_ui_update = now
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────
    # Callback handler
    # ─────────────────────────────────────────────────────────────────────
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        if not await self._is_admin(q.from_user.id): return
        await q.answer()
        d    = q.data
        chat = q.message.chat_id
        try:
            if d == "nav_home":
                await q.message.reply_text(UIManager.get_welcome_text(DEVICE_ID),
                                           reply_markup=UIManager.get_main_keyboard(), parse_mode="Markdown")

            elif d == "toggle_restore":
                self.persistence.auto_restore = not self.persistence.auto_restore
                self.persistence.save()
                await q.edit_message_reply_markup(
                    UIManager.get_system_keyboard(self._console_on, self.persistence.auto_restore))

            elif d == "toggle_console":
                await self._toggle_console(context, chat)
                await q.edit_message_reply_markup(
                    UIManager.get_system_keyboard(self._console_on, self.persistence.auto_restore))

            elif d == "sys_sync":  await self._git_sync(chat)
            elif d == "sys_screenshot": await self._take_screenshot(q.message)
            elif d == "sys_help": await q.message.reply_text(UIManager.get_help_text(), parse_mode="Markdown")

            elif d == "mass_start":
                await context.bot.send_message(
                    chat,
                    "🚀 *Startup Queue Active*\n⏳ Clones launch sequentially (60s gap).",
                    parse_mode="Markdown"
                )
                asyncio.create_task(self._mass_start(chat))

            elif d == "mass_stop":
                for c in self.config.clones_data:
                    asyncio.create_task(self._stop_clone(c.get("name"), chat))
                await context.bot.send_message(chat, "❄️ Mass Stop issued.")

            elif d.startswith("start_"):
                name = d[6:]
                asyncio.create_task(self._enqueue_start(name, chat))

            elif d.startswith("stop_"):
                asyncio.create_task(self._stop_clone(d[5:], chat))

            elif d.startswith("shot_"):
                await self._take_screenshot(q.message)

            elif d.startswith("clone_"):
                name  = d[6:]
                state = self.clone_states.get(name, CloneState.STOPPED).value
                kb    = UIManager.get_clone_submenu(name, state)
                await context.bot.send_message(
                    chat,
                    f"⚙️ *{name.upper()}*\nState: `{state}`",
                    reply_markup=kb, parse_mode="Markdown"
                )

        except Exception as e:
            logger.error(f"Callback [{d}] error: {e}")
            try:
                await context.bot.send_message(chat, f"❌ Error: {e}")
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────
    # STATE MACHINE — Clone startup / stop logic
    # ─────────────────────────────────────────────────────────────────────
    async def _enqueue_start(self, name: Optional[str], chat_id):
        """
        Acquires the global asyncio.Lock before starting any clone.
        Guarantees only ONE clone is in STARTING state at a time.
        After 4/4 completes, waits 300s BEFORE transitioning to RUNNING.
        """
        if not name: return
        ci = self.config.get_clone(name)
        if not ci: return

        # If already starting or running, skip
        current = self.clone_states.get(name, CloneState.STOPPED)
        if current == CloneState.STARTING:
            logger.info(f"_enqueue_start: [{name}] already STARTING. Skip.")
            return

        async with self._start_lock:
            # ── 1. Force Identity & Inject ──────────────────────────────
            self.set_state(name, CloneState.STARTING)
            
            sm = None
            if chat_id and self.application:
                try:
                    sm = await self.application.bot.send_message(
                        chat_id, f"🚀 `{name}`: Запуск...", parse_mode="Markdown")
                except Exception:
                    pass

            # V5.0 Sequence: Cookie -> Launch only
            urls = self.config.servers_list
            ok = await InjectionEngine.inject_and_launch(
                name, ci.get("cookie"), urls[0] if urls else None, sm)

            if ok:
                self.set_state(name, CloneState.RUNNING)
                self.persistence.add_target(name, "RUNNING")
            else:
                self.set_state(name, CloneState.STOPPED)

        await self.refresh_dashboard(force=True)

    async def _mass_start(self, chat_id):
        """Sequential mass start via the _start_lock queue."""
        clones = self.config.clones_data
        for idx, c in enumerate(clones, 1):
            name = c.get("name")
            if not name: continue
            if chat_id and self.application:
                try:
                    await self.application.bot.send_message(
                        chat_id,
                        f"🚀 *Queue [{idx}/{len(clones)}]*: `{name}`",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
            await self._enqueue_start(name, chat_id)
            # 60s gap between each clone (inside lock releases)
            if idx < len(clones):
                await asyncio.sleep(60)

    async def _stop_clone(self, name: Optional[str], chat_id):
        if not name: return
        self.set_state(name, CloneState.STOPPED)
        self.persistence.remove_target(name)
        await InjectionEngine.stop(name)
        if chat_id and self.application:
            try:
                await self.application.bot.send_message(
                    chat_id, f"🌑 `{name}` stopped.", parse_mode="Markdown")
            except Exception:
                pass
        await self.refresh_dashboard(force=True)

    # ─────────────────────────────────────────────────────────────────────
    # Auto-resume on startup
    # ─────────────────────────────────────────────────────────────────────
    async def _auto_resume(self):
        """
        Read persistence.target_states, enqueue all clones whose
        expected state is RUNNING via the sequential startup queue.
        """
        await asyncio.sleep(5)
        targets = [
            n for n, ts in self.persistence.target_states.items()
            if ts == "RUNNING"
        ]
        if not targets:
            return
        admin_id = self.config.admin_ids[0] if self.config.admin_ids else None
        if admin_id and self.application:
            try:
                await self.application.bot.send_message(
                    admin_id,
                    f"♻️ *Auto-Resume*\nQueuing: `{', '.join(targets)}`",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        for n in targets:
            ci = self.config.get_clone(n)
            if ci:
                await self._enqueue_start(n, admin_id)
                await asyncio.sleep(60)

    # ─────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────
    async def _toggle_console(self, context, chat_id: int):
        self._console_on = not self._console_on
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
        buf = "/data/local/tmp/aegis_shot.png"
        try:
            ret, _, err = await run_bash(f"su -c 'screencap -p {buf} && chmod 644 {buf}'")
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
            ret, out, err = await run_bash(f"git -C {_bot_dir} pull --rebase 2>&1")
            result = (out or err or "(no output)")[:3000]
            if self.application:
                await self.application.bot.send_message(
                    chat_id, f"```\n{result}\n```\n✅ VERSION: {VERSION}", parse_mode="Markdown")
        except Exception as e:
            logger.error(f"git_sync error: {e}")

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Unhandled exception: {context.error}", exc_info=context.error)
        admin_id = self.config.admin_ids[0] if self.config.admin_ids else None
        if admin_id:
            try:
                await context.bot.send_message(
                    admin_id, f"🚨 *Global Error*\n`{context.error}`", parse_mode="Markdown")
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────
    # Entry-point
    # ─────────────────────────────────────────────────────────────────────
    async def run(self):
        # 1. CLEAN SLATE: NO PKILL. Bot assumes unique execution.
        logger.info(f"💎 PROJECT AEGIS V{VERSION} STARTING — {DEVICE_ID} (Clean Slate)")


        # 2. Build application
        self.application = ApplicationBuilder().token(self.config.bot_token).build()
        app = self.application

        # 3. Handlers
        app.add_handler(CommandHandler("start",   self.cmd_start))
        app.add_handler(CommandHandler("console", self.cmd_console))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        app.add_handler(CallbackQueryHandler(self.handle_callback))
        app.add_error_handler(self.error_handler)

        # 4. Start
        await app.initialize()
        await app.start()

        # 5. Launch Watchdog (state-gated, uses application explicitly)
        asyncio.create_task(watchdog_loop(app, self))

        # 6. Auto-resume
        asyncio.create_task(self._auto_resume())

        logger.info(f"💎 PROJECT AEGIS V{VERSION} ONLINE — {DEVICE_ID}")

        # 7. Poll
        await app.updater.start_polling(drop_pending_updates=True)

        # 8. Block
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
