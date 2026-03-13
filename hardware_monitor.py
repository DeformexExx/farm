# -*- coding: utf-8 -*-
import os
import subprocess
import shutil

class HardwareMonitor:
    @staticmethod
    def get_cpu_temp():
        """Attempts to read CPU temperature from common Android paths."""
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
    def get_battery_info():
        """Reads battery status via termux-battery-status if available."""
        try:
            import json
            result = subprocess.run(["termux-battery-status"], capture_output=True, text=True)
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception:
            # Fallback to sysfs if termux-api is not installed
            try:
                with open("/sys/class/power_supply/battery/capacity", "r") as f:
                    capacity = int(f.read().strip())
                return {"percentage": capacity}
            except:
                pass
        return None

    @staticmethod
    def get_free_space(path="/data"):
        """Returns free space in GB."""
        try:
            total, used, free = shutil.disk_usage(path)
            return free / (1024**3)
        except Exception:
            return 0.0

    @staticmethod
    def get_report():
        temp = HardwareMonitor.get_cpu_temp()
        batt = HardwareMonitor.get_battery_info()
        space = HardwareMonitor.get_free_space()
        
        report = f"\U0001F321 CPU: {temp if temp else 'N/A'}\u00b0C\n"
        if batt:
            report += f"\U0001F50B Battery: {batt.get('percentage')}% ({batt.get('status', 'Unknown')})\n"
        report += f"\U0001F4BE Free Space: {space:.2f} GB"
        return report

if __name__ == "__main__":
    print(HardwareMonitor.get_report())
