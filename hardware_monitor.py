# -*- coding: utf-8 -*-
import os
import psutil
import time
import subprocess

class HardwareMonitor:
    @staticmethod
    def get_uptime():
        """Returns stylized uptime string."""
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.readline().split()[0])
            hours = int(uptime_seconds // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            return f"{hours}h {minutes}m"

    @staticmethod
    def get_cpu_temp():
        """Attempts to read thermal temp."""
        paths = [
            "/sys/class/thermal/thermal_zone0/temp",
            "/sys/class/thermal/thermal_zone1/temp"
        ]
        for path in paths:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        return f"{int(int(f.read()) / 1000)}°C"
                except: pass
        return "N/A"

    @staticmethod
    def get_cpu_load():
        """Returns average CPU load percentage."""
        try:
            return f"{psutil.cpu_percent(interval=0.5)}%"
        except: return "N/A"

    @staticmethod
    def get_dashboard_report(device_id, active_clones_str=""):
        """v5 Rich Statistics Dashboard."""
        mem = psutil.virtual_memory()
        ram_percent = mem.percent
        free_ram_gb = round(mem.available / (1024**3), 1)
        
        uptime = HardwareMonitor.get_uptime()
        temp = HardwareMonitor.get_cpu_temp()
        cpu = HardwareMonitor.get_cpu_load()
        
        report = (
            f"📡 Device: {device_id} | Uptime: {uptime}\n"
            f"🧠 RAM: {ram_percent}% (Free: {free_ram_gb}GB)\n"
            f"🔥 Temp: {temp} | 🚀 CPU Load: {cpu}\n"
            f"🎮 Clones: {active_clones_str}"
        )
        return report

if __name__ == "__main__":
    print(HardwareMonitor.get_dashboard_report("DEBUG_DEV", "Active: 8/8"))
