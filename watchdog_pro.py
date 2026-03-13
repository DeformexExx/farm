# -*- coding: utf-8 -*-
import subprocess
import time

class WatchdogPro:
    def __init__(self, pkg_name, log_func=print):
        self.pkg_name = pkg_name
        self.log_func = log_func 
        self.last_launch_time = 0

    def log(self, text):
        self.log_func(f"[{self.pkg_name}] {text}")

    def get_pid(self):
        """Simple PID check using pidof."""
        try:
            result = subprocess.run(f"su -c 'pidof {self.pkg_name}'", shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                pids = result.stdout.strip().split()
                return int(pids[0]) if pids else None
        except Exception:
            pass
        return None

    def is_alive(self):
        """
        v2.3 Heartbeat Logic (Simplified):
        1. Check if we just launched (15s grace period).
        2. Check if PID exists.
        """
        now = time.time()
        # 15s Grace Period
        if now - self.last_launch_time < 15:
            return True

        pid = self.get_pid()
        if not pid:
            self.log("L1: PID not found (Process dead).")
            return False
            
        return True

    def force_stop(self):
        """Simple force stop."""
        self.log("Stopping process...")
        subprocess.Popen(
            f"su -c 'am force-stop {self.pkg_name}'",
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        self.last_launch_time = 0

if __name__ == "__main__":
    print("WatchdogPro v2.3 (Simplified) Loaded.")
