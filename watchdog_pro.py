# -*- coding: utf-8 -*-
import subprocess
import time
import psutil
import os

class WatchdogPro:
    def __init__(self, pkg_name, log_func=print):
        self.pkg_name = pkg_name
        self.log_func = log_func 
        self.thread_fail_count = 0
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

    def get_thread_count(self, pid):
        """Counts threads for a given PID via /proc or psutil."""
        try:
            # Using psutil for accuracy
            proc = psutil.Process(pid)
            return len(proc.threads())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return 0
        except Exception as e:
            self.log(f"Thread check error: {e}")
            return 0

    def is_alive(self):
        """
        v4 Smart Watchdog (The 130-Thread Rule):
        1. 15s grace period after launch.
        2. PID must exist.
        3. threads() < 130 for 3 consecutive checks (approx 6 mins) -> Frozen/Glitch.
        """
        now = time.time()
        # 15s Grace Period
        if now - self.last_launch_time < 15:
            return True

        pid = self.get_pid()
        if not pid:
            self.log("L1: PID not found.")
            return False

        # Thread Check (v4 Logic)
        threads = self.get_thread_count(pid)
        if threads < 130:
            self.thread_fail_count += 1
            self.log(f"L2 Alert: low threads ({threads}) | Fail count: {self.thread_fail_count}/3")
            if self.thread_fail_count >= 3:
                self.log(f"L2: Frozen/Glitch detected (Less than 130 threads for 6 mins).")
                self.thread_fail_count = 0
                return False
        else:
            if self.thread_fail_count > 0:
                self.log(f"L2: Threads recovered ({threads}).")
            self.thread_fail_count = 0
            
        return True

    def force_stop(self):
        """Surgical force stop."""
        self.log("Surgical stop dispatched.")
        subprocess.Popen(
            f"su -c 'am force-stop {self.pkg_name}'",
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        self.thread_fail_count = 0
        self.last_launch_time = 0

if __name__ == "__main__":
    print("WatchdogPro v4 (Thread Check) Loaded.")
