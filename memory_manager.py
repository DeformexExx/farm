# -*- coding: utf-8 -*-
import os
import subprocess
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MemoryManager")

class MemoryManager:
    SWAP_PATH = "/data/swapfile"
    SWAP_SIZE_GB = 8

    @staticmethod
    def _run_su(cmd):
        """Helper to run su commands with delay and try-except."""
        try:
            time.sleep(0.5) # Stability delay
            result = subprocess.run(f"su -c '{cmd}'", shell=True, capture_output=True, text=True)
            if result.returncode != 0:
                logger.warning(f"SU Command failed: {cmd} | Error: {result.stderr.strip()}")
            return result
        except Exception as e:
            logger.error(f"Execution error for '{cmd}': {e}")
            return None

    @staticmethod
    def setup_swap():
        """Check and setup 8GB swap file on /data."""
        try:
            if os.path.exists(MemoryManager.SWAP_PATH):
                logger.info("Swap file already exists.")
                return

            logger.info(f"Creating {MemoryManager.SWAP_SIZE_GB}GB swap file...")
            MemoryManager._run_su(f"dd if=/dev/zero of={MemoryManager.SWAP_PATH} bs=1M count={MemoryManager.SWAP_SIZE_GB * 1024}")
            MemoryManager._run_su(f"chmod 600 {MemoryManager.SWAP_PATH}")
            MemoryManager._run_su(f"mkswap {MemoryManager.SWAP_PATH}")
            MemoryManager._run_su(f"swapon {MemoryManager.SWAP_PATH}")
        except Exception as e:
            logger.error(f"Global swap setup error: {e}")

    @staticmethod
    def deep_clean_clone(pkg_name):
        """Clean caches and textures for a specific clone."""
        try:
            base_path = f"/data/data/{pkg_name}"
            folders_to_clean = ["cache", "code_cache", "app_textures", "app_webview"]
            for folder in folders_to_clean:
                path = os.path.join(base_path, folder)
                MemoryManager._run_su(f"rm -rf {path}/*")
            logger.info(f"Cleaned caches for {pkg_name}")
        except Exception as e:
            logger.error(f"Cleaning error for {pkg_name}: {e}")

    @staticmethod
    def drop_system_caches():
        """Drop system caches to free up RAM. Handles Read-only FS gracefully."""
        try:
            MemoryManager._run_su("sync")
            MemoryManager._run_su("echo 3 > /proc/sys/vm/drop_caches")
        except Exception as e:
            logger.error(f"Error during cache drop: {e}")

    @staticmethod
    def set_oom_priority():
        """Set this process to the highest OOM priority."""
        try:
            pid = os.getpid()
            MemoryManager._run_su(f"echo -1000 > /proc/{pid}/oom_score_adj")
        except Exception as e:
            logger.error(f"Failed to set OOM priority: {e}")

if __name__ == "__main__":
    # Test (requires root on Android)
    MemoryManager.set_oom_priority()
    MemoryManager.drop_system_caches()
