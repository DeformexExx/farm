# monitor.py — Project Aegis V10.7 Monolithic Kernel Access
import os
import re
import logging
import time
import asyncio
from typing import Optional, Dict, Tuple
from bash_utils import run_bash

logger = logging.getLogger("MonitorEngineV107")

class MonitorEngine:
    
    # ═══════════════════════════════════════════════════════════════════════
    # V10.7 MONOLITHIC KERNEL ACCESS — Hard-coded su -c "cat /proc/[PID]/status | grep Threads"
    # ═══════════════════════════════════════════════════════════════════════
    _pid_cache: Dict[str, str] = {}
    _cpu_zero_timers: Dict[str, float] = {}  # V12.0: Tracks 0.0% CPU for watchdog
    
    @staticmethod
    async def get_top_telemetry() -> Dict[str, Dict]:
        """
        V12.0: THE TOP-MONITOR — Returns ALL Roblox telemetry at once via top.
        Output format: {clone_name: {"pid": str, "cpu": float}}
        """
        results = {}
        # New Directive: su -c "top -n 1 -b | grep -i 'com.roblox.clien'"
        cmd = "su -c \"top -n 1 -b | grep -i 'com.roblox.clien'\""
        ret, stdout, _ = run_bash(cmd)
        
        if ret == 0 and stdout:
            lines = stdout.strip().split('\n')
            for line in lines:
                parts = line.split()
                if len(parts) >= 9:
                    try:
                        pid = parts[0]
                        cpu = float(parts[8]) # 9th column (0-indexed)
                        
                        # Find the suffix in the package name (e.g. com.roblox.cliene)
                        match = re.search(r'com\.roblox\.(clien[a-z])', line.lower())
                        if match:
                            suffix = match.group(1)
                            results[suffix] = {"pid": pid, "cpu": cpu}
                    except (IndexError, ValueError):
                        continue
        return results
    
    @staticmethod
    async def get_thread_count_v107(pid: str) -> Tuple[Optional[int], str]:
        """V12.0: Obsolete method — Redirected to none."""
        return None, "offline"
    
    @staticmethod
    async def get_thread_count_kernel(pid: str) -> Tuple[int, str]:
        """V12.0: Obsolete method — Redirected to none."""
        return 0, "offline"
    
    # ═══════════════════════════════════════════════════════════════════════
    # V7.1 THREAD TELEMETRY HISTORY — Tracks thread counts for freeze detection
    # ═══════════════════════════════════════════════════════════════════════
    _thread_history: Dict[str, list] = {}  # {clone_name: [(timestamp, count), ...]}
    _cpu_history: Dict[str, list] = {}     # {clone_name: [(timestamp, cpu_percent), ...]}
    
    @staticmethod
    def _get_clone_log_path(clone_name: str) -> str:
        """V7.1: Get the path to clone's individual log file."""
        # Common log locations for Android apps
        base_paths = [
            f"/data/data/com.roblox.{clone_name}/files/log",
            f"/data/data/com.roblox.{clone_name}/cache/log",
            f"/sdcard/Android/data/com.roblox.{clone_name}/files/log",
        ]
        return base_paths[0]  # Default to first path
    
    @staticmethod
    async def get_thread_count_fallback(clone_name: str, pid: str) -> Tuple[int, str]:
        """
        V8.2: Direct Kernel Access for thread counting.
        Primary: /proc/[PID]/status parsing.
        Fallback: /proc/[PID]/task/ directory counting.
        Returns (thread_count, source) where source is 'kernel', 'task', or 'none'.
        """
        # V8.2: Use kernel scanner as primary method
        return await MonitorEngine.get_thread_count_kernel(pid)
    
    @staticmethod
    def _parse_thread_count_from_log(log_content: str) -> int:
        """
        V7.2: Flexible thread count parser with multiple regex patterns.
        Returns thread count or 0 if not found.
        """
        if not log_content:
            return 0
            
        # Comprehensive pattern list for different log formats
        patterns = [
            # Standard patterns
            r'Threads?:\s*(\d+)',
            r'thread[_\-]?count[=:]\s*(\d+)',
            r'active[_\-]?threads?:\s*(\d+)',
            r'\[THREADS?\]:?\s*(\d+)',
            # Additional flexible patterns
            r'threads?\s*[=:]\s*(\d+)',
            r'threads?:?\s*(\d+)\s*(?:threads?|count)',
            r'(?i)thread count[:\s]+(\d+)',
            r'(?i)active threads?[:\s]+(\d+)',
            r'\b(\d+)\s*threads?\b',
        ]
        
        lines = log_content.split('\n')
        # Search in reverse order (newest first)
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            for pattern in patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    try:
                        count = int(match.group(1))
                        if count >= 0:  # Accept 0 as valid reading
                            return count
                    except (ValueError, IndexError):
                        continue
        return 0
    
    @staticmethod
    async def get_clone_cpu_usage(clone_name: str, pid: str) -> float:
        """
        V7.1: Get CPU usage percentage for a clone process.
        Returns CPU percent (0-100) or -1 if unavailable.
        """
        if not pid:
            return -1.0
        try:
            # Use top command for single process CPU
            ret, stdout, _ = run_bash(f"su -c 'top -p {pid} -n 1 2>/dev/null | grep {pid}'")
            if ret == 0 and stdout.strip():
                # Parse CPU column from top output
                parts = stdout.strip().split()
                if len(parts) >= 9:
                    try:
                        # CPU% is typically column 8 in top output
                        cpu_str = parts[8].replace('%', '')
                        return float(cpu_str)
                    except (ValueError, IndexError):
                        pass
            # Alternative: use /proc/{pid}/stat calculation
            ret2, stat1, _ = run_bash(f"su -c 'cat /proc/{pid}/stat 2>/dev/null'")
            if ret2 == 0:
                ret3, uptime_str, _ = run_bash("su -c 'cat /proc/uptime'")
                if ret3 == 0:
                    try:
                        uptime = float(uptime_str.split()[0])
                        fields = stat1.split()
                        if len(fields) > 15:
                            utime = int(fields[13])
                            stime = int(fields[14])
                            total_time = utime + stime
                            # Approximate CPU calculation
                            return min(100.0, total_time / (uptime * 10))  # Rough estimate
                    except (ValueError, IndexError):
                        pass
        except Exception as e:
            logger.debug(f"V7.1: CPU check failed for {clone_name}: {e}")
        return -1.0
    
    @staticmethod
    def record_thread_history(clone_name: str, thread_count: int):
        """V7.1: Record thread count for freeze detection history."""
        if clone_name not in MonitorEngine._thread_history:
            MonitorEngine._thread_history[clone_name] = []
        MonitorEngine._thread_history[clone_name].append((time.time(), thread_count))
        # Keep only last 15 minutes of history (60 entries at 15s intervals)
        cutoff = time.time() - 900
        MonitorEngine._thread_history[clone_name] = [
            (t, c) for t, c in MonitorEngine._thread_history[clone_name] if t > cutoff
        ]
    
    @staticmethod
    def record_cpu_history(clone_name: str, cpu: float):
        """V7.1: Record CPU usage for freeze detection history."""
        if clone_name not in MonitorEngine._cpu_history:
            MonitorEngine._cpu_history[clone_name] = []
        MonitorEngine._cpu_history[clone_name].append((time.time(), cpu))
        # Keep only last 15 minutes
        cutoff = time.time() - 900
        MonitorEngine._cpu_history[clone_name] = [
            (t, c) for t, c in MonitorEngine._cpu_history[clone_name] if t > cutoff
        ]
    
    @staticmethod
    def is_thread_frozen(clone_name: str, threshold: int = 50) -> bool:
        """
        V8.2: Thread freeze detection with configurable threshold.
        Returns True if thread count < threshold for more than 5 minutes.
        Also returns True if /proc entry disappears (process died).
        """
        history = MonitorEngine._thread_history.get(clone_name, [])
        if not history:
            return False
        
        # Check if /proc entry is gone (last reading was -1 and still no data)
        latest_count = history[-1][1]
        now = time.time()
        
        # V8.2: -1 means unable to read /proc - check if this persists
        if latest_count < 0:
            # Find when we first lost /proc access
            first_negative = None
            for ts, count in reversed(history):
                if count >= 0:
                    break
                first_negative = ts
            
            # If /proc has been inaccessible for 60s, consider it crashed
            if first_negative and (now - first_negative) >= 60:
                return True
            return False
            
        # V8.2: Check if thread count is below threshold
        if latest_count > 0 and latest_count < threshold:
            # Check if it has been low for 5 minutes (300 seconds)
            first_low = None
            for ts, count in reversed(history):
                if count < 0:  # Skip unknown readings
                    continue
                if count >= threshold:
                    break
                first_low = ts
            
            if first_low is not None and (now - first_low) >= 300:
                return True
        
        return False
    
    @staticmethod
    def is_cpu_frozen(clone_name: str) -> bool:
        """
        V7.1 CPU FREEZE DETECTION:
        Returns True if CPU usage < 1% for 120 seconds (2 minutes).
        """
        history = MonitorEngine._cpu_history.get(clone_name, [])
        if len(history) < 4:  # Need at least 4 readings (60s at 15s intervals)
            return False
        
        now = time.time()
        # Check last 120 seconds
        cutoff = now - 120
        recent = [cpu for ts, cpu in history if ts > cutoff]
        
        if len(recent) < 4:
            return False
        
        # All readings must be < 1% to be considered frozen
        return all(cpu >= 0 and cpu < 1.0 for cpu in recent)
    
    # ═══════════════════════════════════════════════════════════════════════
    # V8.7 SMART WATCHDOG — Ghost Process & Frozen Detection
    # ═══════════════════════════════════════════════════════════════════════
    
    @staticmethod
    def is_ghost_process(clone_name: str) -> bool:
        """
        V8.7 GHOST PROCESS DETECTION:
        Returns True if thread count == 1 for more than 5 minutes (300s).
        A 1-thread process is IDLE/LOADING and should be killed and relaunched.
        """
        history = MonitorEngine._thread_history.get(clone_name, [])
        if not history:
            return False
        
        now = time.time()
        
        # Check if thread count has been exactly 1 for 5+ minutes
        first_one_thread = None
        for ts, count in reversed(history):
            if count < 0:  # Skip error readings
                continue
            if count != 1:  # Not 1 thread anymore
                break
            first_one_thread = ts
        
        if first_one_thread is not None and (now - first_one_thread) >= 300:
            return True
        
        return False
    
    @staticmethod
    def is_frozen_v87(clone_name: str) -> bool:
        """
        V8.7 FROZEN DETECTION:
        Returns True if thread count < 80 for more than 3 minutes (180s).
        Healthy clone must have Threads > 100.
        """
        history = MonitorEngine._thread_history.get(clone_name, [])
        if not history:
            return False
        
        now = time.time()
        
        # Check if thread count has been below 80 for 3+ minutes
        first_low = None
        for ts, count in reversed(history):
            if count < 0:  # Skip error readings
                continue
            if count >= 80:  # Not frozen anymore
                break
            first_low = ts
        
        if first_low is not None and (now - first_low) >= 180:
            return True
        
        return False
    
    @staticmethod
    async def kill_ghost_process(pid: str, clone_name: str) -> bool:
        """
        V8.7: Kill a ghost process using kill -9.
        Returns True if successfully killed.
        """
        if not pid:
            return False
        
        try:
            logger.critical(f"👻 V8.7 GHOST KILL: Killing {clone_name} (PID {pid}) — stuck at 1 thread for 5min+")
            ret, _, _ = run_bash(f"su -c 'kill -9 {pid}'")
            
            # Verify death
            time.sleep(1)
            _, check_stdout, _ = run_bash(f"su -c 'kill -0 {pid} 2>/dev/null && echo ALIVE || echo DEAD'")
            success = "DEAD" in check_stdout
            
            if success:
                logger.info(f"👻 V8.7 GHOST KILL: {clone_name} terminated successfully")
            else:
                logger.error(f"👻 V8.7 GHOST KILL: {clone_name} may still be alive!")
            
            return success
        except Exception as e:
            logger.error(f"👻 V8.7 GHOST KILL error: {e}")
            return False
    
    @staticmethod
    async def get_clone_pid(clone_name: str) -> str:
        """Get specific PID for a clone package. Returns empty string if not running."""
        package = f"com.roblox.{clone_name}"
        ret, stdout, _ = run_bash(f"su -c 'pidof {package}'")
        if ret == 0 and stdout.strip():
            pid = stdout.strip().split()[0]
            MonitorEngine._pid_cache[clone_name] = pid
            return pid
        MonitorEngine._pid_cache.pop(clone_name, None)
        return ""
    
    @staticmethod
    async def get_cached_pid(clone_name: str) -> str:
        """Get cached PID or refresh if not in cache."""
        if clone_name in MonitorEngine._pid_cache:
            # Verify still alive
            pid = MonitorEngine._pid_cache[clone_name]
            _, stdout, _ = run_bash(f"su -c 'kill -0 {pid} 2>/dev/null && echo ALIVE || echo DEAD'")
            if "ALIVE" in stdout:
                return pid
            # PID died, remove from cache
            MonitorEngine._pid_cache.pop(clone_name, None)
        return await MonitorEngine.get_clone_pid(clone_name)

    @staticmethod
    async def verify_clone_via_dumpsys(clone_name: str) -> bool:
        """
        V7.0: UI-Crash Immunity - Verify clone via dumpsys activity.
        Works even when /proc is inaccessible or SystemUI crashed.
        """
        package = f"com.roblox.{clone_name}"
        try:
            ret, stdout, _ = run_bash(
                f"su -c 'dumpsys activity activities | grep -i {package}'"
            )
            if ret == 0 and stdout.strip():
                if any(kw in stdout.lower() for kw in ['resumed', 'visible', 'foreground']):
                    return True
            return False
        except Exception as e:
            logger.error(f"⚓ ANCHOR: dumpsys verification error for {clone_name}: {e}")
            return False

    @staticmethod
    async def get_system_stats() -> tuple[str, str, str]:
        """Возвращает (RAM_str, CPU_str, TEMP_str)"""
        ram, cpu, temp = "N/A", "N/A", "N/A"
        
        try:
            import psutil
            mem = psutil.virtual_memory()
            ram = f"{mem.percent}%"
            cpu = f"{psutil.cpu_percent()}%"
        except ImportError:
            # Fallback if psutil is missing
            pass
            
        try:
            paths = ["/sys/class/thermal/thermal_zone0/temp", "/sys/class/thermal/thermal_zone1/temp"]
            for path in paths:
                if os.path.exists(path):
                    with open(path, "r") as f:
                        temp = f"{int(int(f.read()) / 1000)}°C"
                    break
        except Exception:
            pass
            
        return ram, cpu, temp

    @staticmethod
    async def get_clone_status(clone_name: str) -> str:
        """V11.0: THE KERNEL HUNTER — Robust PID discovery"""
        # We reuse the tested InjectionEngine hunter logic
        from injection_engine import InjectionEngine
        pid = await InjectionEngine.get_clone_pid(clone_name)
        
        if pid:
            try:
                # V8.2: Use kernel scanner for thread count (Now V11.0 Hunter)
                thread_count, source = await MonitorEngine.get_thread_count_kernel(pid)
                
                # Record for freeze detection (Only if valid)
                if thread_count is not None:
                    # V11.0: Record real count (can be 0 or high)
                    MonitorEngine.record_thread_history(clone_name, thread_count)
                
                # Get RSS memory
                cmd_stats = f"su -c 'cat /proc/{pid}/status | grep -E \"VmRSS\"'"
                ret_st, stdout_st, _ = run_bash(cmd_stats)
                mem = "?"
                if ret_st == 0:
                    for line in stdout_st.split('\n'):
                        line = line.strip()
                        if line.startswith('VmRSS:'):
                            parts = line.split()
                            if len(parts) >= 2:
                                mem = f"{int(parts[1])//1024}MB"
                
                # Get CPU usage for freeze detection
                cpu = await MonitorEngine.get_clone_cpu_usage(clone_name, pid)
                if cpu >= 0:
                    MonitorEngine.record_cpu_history(clone_name, cpu)
                
                # V8.2: Show real thread count, never show [SCANNING...]
                if thread_count is None or thread_count < 0:
                    threads_str = "N/A"  # Kernel read failed
                else:
                    threads_str = str(thread_count)
                    
                return f"Mem: {mem} | Thr: {threads_str} | Src: {source}"
            except Exception as e:
                logger.error(f"Error fetching stats for {clone_name}: {e}")
                return "Stats Error"
        else:
            return "Offline"
