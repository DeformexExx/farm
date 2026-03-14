# -*- coding: utf-8 -*-
import sqlite3
import subprocess
import os
import time
import requests
import logging

logger = logging.getLogger("AegisV6_Injector")

class CookieInjector:
    def __init__(self, log_func=print):
        self.log = log_func

    def validate_cookie(self, cookie):
        """Checks if cookie is alive via Roblox API."""
        try:
            headers = {"Cookie": f".ROBLOSECURITY={cookie}"}
            resp = requests.get("https://users.roblox.com/v1/users/authenticated", headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self.log(f"Cookie Valid: {data.get('name')} (ID: {data.get('id')})")
                return True
            return False
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False

    def inject(self, instance, cookie_value):
        """Direct SQLite injection into Android webview database."""
        pkg = f"com.roblox.{instance}"
        db_path = f"/data/data/{pkg}/app_webview/Default/Cookies"
        tmp_db = f"/data/local/tmp/cookies_{instance}.db"

        self.log(f"Injecting cookie into {instance}...")
        
        # 1. Force Stop
        subprocess.run(f"su -c 'am force-stop {pkg}'", shell=True)
        time.sleep(2)

        # 2. Check path / Cold Start
        check = subprocess.run(f"su -c 'ls {db_path}'", shell=True, capture_output=True)
        if check.returncode != 0:
            self.log("Database missing. Performing Cold Start...")
            subprocess.run(f"su -c 'monkey -p {pkg} -c android.intent.category.LAUNCHER 1'", shell=True)
            time.sleep(15)
            subprocess.run(f"su -c 'am force-stop {pkg}'", shell=True)
            time.sleep(2)

        # 3. Pull DB to tmp
        subprocess.run(f"su -c 'cp {db_path} {tmp_db}'", shell=True)
        subprocess.run(f"su -c 'chmod 666 {tmp_db}'", shell=True)

        # 4. SQLite Injection
        try:
            conn = sqlite3.connect(tmp_db)
            cursor = conn.cursor()
            
            # Timestamps in microseconds (Android/Chromium format)
            now_us = int(time.time() * 1000000)
            expiry_us = now_us + (365 * 24 * 3600 * 1000000) # 1 year

            # REPLACE INTO logic as per prompt
            # host_key, name, value, path, expires_utc, is_httponly, is_secure, samesite, creation_utc, last_access_utc, top_frame_site_key, has_expires, is_persistent
            cookie_tuple = (
                '.roblox.com', '.ROBLOSECURITY', cookie_value, '/',
                expiry_us, 1, 1, -1, now_us, now_us, '', 1, 1
            )
            
            cursor.execute("""
                REPLACE INTO cookies (
                    host_key, name, value, path, expires_utc, is_httponly, is_secure, 
                    samesite, creation_utc, last_access_utc, top_frame_site_key, 
                    has_expires, is_persistent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, cookie_tuple)
            
            conn.commit()
            conn.close()
            self.log("SQLite injection successful.")
        except Exception as e:
            self.log(f"SQLite Error: {e}")
            return False

        # 5. Push DB back and Fix Permissions
        subprocess.run(f"su -c 'cp {tmp_db} {db_path}'", shell=True)
        # Get original owner:group
        stat_res = subprocess.run(f"su -c 'stat -c %u:%g /data/data/{pkg}'", shell=True, capture_output=True, text=True)
        if stat_res.returncode == 0:
            owner = stat_res.stdout.strip()
            subprocess.run(f"su -c 'chown {owner} {db_path}'", shell=True)
            subprocess.run(f"su -c 'chmod 600 {db_path}'", shell=True)
            self.log(f"Permissions fixed for {owner}")

        # Cleanup
        os.remove(tmp_db)
        return True

if __name__ == "__main__":
    def l(t): print(f"[TEST] {t}")
    inj = CookieInjector(l)
    # inj.inject("clienb", "FAKE_COOKIE")
