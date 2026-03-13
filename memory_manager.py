# -*- coding: utf-8 -*-
import os
import subprocess
import time

class MemoryManager:
    SWAP_PATH = "/data/local/tmp/swapfile"
    SWAP_SIZE_GB = 4

    @staticmethod
    def _run_su_detached(cmd):
        """Runs su command in detached mode to save RAM."""
        try:
            subprocess.Popen(
                f"su -c '{cmd}'",
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setpgrp
            )
        except Exception:
            pass

    @staticmethod
    def setup_swap():
        """Check and setup 4GB swap file on /data/local/tmp."""
        try:
            if os.path.exists(MemoryManager.SWAP_PATH):
                print(f"Swap exists at {MemoryManager.SWAP_PATH}")
                return

            print(f"Creating {MemoryManager.SWAP_SIZE_GB}GB swap file...")
            steps = [
                f"dd if=/dev/zero of={MemoryManager.SWAP_PATH} bs=1M count={MemoryManager.SWAP_SIZE_GB * 1024}",
                f"chmod 600 {MemoryManager.SWAP_PATH}",
                f"mkswap {MemoryManager.SWAP_PATH}",
                f"swapon {MemoryManager.SWAP_PATH}"
            ]
            for step in steps:
                subprocess.run(f"su -c '{step}'", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(1)
            print("Swap setup complete.")
        except Exception as e:
            print(f"Swap error: {e}")

    @staticmethod
    def optimize_for_launch():
        """Kernel-level optimizations before clone flight (v3.1)."""
        # Enable KSM (Kernel Samepage Merging) if available to save RAM
        ksm_cmd = "echo 1 > /sys/kernel/mm/ksm/run"
        # Immediate sync and cache drop
        flush_cmd = "sync; echo 3 > /proc/sys/vm/drop_caches"
        
        subprocess.run(f"su -c '{ksm_cmd}'", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(f"su -c '{flush_cmd}'", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @staticmethod
    def deep_clean_clone(pkg_name):
        """Fast pre-flight cleaning (v2.3+ logic)."""
        cmd = f"am force-stop {pkg_name} && pm trim-caches 999G"
        MemoryManager._run_su_detached(cmd)

    @staticmethod
    def system_deep_clean():
        """Ultimate deep clean shell command."""
        cmd = "sync; echo 3 > /proc/sys/vm/drop_caches; am kill-all; fstrim -v /data"
        MemoryManager._run_su_detached(cmd)

    @staticmethod
    def set_oom_priority():
        """Protect bot process from LMK."""
        try:
            pid = os.getpid()
            subprocess.run(f"su -c 'echo -1000 > /proc/{pid}/oom_score_adj'", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

if __name__ == "__main__":
    MemoryManager.setup_swap()
    MemoryManager.optimize_for_launch()
