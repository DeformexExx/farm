# -*- coding: utf-8 -*-
import os
import time
import subprocess
import logging
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WatchdogPro")

class WatchdogPro:
    def __init__(self, pkg_name):
        self.pkg_name = pkg_name
        self.last_ticks = 0
        self.last_tick_time = 0
        self.freeze_counters = {
            "level2": 0,
            "level3": 0
        }

    def get_pid(self):
        """Level 1: PID Check."""
        try:
            result = subprocess.run(f"su -c 'pidof {self.pkg_name}'", shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                output = result.stdout.strip().split()
                return int(output[0]) if output else None
        except Exception:
            pass
        return None

    def get_cpu_ticks(self, pid):
        """Reads total CPU ticks (utime + stime) for the process."""
        try:
            with open(f"/proc/{pid}/stat", "r") as f:
                stats = f.read().split()
                # 14th is utime, 15th is stime
                return int(stats[13]) + int(stats[14])
        except Exception:
            return None

    def check_level2(self, pid):
        """Level 2: Tick Delta Check (Soft Freeze)."""
        current_ticks = self.get_cpu_ticks(pid)
        if current_ticks is None:
            return False
            
        now = time.time()
        if self.last_ticks == 0:
            self.last_ticks = current_ticks
            self.last_tick_time = now
            return True

        # Every 60 seconds, check delta
        if now - self.last_tick_time >= 60:
            delta = current_ticks - self.last_ticks
            logger.info(f"[{self.pkg_name}] Level 2 Delta: {delta} ticks")
            
            self.last_ticks = current_ticks
            self.last_tick_time = now
            
            if delta < 10:
                self.freeze_counters["level2"] += 1
                if self.freeze_counters["level2"] >= 3: # 3 failed checks = 3 minutes
                    return False
            else:
                self.freeze_counters["level2"] = 0
        return True

    def check_level3(self):
        """Level 3: Visual Check (Hard Freeze/Black Screen)."""
        temp_screen = f"/tmp/screen_{self.pkg_name}.png"
        try:
            # Capture screen
            subprocess.run(f"su -c 'screencap -p {temp_screen}'", shell=True, check=True)
            
            with Image.open(temp_screen) as img:
                img = img.resize((10, 10)) # Resize to speed up
                extrema = img.convert("L").getextrema()
                
                # If all pixels are the same (0,0) or (255,255)
                if extrema[0] == extrema[1]:
                    self.freeze_counters["level3"] += 1
                    logger.warning(f"[{self.pkg_name}] Level 3: Static screen detected ({extrema[0]}). Counter: {self.freeze_counters['level3']}")
                    if self.freeze_counters["level3"] >= 3: # 3 minutes of black/white screen
                        return False
                else:
                    self.freeze_counters["level3"] = 0
            
            if os.path.exists(temp_screen):
                os.remove(temp_screen)
                
        except Exception as e:
            logger.error(f"Level 3 check failed: {e}")
            
        return True

    def is_alive(self):
        pid = self.get_pid()
        if not pid:
            logger.error(f"[{self.pkg_name}] Level 1: Process not found.")
            return False
        
        if not self.check_level2(pid):
            logger.error(f"[{self.pkg_name}] Level 2: Soft freeze detected (low ticks).")
            return False
            
        if not self.check_level3():
            logger.error(f"[{self.pkg_name}] Level 3: Hard freeze detected (static screen).")
            return False
            
        return True

    def force_stop(self):
        logger.info(f"Force stopping {self.pkg_name}...")
        subprocess.run(f"su -c 'am force-stop {self.pkg_name}'", shell=True)
        self.freeze_counters = {"level2": 0, "level3": 0}
        self.last_ticks = 0

if __name__ == "__main__":
    logger.info("WatchdogPro module loaded.")
