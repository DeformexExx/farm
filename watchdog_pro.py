# -*- coding: utf-8 -*-
import subprocess
import time
import psutil

class WatchdogPro:
    def __init__(self, pkg_name, log_func=print):
        self.pkg_name = pkg_name
        self.log_func = log_func 
        self.freeze_start_time = 0
        self.is_frozen_detected = False

    def log(self, text):
        self.log_func(f"[{self.pkg_name}] {text}")

    def get_pid(self):
        """Standard PID check using pidof."""
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
        v3 Heartbeat Logic:
        1. Check if PID exists.
        2. Use psutil to check if CPU usage is < 1%.
        3. If CPU < 1% for more than 30 seconds, consider it Frozen.
        """
        pid = self.get_pid()
        if not pid:
            self.log("L1: PID not found.")
            return False

        try:
            proc = psutil.Process(pid)
            # interval=0.1 to get an immediate reading. 
            # Note: 1st call to cpu_percent is always 0.0, so we might need a small sleep or successive calls.
            cpu = proc.cpu_percent(interval=0.5)
            
            if cpu < 1.0:
                if self.freeze_start_time == 0:
                    self.freeze_start_time = time.time()
                
                duration = time.time() - self.freeze_start_time
                if duration >= 30:
                    self.log(f"L2: Frozen detected (CPU {cpu}% for {int(duration)}s).")
                    return False
            else:
                self.freeze_start_time = 0 # Reset if CPU spikes above 1%
        
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self.log("L1: Process access error.")
            return False
        except Exception as e:
            self.log(f"Heartbeat Error: {e}")
            
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
        self.freeze_start_time = 0

if __name__ == "__main__":
    print("WatchdogPro v3 (psutil) Loaded.")
