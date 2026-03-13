import os
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MemoryManager")

class MemoryManager:
    SWAP_PATH = "/data/swapfile"
    SWAP_SIZE_GB = 8

    @staticmethod
    def setup_swap():
        """Check and setup 8GB swap file on /data."""
        if os.path.exists(MemoryManager.SWAP_PATH):
            logger.info("Swap file already exists.")
            return

        logger.info(f"Creating {MemoryManager.SWAP_SIZE_GB}GB swap file at {MemoryManager.SWAP_PATH}...")
        try:
            # Requires root
            commands = [
                f"su -c 'dd if=/dev/zero of={MemoryManager.SWAP_PATH} bs=1M count={MemoryManager.SWAP_SIZE_GB * 1024}'",
                f"su -c 'chmod 600 {MemoryManager.SWAP_PATH}'",
                f"su -c 'mkswap {MemoryManager.SWAP_PATH}'",
                f"su -c 'swapon {MemoryManager.SWAP_PATH}'"
            ]
            for cmd in commands:
                subprocess.run(cmd, shell=True, check=True)
            logger.info("Swap setup complete.")
        except Exception as e:
            logger.error(f"Failed to setup swap: {e}")

    @staticmethod
    def deep_clean_clone(pkg_name):
        """Clean caches and textures for a specific clone."""
        base_path = f"/data/data/{pkg_name}"
        folders_to_clean = ["cache", "code_cache", "app_textures", "app_webview"]
        
        for folder in folders_to_clean:
            path = os.path.join(base_path, folder)
            try:
                subprocess.run(f"su -c 'rm -rf {path}/*'", shell=True)
                logger.info(f"Cleaned {path}")
            except Exception as e:
                logger.warning(f"Failed to clean {path}: {e}")

    @staticmethod
    def drop_system_caches():
        """Drop system caches to free up RAM."""
        try:
            subprocess.run("su -c 'sync && echo 3 > /proc/sys/vm/drop_caches'", shell=True)
            logger.info("System caches dropped.")
        except Exception as e:
            logger.error(f"Failed to drop system caches: {e}")

    @staticmethod
    def set_oom_priority():
        """Set this process to the highest OOM priority so it's not killed."""
        try:
            pid = os.getpid()
            subprocess.run(f"su -c 'echo -1000 > /proc/{pid}/oom_score_adj'", shell=True)
            logger.info(f"OOM priority set to -1000 for PID {pid}")
        except Exception as e:
            logger.error(f"Failed to set OOM priority: {e}")

if __name__ == "__main__":
    # Test (requires root on Android)
    MemoryManager.set_oom_priority()
    MemoryManager.drop_system_caches()
