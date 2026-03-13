# -*- coding: utf-8 -*-
import os
import psutil
import time

class HardwareMonitor:
    @staticmethod
    def get_cpu_temp():
        paths = [
            "/sys/class/thermal/thermal_zone0/temp",
            "/sys/class/thermal/thermal_zone1/temp",
            "/sys/devices/virtual/thermal/thermal_zone0/temp"
        ]
        for path in paths:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        temp = int(f.read().strip())
                        return temp / 1000.0 if temp > 1000 else temp
                except Exception:
                    continue
        return None

    @staticmethod
    def get_uptime():
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.readline().split()[0])
                hours = int(uptime_seconds // 3600)
                minutes = int((uptime_seconds % 3600) // 60)
                return f"{hours}h {minutes}m"
        except Exception:
            return "N/A"

    @staticmethod
    def get_dashboard_report(active_clones_count):
        ram = psutil.virtual_memory()
        temp = HardwareMonitor.get_cpu_temp()
        uptime = HardwareMonitor.get_uptime()
        
        # Simple text for v2 stability
        report = (
            f"--- SYSTEM DASHBOARD ---\n"
            f"RAM: {ram.percent}% ({ram.available // (1024**2)}MB Free)\n"
            f"TEMP: {temp if temp else 'N/A'} deg C\n"
            f"UPTIME: {uptime}\n"
            f"CLONES ACTIVE: {active_clones_count}\n"
            f"------------------------"
        )
        return report

if __name__ == "__main__":
    print(HardwareMonitor.get_dashboard_report(0))
