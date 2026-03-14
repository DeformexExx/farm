# -*- coding: utf-8 -*-
import subprocess
import time
import psutil
import os

class WatchdogPro:
    def __init__(self, pkg_name, log_func=print):
        self.pkg_name = pkg_name
        self.log_func = log_func 
        self.last_launch_time = 0
        self.fail_count = 0

    def log(self, text):
        self.log_func(f"[{self.pkg_name}] {text}")

    def get_pid(self):
        try:
            result = subprocess.run(f"su -c 'pidof {self.pkg_name}'", shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                pids = result.stdout.strip().split()
                return int(pids[0]) if pids else None
        except Exception: pass
        return None

    def get_thread_count(self, pid):
        """Counts threads for a given PID. v6 uses /proc/[pid]/status effectively."""
        try:
            # Using psutil as a robust wrapper for /proc
            proc = psutil.Process(pid)
            return len(proc.threads())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return 0
        except Exception as e:
            self.log(f"Thread check error: {e}")
            return 0

    def check_health(self):
        """
        v6 Health Check:
        1. 30s grace period.
        2. PID missing -> Needs Restart.
        3. Threads < 110 (significant drop below 130) -> Needs Restart.
        """
        now = time.time()
        if now - self.last_launch_time < 30:
            return True

        pid = self.get_pid()
        if not pid:
            self.log("L2: Process missing.")
            return False

        threads = self.get_thread_count(pid)
        # "Significantly below 130" - setting threshold at 110
        if threads < 110:
            self.fail_count += 1
            self.log(f"L1: Critical low threads ({threads}). Counter: {self.fail_count}/2")
            if self.fail_count >= 2:
                self.log(f"L1: Freeze confirmed ({threads} threads).")
                self.fail_count = 0
                return False
        else:
            self.fail_count = 0
            
        return True

    def force_stop(self):
        subprocess.run(f"su -c 'am force-stop {self.pkg_name}'", shell=True)
        self.last_launch_time = 0
        self.fail_count = 0

if __name__ == "__main__":
    print("WatchdogPro v6 Loaded.")
