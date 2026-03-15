# -*- coding: utf-8 -*-
import os
import logging
from bash_utils import run_bash

logger = logging.getLogger("MonitorEngine")

class MonitorEngine:
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
