# -*- coding: utf-8 -*-
# main.py — Project Aegis V8.2 Direct Kernel Thread Counting
import os
import sys
import enum
import asyncio
import logging
import time
import signal
import threading
from typing import Optional, Dict
from datetime import datetime, timedelta

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
VERSION = "8.2"

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
logger = logging.getLogger("AegisV82")

# ═══════════════════════════════════════════════════════════════════════════
# SYSTEM ANCHOR ARCHITECTURE — V7.0 Deep Daemonization
# ═══════════════════════════════════════════════════════════════════════════

# ── PID LOCK FILE ─────────────────────────────────────────────────────────
LOCK_FILE = os.path.join(FARM_DIR, f".aegis_{DEVICE_ID}.lock")

def acquire_pid_lock() -> bool:
    """
    V7.0: PID-Locking to prevent ghost duplicates.
    Returns True if lock acquired, False if another instance is running.
    """
    import os
    current_pid = os.getpid()
    
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                old_pid = f.read().strip()
            if old_pid:
                # Check if old process is still alive
                try:
                    os.kill(int(old_pid), 0)
                    # Process exists - we are a ghost
                    logger.critical(f"🚫 ANCHOR: Another Aegis instance running (PID {old_pid}). Exiting.")
                    return False
                except (ProcessLookupError, ValueError, OSError):
                    # Process is dead, we can take over
                    pass
        except Exception:
            pass
    
    # Write our PID
    with open(LOCK_FILE, "w") as f:
        f.write(str(current_pid))
    logger.info(f"⚓ ANCHOR: PID lock acquired ({current_pid})")
    return True

def release_pid_lock():
    """Release the PID lock on shutdown."""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
            logger.info("⚓ ANCHOR: PID lock released")
    except Exception:
        pass

# ── SIGNAL HANDLERS ───────────────────────────────────────────────────────
def _signal_handler(signum, frame):
    """
    V7.0: Ignore SIGHUP and SIGTERM from Android LMK.
    Only exit on SIGINT (Ctrl+C) or explicit shutdown.
    """
    sig_name = signal.Signals(signum).name
    logger.warning(f"⚓ ANCHOR: Signal {sig_name} received and IGNORED (LMK immunity)")

# Register LMK-resistant signal handlers
try:
    signal.signal(signal.SIGHUP, _signal_handler)   # Hang up - ignore
    signal.signal(signal.SIGTERM, _signal_handler)  # Terminate - ignore
    # SIGINT (Ctrl+C) and SIGKILL remain unhandled for emergency exit
except Exception as e:
    logger.warning(f"⚓ ANCHOR: Signal handler setup failed: {e}")

# ── SYSTEM PRIORITY & OOM ─────────────────────────────────────────────────
async def anchor_to_system():
    """
    V8.0 GOD MODE: System-Critical Service Level.
    - Set OOM score to -1000 (unkillable even if system exploding)
    - Elevate CPU priority to maximum
    - Apply same protection to child ADB/subprocesses
    """
    pid = os.getpid()
    
    # V8.0 GOD MODE: OOM Score Adjustment (-1000 = absolutely never kill)
    oom_path = f"/proc/{pid}/oom_score_adj"
    try:
        ret, _, _ = await run_bash(f"su -c 'echo -1000 > {oom_path}'")
        if ret == 0:
            logger.info("👑 V8.0 GOD MODE: OOM score set to -1000 (IMMORTAL)")
        else:
            logger.warning("👑 V8.0 GOD MODE: Failed to set OOM score (requires root)")
    except Exception as e:
        logger.warning(f"👑 V8.0 GOD MODE: OOM adjustment error: {e}")
    
    # V8.0: Maximum CPU Priority (renice -20 = real-time priority)
    try:
        ret, _, _ = await run_bash(f"su -c 'renice -n -20 -p {pid}'")
        if ret == 0:
            logger.info("👑 V8.0 GOD MODE: CPU priority at MAXIMUM (renice -20)")
        else:
            # Fallback to -15 if -20 fails
            await run_bash(f"su -c 'renice -n -15 -p {pid}'")
            logger.info("👑 V8.0 GOD MODE: CPU priority at HIGH (renice -15)")
    except Exception as e:
        logger.warning(f"👑 V8.0 GOD MODE: renice error: {e}")
    
    # V8.0: CPU Isolation (dedicate core 0 to bot)
    try:
        ret, _, _ = await run_bash(f"su -c 'taskset -cp 0 {pid}' 2>/dev/null")
        if ret == 0:
            logger.info("👑 V8.0 GOD MODE: CPU isolation on core 0")
    except Exception:
        pass
    
    # V8.0: Protect all existing child processes
    await protect_child_processes()
    
    # V8.0: Set I/O priority to real-time
    try:
        await run_bash(f"su -c 'ionice -c 1 -n 0 -p {pid}' 2>/dev/null")
        logger.info("👑 V8.0 GOD MODE: I/O priority set to REAL-TIME")
    except Exception:
        pass

async def protect_child_processes():
    """
    V8.0: Apply OOM protection to all child ADB and monitoring processes.
    """
    try:
        # Find all child processes of the bot
        ret, stdout, _ = await run_bash(f"su -c 'pgrep -P {os.getpid()} 2>/dev/null || echo NONE'")
        if ret == 0 and stdout.strip() and stdout.strip() != "NONE":
            child_pids = stdout.strip().split('\n')
            for child_pid in child_pids:
                if child_pid.strip():
                    # Apply -1000 OOM score to each child
                    await run_bash(f"su -c 'echo -1000 > /proc/{child_pid.strip()}/oom_score_adj 2>/dev/null'")
            logger.info(f"👑 V8.0 GOD MODE: Applied OOM protection to {len(child_pids)} child processes")
    except Exception as e:
        logger.debug(f"👑 V8.0 GOD MODE: Child protection skipped: {e}")

# ═══════════════════════════════════════════════════════════════════════════
# V8.0 EMERGENCY RAM RECOVERY — STOP/CONT Protocol
# ═══════════════════════════════════════════════════════════════════════════
_emergency_stopped: Dict[str, float] = {}  # Track clones in STOP state

async def emergency_ram_recovery(bot_instance: "AegisBot"):
    """
    V8.0 HARD-CORE: When RAM < 100MB, stop being polite.
    Uses kill -STOP to freeze least important clone entirely.
    """
    try:
        import psutil
        mem = psutil.virtual_memory()
        available_mb = mem.available // (1024 * 1024)
        
        if available_mb < 100:  # Less than 100MB available
            logger.critical(f"🚨 V8.0 EMERGENCY: RAM critically low ({available_mb}MB available)")
            
            # Find the least important running clone (oldest uptime)
            victim = None
            oldest_time = float('inf')
            
            for name, state in bot_instance.clone_states.items():
                if state == CloneState.RUNNING:
                    start_time = bot_instance.running_since.get(name, time.time())
                    if start_time < oldest_time:
                        oldest_time = start_time
                        victim = name
            
            if victim:
                pid = await InjectionEngine.get_clone_pid(victim)
                if pid:
                    # STOP the clone - freeze its RAM usage entirely
                    await run_bash(f"su -c 'kill -STOP {pid}'")
                    _emergency_stopped[victim] = time.time()
                    logger.critical(f"🚨 V8.0 EMERGENCY: STOPPED {victim} (PID {pid}) to freeze RAM")
                    
                    # Notify admin
                    admin_id = bot_instance.config.admin_ids[0] if bot_instance.config.admin_ids else None
                    if admin_id and bot_instance.application:
                        try:
                            await bot_instance.application.bot.send_message(
                                admin_id,
                                f"🚨 *EMERGENCY RAM RECOVERY*\n`{victim}` STOPPED (frozen)\nAvailable: {available_mb}MB",
                                parse_mode="Markdown"
                            )
                        except Exception:
                            pass
                    
                    # Schedule resume after 30 seconds
                    asyncio.create_task(_resume_clone_after_emergency(bot_instance, victim, pid))
                    
    except ImportError:
        pass
    except Exception as e:
        logger.error(f"🚨 V8.0 EMERGENCY: Recovery error: {e}")

async def _resume_clone_after_emergency(bot_instance: "AegisBot", name: str, pid: str):
    """
    Resume a clone after 30 second emergency freeze.
    """
    await asyncio.sleep(30)
    
    # Check if still in emergency stopped state
    if name in _emergency_stopped:
        del _emergency_stopped[name]
        
        # Try to resume
        try:
            await run_bash(f"su -c 'kill -CONT {pid}'")
            logger.info(f"🚨 V8.0 EMERGENCY: RESUMED {name} (PID {pid})")
        except Exception as e:
            logger.error(f"🚨 V8.0 EMERGENCY: Failed to resume {name}: {e}")
            # If resume fails, mark as stopped
            bot_instance.set_state(name, CloneState.STOPPED)

# ═══════════════════════════════════════════════════════════════════════════
# V8.0 INTERFACE ISOLATION — Pure Shell Mode
# ═══════════════════════════════════════════════════════════════════════════
_system_ui_crashed = False

async def check_system_ui_health() -> bool:
    """
    V8.0: Check if SystemUI is responsive.
    Returns True if healthy, False if crashed.
    """
    try:
        # Check if system_server is running
        ret, stdout, _ = await run_bash("su -c 'service list | grep system_server'")
        if ret != 0 or not stdout.strip():
            return False
        
        # Additional check: can we get window info
        ret2, _, _ = await run_bash("su -c 'dumpsys window | head -5' 2>/dev/null")
        if ret2 != 0:
            return False
            
        return True
    except Exception:
        return False

async def enter_pure_shell_mode(bot_instance: "AegisBot"):
    """
    V8.0: Switch to Pure Shell Mode when SystemUI crashes.
    Continue managing clones via direct am commands, ignoring frozen screen.
    """
    global _system_ui_crashed
    
    if _system_ui_crashed:
        return  # Already in shell mode
    
    _system_ui_crashed = True
    logger.critical("👁️ V8.0 INTERFACE ISOLATION: SystemUI CRASHED — Entering Pure Shell Mode")
    
    # Notify admin
    admin_id = bot_instance.config.admin_ids[0] if bot_instance.config.admin_ids else None
    if admin_id and bot_instance.application:
        try:
            await bot_instance.application.bot.send_message(
                admin_id,
                "👁️ *INTERFACE ISOLATION*\nSystemUI crashed.\nSwitched to Pure Shell Mode.\nRoblox clones continue running headless.",
                parse_mode="Markdown"
            )
        except Exception:
            pass

async def exit_pure_shell_mode(bot_instance: "AegisBot"):
    """
    V8.0: Exit Pure Shell Mode when SystemUI recovers.
    """
    global _system_ui_crashed
    
    if not _system_ui_crashed:
        return  # Already in normal mode
    
    _system_ui_crashed = False
    logger.info("👁️ V8.0 INTERFACE ISOLATION: SystemUI RECOVERED — Exiting Pure Shell Mode")

# ═══════════════════════════════════════════════════════════════════════════
# V8.0 PID-LOCK RECOVERY — Re-adoption Protocol
# ═══════════════════════════════════════════════════════════════════════════
async def scan_and_adopt_clones(bot_instance: "AegisBot"):
    """
    V8.0: After crash recovery, re-adopt existing Roblox windows instead of launching new ones.
    """
    logger.info("🔍 V8.0 PID-LOCK RECOVERY: Scanning for existing clones to adopt...")
    
    adopted = 0
    for c in bot_instance.config.clones_data:
        name = c.get("name")
        if not name:
            continue
        
        # Check if clone is already running
        pid = await InjectionEngine.get_clone_pid(name)
        if pid:
            # Verify it's actually a Roblox process
            ret, cmdline, _ = await run_bash(f"su -c 'cat /proc/{pid}/cmdline 2>/dev/null || echo UNKNOWN'")
            if ret == 0 and f"com.roblox.{name}" in cmdline:
                # Adopt this clone
                bot_instance.set_state(name, CloneState.RUNNING)
                adopted += 1
                logger.info(f"🔍 V8.0 PID-LOCK RECOVERY: Adopted {name} (PID {pid})")
    
    if adopted > 0:
        logger.info(f"🔍 V8.0 PID-LOCK RECOVERY: Adopted {adopted} existing clones")
        # Notify admin
        admin_id = bot_instance.config.admin_ids[0] if bot_instance.config.admin_ids else None
        if admin_id and bot_instance.application:
            try:
                await bot_instance.application.bot.send_message(
                    admin_id,
                    f"🔍 *PID-LOCK RECOVERY*\nAdopted {adopted} existing clones after restart",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
    else:
        logger.info("🔍 V8.0 PID-LOCK RECOVERY: No existing clones found to adopt")

# ── SURGICAL TRIM ─────────────────────────────────────────────────────────
async def surgical_trim(bot_instance: "AegisBot"):
    """
    V7.0: Memory Pressure Relief.
    Before RAM hits red zone, trim idle clones without killing.
    Uses 'am set-inactive' to free GPU buffers.
    """
    try:
        import psutil
        mem = psutil.virtual_memory()
        
        # If RAM > 85%, trigger surgical trim
        if mem.percent > 85:
            logger.warning(f"⚓ ANCHOR: Memory pressure detected ({mem.percent}%), initiating surgical trim...")
            
            for c in bot_instance.config.clones_data:
                name = c.get("name")
                if not name:
                    continue
                    
                state = bot_instance.clone_states.get(name, CloneState.STOPPED)
                package = f"com.roblox.{name}"
                
                # Only trim RUNNING clones that haven't been active recently
                if state == CloneState.RUNNING:
                    # Check if clone has been running for > 5 minutes (not newly started)
                    runtime = time.time() - bot_instance.running_since.get(name, time.time())
                    if runtime > 300:  # 5 minutes
                        # Set inactive to free GPU buffers without killing
                        await run_bash(f"su -c 'am set-inactive {package} true'")
                        logger.info(f"⚓ ANCHOR: Surgical trim applied to {name}")
                        
            # Also drop system caches
            await InjectionEngine.clear_memory()
            
    except ImportError:
        pass  # psutil not available
    except Exception as e:
        logger.error(f"⚓ ANCHOR: Surgical trim error: {e}")

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
# TELEMETRY DAEMON — V8.2 Direct Kernel Thread Counting (10s interval)
# ═══════════════════════════════════════════════════════════════════════════
async def telemetry_daemon(bot_instance: "AegisBot"):
    """
    V8.2: Direct Kernel Thread Counting every 10 seconds.
    Uses /proc/[PID]/status for real-time thread telemetry.
    """
    logger.info("📊 V8.2 TELEMETRY: Kernel Scanner started (10s interval)")
    cycle = 0
    
    while True:
        await asyncio.sleep(10)  # 10 second interval
        cycle += 1
        
        try:
            for name, state in list(bot_instance.clone_states.items()):
                if state == CloneState.RUNNING:
                    pid = await InjectionEngine.get_clone_pid(name)
                    if pid:
                        # V8.2: Collect thread count via kernel scanner
                        thread_count, source = await MonitorEngine.get_thread_count_kernel(pid)
                        MonitorEngine.record_thread_history(name, thread_count)
                        
                        # Collect CPU usage
                        cpu = await MonitorEngine.get_clone_cpu_usage(name, pid)
                        if cpu >= 0:
                            MonitorEngine.record_cpu_history(name, cpu)
                        
                        # Log every 6 cycles (1 minute)
                        if cycle % 6 == 0:
                            logger.debug(f"📊 V8.2 [{name}] Threads: {thread_count} ({source}), CPU: {cpu:.1f}%")
                    else:
                        # PID lost but state is RUNNING - mark STOPPED
                        logger.warning(f"📊 V8.2 [{name}] PID lost during telemetry, marking STOPPED")
                        bot_instance.set_state(name, CloneState.STOPPED)
                        
        except Exception as e:
            logger.error(f"📊 V8.2 TELEMETRY error: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# FORCE REDRAW — V7.1 System UI Bypass
# ═══════════════════════════════════════════════════════════════════════════
async def force_redraw() -> bool:
    """
    V7.1: Force UI redraw to unfreeze Android Launcher/SystemUI.
    Uses service call activity 42 or am restart for safe system nudge.
    """
    try:
        # Method 1: Send refresh broadcast (safe, doesn't kill anything)
        await run_bash("su -c 'am broadcast -a android.intent.action.SCREEN_OFF'")
        await asyncio.sleep(0.5)
        await run_bash("su -c 'am broadcast -a android.intent.action.SCREEN_ON'")
        
        # Method 2: Activity manager nudge
        await run_bash("su -c 'service call activity 42 i32 0' 2>/dev/null || true")
        
        # Method 3: Input keyevent to wake up the system
        await run_bash("su -c 'input keyevent 82' 2>/dev/null || true")  # Menu key
        
        logger.info("🔄 FORCE REDRAW: System UI nudge executed")
        return True
    except Exception as e:
        logger.error(f"🔄 FORCE REDRAW failed: {e}")
        return False
async def keepalive_daemon(bot_instance: "AegisBot"):
    """
    V8.0 HARD-CORE: System-Critical Keep-Alive with Interface Isolation.
    Detects SystemUI crashes and switches to Pure Shell Mode.
    Triggers emergency RAM recovery when needed.
    """
    global _system_ui_crashed
    
    logger.info("👑 V8.0 GOD MODE: Keep-Alive Daemon started")
    heartbeat_count = 0
    ui_check_counter = 0
    
    while True:
        await asyncio.sleep(30)  # Check every 30 seconds
        heartbeat_count += 1
        ui_check_counter += 1
        
        try:
            # V8.0: SystemUI Health Check every 60 seconds
            if ui_check_counter >= 2:
                ui_check_counter = 0
                ui_healthy = await check_system_ui_health()
                
                if not ui_healthy and not _system_ui_crashed:
                    # SystemUI crashed - enter Pure Shell Mode
                    await enter_pure_shell_mode(bot_instance)
                elif ui_healthy and _system_ui_crashed:
                    # SystemUI recovered - exit Pure Shell Mode
                    await exit_pure_shell_mode(bot_instance)
            
            # 1. Headless heartbeat - input tap with device ID (bypasses UI)
            await run_bash("su -c 'input -d 0 tap 540 960' 2>/dev/null || su -c 'input tap 540 960' 2>/dev/null || true")
            
            # 2. Check system health via dumpsys (works without SystemUI)
            ret, stdout, _ = await run_bash("su -c 'dumpsys activity activities | grep -E \"mFocused|mResumed\"' 2>/dev/null || echo NONE")
            system_responsive = ret == 0 and stdout.strip() != "NONE"
            
            # 3. V8.0: Memory pressure check — EMERGENCY PROTOCOL
            await emergency_ram_recovery(bot_instance)
            
            # 4. Memory pressure check & surgical trim (fallback)
            if heartbeat_count % 6 == 0:  # Every 3 minutes
                await surgical_trim(bot_instance)
            
            # 5. V8.0: Protect child processes periodically
            if heartbeat_count % 10 == 0:  # Every 5 minutes
                await protect_child_processes()
            
            # 6. PID validation for all clones
            for name, state in list(bot_instance.clone_states.items()):
                if state == CloneState.RUNNING:
                    # Use dumpsys for verification (works even if UI crashed)
                    verified = await MonitorEngine.verify_clone_via_dumpsys(name)
                    if not verified:
                        pid = await InjectionEngine.get_clone_pid(name)
                        if not pid:
                            logger.warning(f"👑 V8.0: [{name}] Lost via dumpsys & pidof, marking STOPPED")
                            bot_instance.set_state(name, CloneState.STOPPED)
            
            # 7. Periodic logging
            if heartbeat_count % 10 == 0:  # Every 5 minutes
                mode_str = "SHELL-MODE" if _system_ui_crashed else "NORMAL"
                logger.info(f"👑 V8.0 Keep-Alive #{heartbeat_count} [Mode: {mode_str}]")
                        
        except Exception as e:
            logger.error(f"👑 V8.0 Keep-Alive error: {e}")
            await asyncio.sleep(5)


# ═══════════════════════════════════════════════════════════════════════════
# DAILY RESTART DAEMON — V7.4 Scheduled Maintenance (05:00 local time)
# ═══════════════════════════════════════════════════════════════════════════
async def daily_restart_daemon(bot_instance: "AegisBot"):
    """
    V7.4: Automatically restarts all running clones at 05:00 local time.
    Each restarted clone gets the standard 600s immunity window after launch.
    """
    from datetime import datetime, timedelta
    
    logger.info("🕐 DAILY RESTART: Daemon started (V7.4 - 05:00 local time)")
    
    while True:
        now = datetime.now()
        # Calculate time until next 05:00
        target = now.replace(hour=5, minute=0, second=0, microsecond=0)
        if now >= target:
            # Already past 05:00 today, schedule for tomorrow
            target = target + timedelta(days=1)
        
        wait_seconds = (target - now).total_seconds()
        logger.info(f"🕐 DAILY RESTART: Next restart at {target.strftime('%Y-%m-%d %H:%M')} (in {int(wait_seconds/3600)}h {int((wait_seconds%3600)/60)}m)")
        
        await asyncio.sleep(wait_seconds)
        
        # It's 05:00 - perform daily restart
        logger.info("🕐 DAILY RESTART: Triggering sequential restart of all running clones")
        admin_id = bot_instance.config.admin_ids[0] if bot_instance.config.admin_ids else None
        
        if admin_id and bot_instance.application:
            try:
                await bot_instance.application.bot.send_message(
                    admin_id,
                    "🕐 *Daily Restart (05:00)*\nRestarting all running clones sequentially...",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        
        # Get list of currently running clones
        running_clones = [
            name for name, state in bot_instance.clone_states.items()
            if state == CloneState.RUNNING
        ]
        
        if not running_clones:
            logger.info("🕐 DAILY RESTART: No clones currently running")
            if admin_id and bot_instance.application:
                try:
                    await bot_instance.application.bot.send_message(
                        admin_id, "🕐 Daily Restart: No clones were running", parse_mode="Markdown"
                    )
                except Exception:
                    pass
            continue
        
        # Sequential restart with 60s gap (same as mass_start)
        for idx, name in enumerate(running_clones, 1):
            logger.info(f"🕐 DAILY RESTART: [{idx}/{len(running_clones)}] Restarting {name}")
            
            if admin_id and bot_instance.application:
                try:
                    await bot_instance.application.bot.send_message(
                        admin_id,
                        f"🕐 *Daily Restart [{idx}/{len(running_clones)}]*: `{name}`",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
            
            # Stop the clone (this triggers Smart Pause)
            await bot_instance._stop_clone(name, admin_id)
            
            # Wait for Smart Pause to complete (30s) + small buffer
            await asyncio.sleep(35)
            
            # Start the clone (600s immunity window applied automatically)
            await bot_instance._enqueue_start(name, admin_id)
            
            # 60s gap between clones
            if idx < len(running_clones):
                await asyncio.sleep(60)
        
        logger.info("🕐 DAILY RESTART: Complete")
        if admin_id and bot_instance.application:
            try:
                await bot_instance.application.bot.send_message(
                    admin_id,
                    f"✅ *Daily Restart Complete*\n{len(running_clones)} clones restarted with 600s immunity",
                    parse_mode="Markdown"
                )
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════
# WATCHDOG — V8.2 Direct Kernel Thread Counting
# ═══════════════════════════════════════════════════════════════════════════
async def watchdog_loop(application: Application, bot_instance: "AegisBot"):
    """
    V8.2: Direct Kernel Thread Counting — Reliable freeze detection.
    Features: Threads < 50 for 5min triggers restart, /proc disappearance detection.
    CRITICAL RULE: Watchdog is LEGALLY BLIND to any clone not in RUNNING state.
    """
    import re

    offline_strikes: Dict[str, int]   = {}
    last_action:     Dict[str, float] = {}
    freeze_strikes:  Dict[str, int]   = {}  # V7.1: Track freeze detection confidence

    # SILENT START: Skip everything for first 10 minutes
    boot_time = time.time()
    
    logger.info("🔬 V8.2 WATCHDOG: Direct Kernel Thread Counting initialized")
    
    while True:
        await asyncio.sleep(60)
        
        # ══ 10-MINUTE TOTAL SILENCE ════════════════════════════════════
        if time.time() - boot_time < 600:
            logger.info(f"🔬 V8.2: Silent Mode ({int(600 - (time.time() - boot_time))}s remaining)")
            continue
        try:
            now = time.time()

            for name, state in list(bot_instance.clone_states.items()):

                # ══ STATE GATE — The core fix ══════════════════════════════
                if state != CloneState.RUNNING:
                    if state == CloneState.STARTING:
                        logger.debug(f"⚓ ANCHOR: Watchdog [{name}] STARTING — ignored.")
                    continue

                # ── V7.3: Smart Pause check ───────────────────────────────
                pause_until = bot_instance.manual_pause.get(name, 0)
                pause_remaining = pause_until - time.time()
                if pause_remaining > 0:
                    logger.debug(f"⚓ ANCHOR: Watchdog [{name}] SMART PAUSE ({int(pause_remaining)}s remaining) — skipped")
                    continue

                # ── Post-action cooldown 60s ────────────────────────────
                if now - last_action.get(name, 0) < 60:
                    continue

                # ── V7.2: 600-second immunity window ────────────────────
                start_time = bot_instance.clone_start_time.get(name, 0)
                immunity_remaining = 600 - (now - start_time)
                if immunity_remaining > 0:
                    logger.debug(f"⚓ ANCHOR: Watchdog [{name}] IMMUNITY WINDOW ({int(immunity_remaining)}s remaining) — skipped")
                    continue

                # ── Get status (dual verification) ────────────────────────
                st = await MonitorEngine.get_clone_status(name)
                
                # V7.0: Backup verification via dumpsys if /proc fails
                if "Offline" in st or "Error" in st:
                    dumpsys_ok = await MonitorEngine.verify_clone_via_dumpsys(name)
                    if dumpsys_ok:
                        # Clone is actually running, /proc just unavailable
                        continue
                
                # V8.2 KERNEL-BASED FREEZE DETECTION — Threads < 50 for 5 minutes
                needs_action = False
                reason       = ""
                
                # Check thread-based freeze (Threads < 50 for 5 minutes)
                if MonitorEngine.is_thread_frozen(name, threshold=50):
                    freeze_strikes[name] = freeze_strikes.get(name, 0) + 1
                    if freeze_strikes[name] >= 3:  # V8.2: 3 strikes before action
                        reason = f"FROZEN (Threads<50 for 5min ×{freeze_strikes[name]})"
                        needs_action = True
                    else:
                        logger.warning(f"🧊 V8.2 [{name}] Freeze strike {freeze_strikes[name]}/3 (Threads<50)")
                
                # Check CPU-based freeze (<1% for 120s)
                elif MonitorEngine.is_cpu_frozen(name):
                    freeze_strikes[name] = freeze_strikes.get(name, 0) + 1
                    if freeze_strikes[name] >= 3:  # V8.2: 3 strikes before action
                        reason = f"FROZEN (CPU stall ×{freeze_strikes[name]})"
                        needs_action = True
                    else:
                        logger.warning(f"🧊 V8.2 [{name}] Freeze strike {freeze_strikes[name]}/3 (CPU stall)")
                else:
                    freeze_strikes[name] = 0  # Reset on healthy readings

                # Standard offline detection
                if not needs_action:
                    if "Offline" in st:
                        offline_strikes[name] = offline_strikes.get(name, 0) + 1
                        if offline_strikes[name] >= 3:
                            reason       = f"Offline ×{offline_strikes[name]}"
                            needs_action = True
                        else:
                            logger.info(f"⚓ ANCHOR: Watchdog [{name}] Offline strike {offline_strikes[name]}/3")
                    else:
                        offline_strikes[name] = 0
                        # Traditional thread count bounds check
                        m = re.search(r"Thr:\s*(\d+)", st)
                        if m:
                            thr = int(m.group(1))
                            if 0 < thr < 130:  # Only trigger if > 0 (0 handled by freeze detection)
                                reason       = f"Low threads (Thr:{thr})"
                                needs_action = True
                            elif thr > 500:
                                reason       = f"Leaking (Thr:{thr})"
                                needs_action = True

                if needs_action:
                    last_action[name]       = now
                    offline_strikes[name]   = 0
                    freeze_strikes[name]    = 0
                    bot_instance.set_state(name, CloneState.STOPPED)
                    logger.warning(f"⚓ ANCHOR: Watchdog [{name}] {reason}. Queueing restart…")
                    admin = bot_instance.config.admin_ids[0] if bot_instance.config.admin_ids else None
                    if admin:
                        try:
                            await application.bot.send_message(
                                admin,
                                f"⚓ *ANCHOR*: `{name}` → {reason}\n🌑 STOPPED → queued relaunch…",
                                parse_mode="Markdown"
                            )
                        except TelegramError:
                            pass
                    asyncio.create_task(bot_instance._enqueue_start(name, admin))

            await bot_instance.refresh_dashboard()

        except Exception as e:
            logger.error(f"⚓ ANCHOR: Watchdog error: {e}")


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

        # V7.2: Clone immunity window tracking — {clone_name: timestamp when started}
        self.clone_start_time: Dict[str, float] = {}

        # V7.3: Smart Pause tracking — {clone_name: pause_until_timestamp}
        self.manual_pause: Dict[str, float] = {}

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
            # V7.2: Record when clone became RUNNING for immunity window
            self.clone_start_time[name] = time.time()
        elif old == CloneState.RUNNING:
            self.running_since.pop(name, None)
            # Keep clone_start_time for immunity tracking even after stopping
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
            elif d == "sys_force_redraw":
                ok = await force_redraw()
                await context.bot.send_message(
                    chat,
                    f"🔄 *Force Redraw*: {'✅ Executed' if ok else '❌ Failed'}",
                    parse_mode="Markdown"
                )

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

        # V7.3: Cancel Smart Pause if active (user started clone early)
        if name in self.manual_pause:
            remaining = self.manual_pause[name] - time.time()
            if remaining > 0:
                logger.info(f"🚀 [{name}] Smart Pause cancelled early ({int(remaining)}s remaining)")
            self.manual_pause.pop(name, None)

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
        
        # V7.3: Trigger Smart Pause — disable watchdog for 30 seconds
        # NOTE: During this 30s window, the watchdog will NOT kill the clone
        # even if it appears to still be running. This prevents the race condition
        # where watchdog detects the clone as "frozen" while it's gracefully shutting down.
        pause_until = time.time() + 30
        self.manual_pause[name] = pause_until
        logger.info(f"🛑 [{name}] SMART PAUSE triggered — watchdog disabled for 30s")
        
        self.set_state(name, CloneState.STOPPED)
        self.persistence.remove_target(name)
        await InjectionEngine.stop(name)
        
        # V7.3: Schedule delayed check after 30 seconds
        asyncio.create_task(self._smart_pause_check(name, chat_id))
        
        if chat_id and self.application:
            try:
                await self.application.bot.send_message(
                    chat_id, f"🌑 `{name}` stopped.\n⏱️ Smart Pause: 30s watchdog immunity", parse_mode="Markdown")
            except Exception:
                pass
        await self.refresh_dashboard(force=True)

    async def _smart_pause_check(self, name: str, chat_id: Optional[int]):
        """
        V7.3: After 30s Smart Pause, check if clone is still running.
        If yes — it failed to stop, perform surgical kill.
        SAFETY: Skip if pause was cancelled early (user started clone).
        """
        await asyncio.sleep(30)
        
        # SAFETY CHECK: Verify pause is still active (wasn't cancelled early)
        if name not in self.manual_pause:
            logger.info(f"🛑 [{name}] Smart Pause was cancelled early — skipping surgical kill check")
            return
        
        # Clear the pause (normal operation resumes)
        self.manual_pause.pop(name, None)
        
        # Check if clone is still running
        pid = await InjectionEngine.get_clone_pid(name)
        if pid:
            logger.warning(f"🛑 [{name}] Still running after Smart Pause — performing surgical kill")
            await InjectionEngine.kill_by_pid(pid, name)
            
            # Double-check
            await asyncio.sleep(2)
            pid = await InjectionEngine.get_clone_pid(name)
            if pid:
                logger.error(f"🛑 [{name}] Surgical kill failed — force killing")
                await run_bash(f"su -c 'kill -9 {pid}'")
            
            if chat_id and self.application:
                try:
                    await self.application.bot.send_message(
                        chat_id, f"🚨 `{name}` required surgical kill after failed stop.", parse_mode="Markdown")
                except Exception:
                    pass
        else:
            logger.info(f"🛑 [{name}] Smart Pause ended — clone properly stopped")

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
        # V7.0: PID LOCK - Prevent ghost duplicates
        if not acquire_pid_lock():
            sys.exit(1)
        
        try:
            # 1. ANCHOR TO SYSTEM
            logger.info(f"� PROJECT AEGIS V8.2 DIRECT KERNEL THREAD COUNTING — {DEVICE_ID}")
            await anchor_to_system()
            
            # 2. V8.0: Scan and adopt existing clones before starting new ones
            await scan_and_adopt_clones(self)

            # 3. Build application
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

            # 6. Launch Watchdog (V8.0 Hard-Core)
            asyncio.create_task(watchdog_loop(app, self))

            # 6.1 Launch Keep-Alive Daemon (V8.0 System Critical)
            asyncio.create_task(keepalive_daemon(self))

            # 6.5 Launch Telemetry Daemon (V7.1 Active Supervisor)
            asyncio.create_task(telemetry_daemon(self))

            # 6.6 Launch Daily Restart Daemon (V7.4 Scheduled Maintenance)
            asyncio.create_task(daily_restart_daemon(self))

            # 7. Auto-resume
            asyncio.create_task(self._auto_resume())

            logger.info(f"� PROJECT AEGIS V8.2 KERNEL SCANNER ACTIVE — {DEVICE_ID}")

            # 8. Poll
            await app.updater.start_polling(drop_pending_updates=True)

            # 9. Block
            try:
                while True:
                    await asyncio.sleep(3600)
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass
            finally:
                await app.stop()
                await app.shutdown()
        finally:
            # Release PID lock on exit
            release_pid_lock()


# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        asyncio.run(AegisBot().run())
    except Exception as e:
        logger.critical(f"Fatal startup error: {e}")
