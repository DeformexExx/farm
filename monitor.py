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
        V5.6 Native Sight: Checks for clone using 'su -c ps -ef'.
        """
        # Improved PID search for ugPhone (V5.6)
        cmd_pid = f"su -c \"ps -ef | grep com.roblox.{clone_name} | grep -v grep | awk '{{print $2}}'\""
        ret, stdout_pid, _ = await run_bash(cmd_pid)
        pid = stdout_pid.strip()
        
        if pid:
            try:
                # Use root access for threads and memory (V5.6)
                cmd_stats = f"su -c \"cat /proc/{pid}/status | grep -E '(VmRSS|Threads)'\""
                ret_st, stdout_st, _ = await run_bash(cmd_stats)
                
                cmd_stat = f"su -c \"cat /proc/{pid}/stat\""
                ret_stat, stdout_stat, _ = await run_bash(cmd_stat)
                cpu_ticks = "0"
                if ret_stat == 0 and stdout_stat:
                    parts = stdout_stat.split()
                    if len(parts) >= 15:
                        cpu_ticks = str(int(parts[13]) + int(parts[14]))
                
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
                                
                return f"Mem: {mem} | Thr: {threads} | CpuTicks: {cpu_ticks}"
            except Exception as e:
                logger.error(f"Error fetching stats for {clone_name}: {e}")
                return "Stats Error"
        else:
            return "Offline"
