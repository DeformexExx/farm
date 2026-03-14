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
        v6.1 Silent Health Check:
        1. 30s grace period.
        2. PID missing -> Silent False.
        3. Threads < 110 -> Silent False.
        """
        now = time.time()
        if now - self.last_launch_time < 30:
            return True

        pid = self.get_pid()
        if not pid:
            # Silent recovery
            return False

        threads = self.get_thread_count(pid)
        if threads < 110:
            self.fail_count += 1
            if self.fail_count >= 2:
                # Silent recovery
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
