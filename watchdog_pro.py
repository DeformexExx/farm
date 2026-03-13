# -*- coding: utf-8 -*-
import subprocess
import time

class WatchdogPro:
    def __init__(self, pkg_name, log_func=print):
        self.pkg_name = pkg_name
        self.log_func = log_func # Hook for Remote Console
        self.last_ticks = 0
        self.last_tick_time = 0
        self.freeze_count = 0

    def log(self, text):
        self.log_func(f"[{self.pkg_name}] {text}")

    def get_pid(self):
        try:
            result = subprocess.run(f"su -c 'pidof {self.pkg_name}'", shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                pids = result.stdout.strip().split()
                return int(pids[0]) if pids else None
        except Exception:
            pass
        return None

    def get_cpu_ticks(self, pid):
        try:
            result = subprocess.run(f"su -c 'cat /proc/{pid}/stat'", shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                stats = result.stdout.split()
                if len(stats) > 14:
                    return int(stats[13]) + int(stats[14])
        except Exception:
            pass
        return None

    def is_alive(self):
        pid = self.get_pid()
        if not pid:
            self.log("L1: PID not found.")
            return False

        current_ticks = self.get_cpu_ticks(pid)
        if current_ticks is None:
            return True 

        now = time.time()
        if self.last_ticks == 0:
            self.last_ticks = current_ticks
            self.last_tick_time = now
            return True

        if now - self.last_tick_time >= 120:
            delta = current_ticks - self.last_ticks
            self.log(f"L2 Heartbeat Delta: {delta} ticks")
            self.last_ticks = current_ticks
            self.last_tick_time = now

            if delta <= 0:
                self.freeze_count += 1
                if self.freeze_count >= 1:
                    return False
            else:
                self.freeze_count = 0
        
        return True

    def force_stop(self):
        self.log("Terminating...")
        subprocess.Popen(
            f"su -c 'am force-stop {self.pkg_name}'",
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        self.freeze_count = 0
        self.last_ticks = 0
