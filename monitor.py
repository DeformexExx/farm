# -*- coding: utf-8 -*-
# monitor.py — Project Aegis V7.1 Active Supervisor Tuning
import os
import logging
import time
from typing import Optional, Dict, Tuple
from bash_utils import run_bash

logger = logging.getLogger("MonitorEngine")

class MonitorEngine:
    
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
        V7.1: Fallback telemetry when /proc fails.
        Reads last 20 lines of clone's log file to extract thread count.
        Returns (thread_count, source) where source is 'proc', 'log', or 'none'.
        """
        # First try /proc/{pid}/status
        if pid:
            ret, stdout, _ = await run_bash(f"su -c 'cat /proc/{pid}/status | grep -E \"Threads:\"'")
            if ret == 0:
                for line in stdout.split('\n'):
                    if line.strip().startswith('Threads:'):
                        parts = line.split()
                        if len(parts) >= 2:
                            try:
                                return int(parts[1]), "proc"
                            except ValueError:
                                pass
        
        # Fallback: Read from clone's log file
        log_path = MonitorEngine._get_clone_log_path(clone_name)
        try:
            ret, stdout, _ = await run_bash(f"su -c 'tail -n 20 {log_path} 2>/dev/null || echo NONE'")
            if ret == 0 and stdout.strip() != "NONE":
                # Look for thread count patterns in log
                # Common patterns: "Threads: 123", "thread_count=123", "active_threads: 123"
                import re
                patterns = [
                    r'Threads?:\s*(\d+)',
                    r'thread[_\-]?count[=:]\s*(\d+)',
                    r'active[_\-]?threads?:\s*(\d+)',
                    r'\[THREADS?\]:?\s*(\d+)',
                ]
                for line in stdout.split('\n'):
                    for pattern in patterns:
                        match = re.search(pattern, line, re.IGNORECASE)
                        if match:
                            try:
                                return int(match.group(1)), "log"
                            except ValueError:
                                continue
        except Exception as e:
            logger.debug(f"V7.1: Log fallback failed for {clone_name}: {e}")
        
        return 0, "none"
    
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
            ret, stdout, _ = await run_bash(f"su -c 'top -p {pid} -n 1 2>/dev/null | grep {pid}'")
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
            ret2, stat1, _ = await run_bash(f"su -c 'cat /proc/{pid}/stat 2>/dev/null'")
            if ret2 == 0:
                ret3, uptime_str, _ = await run_bash("su -c 'cat /proc/uptime'")
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
    def is_thread_frozen(clone_name: str) -> bool:
        """
        V7.1 AGGRESSIVE FREEZE DETECTION:
        Returns True if thread count is 0 or hasn't changed for 180 seconds.
        """
        history = MonitorEngine._thread_history.get(clone_name, [])
        if not history:
            return False
        
        latest_count = history[-1][1]
        if latest_count == 0:
            return True  # Zero threads = definitely frozen
        
        if len(history) < 3:
            return False  # Not enough data
        
        # Check if count has been constant for 180 seconds
        now = time.time()
        first_same = None
        current_count = history[-1][1]
        
        for ts, count in reversed(history):
            if count != current_count:
                break
            first_same = ts
        
        if first_same and (now - first_same) >= 180:
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
    
    @staticmethod
    async def get_clone_pid(clone_name: str) -> str:
        """Get specific PID for a clone package. Returns empty string if not running."""
        package = f"com.roblox.{clone_name}"
        ret, stdout, _ = await run_bash(f"su -c 'pidof {package}'")
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
            ret, _, _ = await run_bash(f"su -c 'kill -0 {pid} 2>/dev/null && echo ALIVE || echo DEAD'")
            if "ALIVE" in ret:
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
            ret, stdout, _ = await run_bash(
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
        """
        V7.1: Проверяет запущен ли клон. Если да - возвращает статистику памяти и потоков.
        Если нет - возвращает 'Offline'.
        Использует fallback telemetry когда /proc недоступен.
        """
        ret, stdout_pid, _ = await run_bash(f"su -c 'pidof com.roblox.{clone_name}'")
        pid = stdout_pid.strip()
        
        if ret == 0 and pid:
            try:
                # V7.1: Use fallback telemetry for thread count
                thread_count, source = await MonitorEngine.get_thread_count_fallback(clone_name, pid)
                
                # Record for freeze detection
                MonitorEngine.record_thread_history(clone_name, thread_count)
                
                # Get RSS memory
                cmd_stats = f"su -c 'cat /proc/{pid}/status | grep -E \"VmRSS\"'"
                ret_st, stdout_st, _ = await run_bash(cmd_stats)
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
                
                threads_str = str(thread_count) if thread_count > 0 else "?"
                return f"Mem: {mem} | Thr: {threads_str} | Src: {source}"
            except Exception as e:
                logger.error(f"Error fetching stats for {clone_name}: {e}")
                return "Stats Error"
        else:
            return "Offline"
