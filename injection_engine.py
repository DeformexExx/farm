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
    
    # ═══════════════════════════════════════════════════════════════════════
    # PID MANAGEMENT — Targeted Isolation v7.0
    # ═══════════════════════════════════════════════════════════════════════
    @staticmethod
    async def get_clone_pid(clone_name: str) -> str:
        """Get specific PID for a clone. Returns empty string if not running."""
        package = f"com.roblox.{clone_name}"
        ret, stdout, _ = await run_bash(f"su -c 'pidof {package}'")
        if ret == 0 and stdout.strip():
            # pidof can return multiple PIDs, take the first one
            return stdout.strip().split()[0]
        return ""
    
    @staticmethod
    async def clear_memory():
        """Send memory clear command to OS to prevent Chain Crash effect."""
        # Drop caches (requires root)
        await run_bash("su -c 'echo 3 > /proc/sys/vm/drop_caches'")
        # Trim caches via activity manager
        await run_bash("su -c 'am trim-memory RUNNING_CRITICAL'")
        # Trigger garbage collection hint
        await run_bash("su -c 'kill -10 1' 2>/dev/null || true")  # SIGUSR1 to init, optional
    
    @staticmethod
    async def kill_by_pid(pid: str, clone_name: str) -> bool:
        """
        V7.3 TARGETED KILL: Graceful (-15) then Force (-9) if needed.
        VALIDATION: Only kills PIDs that belong to the specific Roblox clone.
        NEVER use pkill or am force-stop.
        """
        if not pid:
            logger.warning(f"[{clone_name}] No PID provided for kill.")
            return False
        
        # V7.3 FIX: Clean PID - take first number only, strip whitespace
        pid_clean = str(pid).strip().split()[0]
        if not pid_clean.isdigit():
            logger.error(f"[{clone_name}] Invalid PID format: {pid}")
            return False
        
        # V7.0 VALIDATION: Verify PID belongs to target clone
        package = f"com.roblox.{clone_name}"
        try:
            # Check /proc/{pid_clean}/cmdline to verify ownership
            ret, cmdline, _ = await run_bash(f"su -c 'cat /proc/{pid_clean}/cmdline 2>/dev/null || echo UNKNOWN'")
            if ret != 0 or not cmdline or package not in cmdline:
                # Fallback: check ps output
                ret2, ps_out, _ = await run_bash(f"su -c 'ps -A | grep {pid_clean}'")
                if ret2 != 0 or package not in ps_out:
                    logger.error(f"⚓ ANCHOR: PID {pid_clean} VALIDATION FAILED - does not belong to {package}. ABORTING KILL.")
                    return False
        except Exception as e:
            logger.warning(f"⚓ ANCHOR: PID validation warning: {e}")
        
        logger.info(f"⚓ ANCHOR: [{clone_name}] Targeted kill initiated for PID {pid_clean}")
        
        # Step 1: Graceful shutdown (SIGTERM)
        ret, _, _ = await run_bash(f"su -c 'kill -15 {pid_clean}'")
        
        # Wait up to 3 seconds for graceful exit
        for i in range(6):
            await asyncio.sleep(0.5)
            _, stdout, _ = await run_bash(f"su -c 'kill -0 {pid_clean} 2>/dev/null && echo ALIVE || echo DEAD'")
            if "DEAD" in stdout:
                logger.info(f"⚓ ANCHOR: [{clone_name}] PID {pid_clean} exited gracefully.")
                return True
        
        # Step 2: Force kill (SIGKILL) if still alive
        logger.warning(f"⚓ ANCHOR: [{clone_name}] PID {pid_clean} resisted SIGTERM, applying SIGKILL...")
        ret, _, _ = await run_bash(f"su -c 'kill -9 {pid_clean}'")
        await asyncio.sleep(0.5)
        
        # Verify death
        _, stdout, _ = await run_bash(f"su -c 'kill -0 {pid_clean} 2>/dev/null && echo ALIVE || echo DEAD'")
        success = "DEAD" in stdout
        if success:
            logger.info(f"⚓ ANCHOR: [{clone_name}] PID {pid_clean} terminated forcefully.")
        else:
            logger.error(f"⚓ ANCHOR: [{clone_name}] FAILED to kill PID {pid_clean}!")
        return success
    
    @staticmethod
    async def stop(clone_name: str) -> bool:
        """
        TARGETED ISOLATION: Find specific PID and kill it.
        NEVER touches com.roblox.client base unless confirmed as target.
        """
        # Clear memory BEFORE closing to prevent Chain Crash
        await InjectionEngine.clear_memory()
        await asyncio.sleep(0.3)
        
        # Get specific PID
        pid = await InjectionEngine.get_clone_pid(clone_name)
        if not pid:
            logger.info(f"[{clone_name}] Not running (no PID found).")
            return True  # Already stopped
        
        # Targeted kill
        success = await InjectionEngine.kill_by_pid(pid, clone_name)
        
        # Cleanup any remaining orphans for this package specifically
        package = f"com.roblox.{clone_name}"
        ret, stdout, _ = await run_bash(f"su -c 'ps -A | grep {package} | grep -v grep'")
        if ret == 0 and stdout.strip():
            # Found orphans, get their PIDs
            for line in stdout.strip().split('\n'):
                parts = line.split()
                if len(parts) >= 2:
                    orphan_pid = parts[1]
                    if orphan_pid != pid:
                        logger.warning(f"[{clone_name}] Cleaning orphan PID {orphan_pid}")
                        await InjectionEngine.kill_by_pid(orphan_pid, clone_name)
        
        return success
    
    @staticmethod
    async def clean(clone_name: str) -> bool:
        """Stop clone and clear its cache."""
        await InjectionEngine.stop(clone_name)
        # Clear memory again after stop
        await InjectionEngine.clear_memory()
        # Clear app cache
        ret, stdout, stderr = await run_bash(f"su -c 'rm -rf /data/data/com.roblox.{clone_name}/cache/*'")
        return ret == 0
    @staticmethod
    async def inject_and_launch(clone_name: str, cookie: str, place_id: str, status_msg=None) -> bool:
        """
        The strictly ordered, pure-bash injection mechanism.
        Возвращает True если запуск успешен, иначе False.
        Обновляет статус через status_msg.edit_text(text) если передан.
        """
        async def update_status(text: str):
            logger.info(text)
            if status_msg:
                try:
                    await status_msg.edit_text(text)
                except Exception:
                    pass

        try:
            # 1. Skip Cleanup (V5.0 SAFE MODE)
            # await run_bash(f"su -c 'am force-stop com.roblox.{clone_name}'")

            # 2. SQLite Injection (STRICT BASH)
            await update_status(f"⏳ ({clone_name}) 2/4: Инъекция Cookie (BASH)...")
            
            sqlite_bin = "/data/data/com.termux/files/usr/bin/sqlite3"
            db_path = f"/data/data/com.roblox.{clone_name}/app_webview/Default/Cookies"
            
            # Calculate Timestamp in microseconds
            current_time = int(time.time() * 1000000)
            
            sql_del = "DELETE FROM cookies;"
            sql_ins = (
                f"INSERT INTO cookies ("
                f"creation_utc, host_key, top_frame_site_key, name, value, "
                f"path, expires_utc, is_secure, is_httponly, last_access_utc, "
                f"has_expires, is_persistent, samesite, source_port"
                f") VALUES ("
                f"{current_time}, '.roblox.com', '', '.ROBLOSECURITY', '{cookie}', "
                f"'/', 253402300799000000, 1, 1, {current_time}, "
                f"1, 1, -1, -1"
                f");"
            )
            
            # Form the full su command with escaped quotes for sqlite
            inj_cmd = f"su -c \"{sqlite_bin} {db_path} \\\"{sql_del} {sql_ins}\\\"\""
            ret, stdout, stderr = await run_bash(inj_cmd)
            
            if ret != 0:
                await update_status(f"❌ SQLite Ошибка ({clone_name}):\n{stderr}")
                return False

            # 3. Permissions Fix (CRITICAL)
            await update_status(f"⏳ ({clone_name}) 3/4: Восстановление прав...")
            chown_cmd = f"su -c \"chown \\$(stat -c %u:%g /data/data/com.roblox.{clone_name}) {db_path}\""
            ret, stdout, stderr = await run_bash(chown_cmd)
            
            if ret != 0:
                if "Permission denied" in stderr or "not found" in stderr:
                    await update_status(f"❌ Root Error ({clone_name}): Устройство без Root или tsu не установлен.\n{stderr}")
                else:
                    await update_status(f"❌ Chown Ошибка ({clone_name}):\n{stderr}")
                return False

            # 4. Launch (Monkey / Intent) (Golden Sequence)
            await update_status(f"⏳ ({clone_name}) 4/4: Запуск (Awaken)...")
            
            # Step 1: Force Stop (already done at step 1, but user requested it again in sequence)
            # await run_bash(f"su -c 'am force-stop com.roblox.{clone_name}'")
            
            # Step 3: Start the app (Awaken)
            ret, stdout, stderr = await run_bash(f"su -c 'monkey -p com.roblox.{clone_name} 1'")
            
            if ret != 0:
                await update_status(f"❌ Monkey Error ({clone_name}):\n{stderr}")
                return False

            if place_id:
                # Step 4: WAIT 6 SECONDS (ugPhone needs time)
                await asyncio.sleep(6)
                
                # Step 5: Send the Join command (Strike)
                import re
                share_code = None
                
                # Safe Extraction (Regex)
                match = re.search(r"code=([a-zA-Z0-9]+)", str(place_id))
                if match:
                    share_code = match.group(1)
                
                if share_code:
                    # Universal Intent Format (roblox://)
                    join_intent = f"roblox://navigation/share_links?code={share_code}&type=Server"
                    join_cmd = f"su -c 'am start -W -a android.intent.action.VIEW -d \"{join_intent}\" com.roblox.{clone_name}'"
                    ret, stdout, stderr = await run_bash(join_cmd)
                    if ret != 0:
                        logger.error(f"Join Intent fail for {clone_name}: {stderr}")
                else:
                    # Fallback to standard PlaceID or direct URL
                    if str(place_id).isdigit():
                        join_cmd = f"su -c 'am start -W -a android.intent.action.VIEW -d \"roblox://placeId={place_id}\" com.roblox.{clone_name}'"
                    else:
                        join_cmd = f"su -c 'am start -W -a android.intent.action.VIEW -d \"{place_id}\" com.roblox.{clone_name}'"
                    
                    ret, stdout, stderr = await run_bash(join_cmd)
                
            await update_status(f"✅ Запущено ({clone_name})")
            return True
            
        except Exception as e:
            logger.error(f"Launch Sequence Error for {clone_name}: {e}")
            await update_status(f"❌ Критическая ошибка ({clone_name}): {str(e)}")
            return False

# ═══════════════════════════════════════════════════════════════════════════
# V7.0 ASYNC LOCK WRAPPER for inject_and_launch
# ═══════════════════════════════════════════════════════════════════════════
_original_inject = InjectionEngine.inject_and_launch

async def _locked_inject(clone_name: str, cookie: str, place_id: str, status_msg=None) -> bool:
    """V7.0: Global StartLock wrapper to prevent concurrent am start calls."""
    async with InjectionEngine._start_lock:
        logger.info(f"⚓ ANCHOR: Global StartLock acquired for {clone_name}")
        return await _original_inject(clone_name, cookie, place_id, status_msg)

InjectionEngine.inject_and_launch = staticmethod(_locked_inject)
# ═══════════════════════════════════════════════════════════════════════════
