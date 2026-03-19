# -*- coding: utf-8 -*-
import logging
import subprocess

logger = logging.getLogger("BashUtils")

def run_bash(cmd: str) -> tuple[int, str, str]:
    """Выполняет bash команду синхронно и возвращает (код_возврата, stdout, stderr)"""
    try:
        # Use subprocess.run for synchronous execution as requested in V10.9
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=30
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        logger.error(f"Bash Execution Error: {e} | CMD: {cmd}")
        return -1, "", str(e)
