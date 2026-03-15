# -*- coding: utf-8 -*-
import asyncio
import logging
import sqlite3
import os
from bash_utils import run_bash

logger = logging.getLogger("InjectionEngine")

class InjectionEngine:
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
            # 1. Force Stop
            await update_status(f"⏳ ({clone_name}) 1/4: Остановка...")
            await run_bash(f"su -c 'am force-stop com.roblox.{clone_name}'")
            await asyncio.sleep(1)

            # 2. SQLite Injection
            await update_status(f"⏳ ({clone_name}) 2/4: Инъекция Cookie (Python)...")
            db_path = f"/data/data/com.roblox.{clone_name}/app_webview/Default/Cookies"
            local_db = f"/data/local/tmp/cookies_{clone_name}.db"
            
            # Копируем файл базы из закрытой директории и даем права
            copy_out_cmd = f"su -c 'cp {db_path} {local_db} && chmod 777 {local_db}'"
            ret, stdout, stderr = await run_bash(copy_out_cmd)
            if ret != 0:
                await update_status(f"❌ Ошибка копирования БД ({clone_name}):\n{stderr}")
                return False

            # Открываем БД локально средствами Python
            try:
                conn = sqlite3.connect(local_db)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM cookies;")
                cursor.execute(f"INSERT INTO cookies (host_key, name, value, path, expires_utc, is_secure, is_httponly, has_expires, is_persistent, samesite, source_port) VALUES ('.roblox.com', '.ROBLOSECURITY', '{cookie}', '/', 253402300799000000, 1, 1, 1, 1, -1, -1);")
                conn.commit()
                conn.close()
            except Exception as e:
                await update_status(f"❌ Ошибка SQLite Python ({clone_name}):\n{e}")
                return False

            # Возвращаем модифицированный файл обратно
            copy_in_cmd = f"su -c 'cp {local_db} {db_path}'"
            ret, stdout, stderr = await run_bash(copy_in_cmd)
            if ret != 0:
                await update_status(f"❌ Ошибка возврата БД ({clone_name}):\n{stderr}")
                return False
                
            # Удаляем временный файл
            if os.path.exists(local_db):
                os.remove(local_db)

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

            # 4. Launch (Monkey / Intent)
            await update_status(f"⏳ ({clone_name}) 4/4: Запуск...")
            if place_id:
                join_cmd = f"su -c 'am start -a android.intent.action.VIEW -d \"roblox://placeId={place_id}\" com.roblox.{clone_name}'"
                await run_bash(join_cmd)
            else:
                await run_bash(f"su -c 'monkey -p com.roblox.{clone_name} -c android.intent.category.LAUNCHER 1'")
                
            await update_status(f"✅ Запущено ({clone_name})")
            return True
            
        except Exception as e:
            logger.error(f"Launch Sequence Error for {clone_name}: {e}")
            await update_status(f"❌ Критическая ошибка ({clone_name}): {str(e)}")
            return False

    @staticmethod
    async def stop(clone_name: str) -> bool:
        ret, stdout, stderr = await run_bash(f"su -c 'am force-stop com.roblox.{clone_name}'")
        return ret == 0

    @staticmethod
    async def clean(clone_name: str) -> bool:
        await InjectionEngine.stop(clone_name)
        ret, stdout, stderr = await run_bash(f"su -c 'rm -rf /data/data/com.roblox.{clone_name}/cache/*'")
        return ret == 0
