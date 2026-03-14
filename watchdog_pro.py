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
        """Counts threads for a given PID via psutil."""
        try:
            proc = psutil.Process(pid)
            return len(proc.threads())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return 0
        except Exception as e:
            self.log(f"Thread check error: {e}")
            return 0

    def is_alive(self):
        """
        v5 Multi-Layer Watchdog:
        1. 30s Cooldown after any launch.
        2. L2 (Process Watch): If PID is missing -> immediate restart.
        3. L1 (Thread Watch): If threads < 130 for 3 checks -> force-stop & restart.
        """
        now = time.time()
        # 30s Grace Period (v5)
        if now - self.last_launch_time < 30:
            return True

        pid = self.get_pid()
        # L2: PID check
        if not pid:
            self.log("L2: Process missing (PID not found).")
            return False

        # L1: Thread Check
        threads = self.get_thread_count(pid)
        if threads < 130:
            self.thread_fail_count += 1
            self.log(f"L1 Alert: low threads ({threads}) | Fail count: {self.thread_fail_count}/3")
            if self.thread_fail_count >= 3:
                self.log(f"L1: Frozen detected (< 130 threads).")
                self.thread_fail_count = 0
                return False
        else:
            self.thread_fail_count = 0 # Proper recovery reset
            
        return True

    def force_stop(self):
        """Surgical force stop."""
        self.log("Dispatched surgical stop.")
        try:
            subprocess.Popen(
                f"su -c 'am force-stop {self.pkg_name}'",
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception: pass
        self.thread_fail_count = 0
        self.last_launch_time = 0

if __name__ == "__main__":
    print("WatchdogPro v5 (L1/L2) Loaded.")
