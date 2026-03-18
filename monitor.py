# -*- coding: utf-8 -*-
import os
import logging
from typing import Optional
from bash_utils import run_bash

logger = logging.getLogger("MonitorEngine")

class MonitorEngine:
    
    # ═══════════════════════════════════════════════════════════════════════
    # PID TRACKING — V6.0 Daemon Mode
    # ═══════════════════════════════════════════════════════════════════════
    _pid_cache: dict = {}  # {clone_name: pid}
    
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
        Проверяет запущен ли клон. Если да - возвращает статистику памяти и потоков.
        Если нет - возвращает 'Offline'.
        """
        ret, stdout_pid, _ = await run_bash(f"su -c 'pidof com.roblox.{clone_name}'")
        pid = stdout_pid.strip()
        
        if ret == 0 and pid:
            try:
                # Get RSS memory and Threads using ps/grep or /proc parsing via su
                cmd_stats = f"su -c 'cat /proc/{pid}/status | grep -E \"(VmRSS|Threads)\"'"
                ret_st, stdout_st, _ = await run_bash(cmd_stats)
                
                threads, mem = "?", "?"
                if ret_st == 0:
                    for line in stdout_st.split('\n'):
                        line = line.strip()
                        if line.startswith('VmRSS:'):
                            parts = line.split()
                            if len(parts) >= 2:
                                mem = f"{int(parts[1])//1024}MB"
                        elif line.startswith('Threads:'):
                            parts = line.split()
                            if len(parts) >= 2:
                                threads = parts[1]
                                
                return f"Mem: {mem} | Thr: {threads}"
            except Exception as e:
                logger.error(f"Error fetching stats for {clone_name}: {e}")
                return "Stats Error"
        else:
            return "Offline"
