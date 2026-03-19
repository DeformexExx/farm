# -*- coding: utf-8 -*-
import asyncio
import logging
import time
import re
from bash_utils import run_bash

logger = logging.getLogger("InjectionEngine")

class InjectionEngine:
    
    # ═══════════════════════════════════════════════════════════════════════
    # V7.0 GLOBAL START LOCK — Prevents concurrent am start calls
    # ═══════════════════════════════════════════════════════════════════════
    _start_lock = asyncio.Lock()
    
    @staticmethod
    async def get_clone_pid(clone_name: str) -> str:
        """V11.1: Absolute PID Hunter — Precise ps-grep for ugPhone kernel"""
        # User Directive: ps -A | grep -i "com.roblox.clien{suffix}" | awk '{print $2}'
        # clone_name is the suffix (e.g. 'clienb')
        cmd = f"su -c \"ps -A | grep -i 'com.roblox.{clone_name}' | grep -v grep | awk '{{print $2}}'\""
        ret, stdout, _ = run_bash(cmd)
        
        if ret == 0 and stdout.strip():
            pids = stdout.strip().split()
            if pids:
                return pids[-1]
        return ""
    
    @staticmethod
    async def clear_memory():
        """Send memory clear command to OS to prevent Chain Crash effect."""
        run_bash("su -c 'echo 3 > /proc/sys/vm/drop_caches'")
        run_bash("su -c 'am trim-memory RUNNING_CRITICAL'")
        run_bash("su -c 'kill -10 1' 2>/dev/null || true")
    
    @staticmethod
    async def kill_by_pid(pid: str, clone_name: str) -> bool:
        """Targeted Kill V7.3: Graceful then Force."""
        if not pid: return False
        pid_clean = str(pid).strip().split()[0]
        if not pid_clean.isdigit(): return False
        
        package = f"com.roblox.{clone_name}"
        ret, cmdline, _ = run_bash(f"su -c 'cat /proc/{pid_clean}/cmdline 2>/dev/null || echo UNKNOWN'")
        if package not in cmdline:
            ret2, ps_out, _ = run_bash(f"su -c 'ps -A | grep {pid_clean}'")
            if package not in ps_out: return False
            
        run_bash(f"su -c 'kill -15 {pid_clean}'")
        for _ in range(6):
            await asyncio.sleep(0.5)
            _, stdout, _ = run_bash(f"su -c 'kill -0 {pid_clean} 2>/dev/null && echo ALIVE || echo DEAD'")
            if "DEAD" in stdout: return True
            
        run_bash(f"su -c 'kill -9 {pid_clean}'")
        await asyncio.sleep(0.5)
        _, stdout, _ = run_bash(f"su -c 'kill -0 {pid_clean} 2>/dev/null && echo ALIVE || echo DEAD'")
        return "DEAD" in stdout

    @staticmethod
    async def stop(clone_name: str) -> bool:
        """Targeted isolation stop."""
        await InjectionEngine.clear_memory()
        pid = await InjectionEngine.get_clone_pid(clone_name)
        if not pid: return True
        return await InjectionEngine.kill_by_pid(pid, clone_name)

    @staticmethod
    async def get_running_clones() -> list:
        """V11.0: Robust scan for all active Roblox clones."""
        active = []
        # Find all com.roblox processes
        ret, stdout, _ = run_bash("su -c \"ps -A | grep 'com.roblox' | grep -v grep\"")
        if ret == 0 and stdout.strip():
            for line in stdout.strip().split('\n'):
                # Extract package name (usually the last column)
                parts = line.split()
                if len(parts) >= 8:
                    pkg = parts[-1]
                    if "com.roblox." in pkg:
                        name = pkg.split("com.roblox.")[-1]
                        if name not in active:
                            active.append(name)
        return active

    @staticmethod
    async def clear_app_cache(clone_name: str):
        """Silently clear cache."""
        ret, _, _ = run_bash(f"su -c 'rm -rf /data/data/com.roblox.{clone_name}/cache/*'")
        return ret == 0

    @staticmethod
    async def clean(clone_name: str) -> bool:
        """Stop and clear cache."""
        await InjectionEngine.stop(clone_name)
        await InjectionEngine.clear_memory()
        return await InjectionEngine.clear_app_cache(clone_name)

    @staticmethod
    async def inject_and_launch(clone_name: str, cookie: str, place_id: str, status_msg=None) -> bool:
        """V10.9 FINAL: Strictly ordered injection with StartLock."""
        async def update_status(text: str):
            logger.info(text)
            if status_msg:
                try: await status_msg.edit_text(text)
                except: pass

        async with InjectionEngine._start_lock:
            try:
                await update_status(f"⏳ ({clone_name}) 2/4: Инъекция Cookie...")
                run_bash(f"su -c 'mkdir -p /data/data/com.roblox.{clone_name}/shared_prefs'")
                xml = f'<?xml version=\'1.0\' encoding=\'utf-8\' standalone=\'yes\' ?>\\n<map>\\n    <string name=\\".ROBLOSECURITY\\">{cookie}</string>\\n</map>'
                run_bash(f"su -c 'echo -e \"{xml}\" > /data/data/com.roblox.{clone_name}/shared_prefs/com.roblox.roblox.xml'")
                
                await update_status(f"⏳ ({clone_name}) 3/4: Настройка прав...")
                run_bash(f"su -c 'chmod 660 /data/data/com.roblox.{clone_name}/shared_prefs/com.roblox.roblox.xml'")
                run_bash(f"su -c 'chown $(stat -c %u:%g /data/data/com.roblox.{clone_name}) /data/data/com.roblox.{clone_name}/shared_prefs/com.roblox.roblox.xml'")

                await update_status(f"⏳ ({clone_name}) 4/4: Запуск...")
                run_bash(f"su -c 'monkey -p com.roblox.{clone_name} 1'")
                
                if place_id:
                    await asyncio.sleep(6)
                    m = re.search(r"code=([a-zA-Z0-9]+)", str(place_id))
                    intent = f"roblox://navigation/share_links?code={m.group(1)}&type=Server" if m else (f"roblox://placeId={place_id}" if str(place_id).isdigit() else str(place_id))
                    run_bash(f"su -c 'am start -a android.intent.action.VIEW -d \"{intent}\" com.roblox.{clone_name}'")
                    
                await update_status(f"✅ Запущено ({clone_name})")
                
                await asyncio.sleep(2)
                ret, pids, _ = run_bash(f"su -c 'pidof com.roblox.{clone_name}'")
                if ret == 0:
                    for p in pids.split():
                        run_bash(f"su -c 'echo -1000 > /proc/{p}/oom_score_adj 2>/dev/null'")
                return True
            except Exception as e:
                await update_status(f"❌ Ошибка ({clone_name}): {e}")
                return False
