# -*- coding: utf-8 -*-
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import logging
import time
from functools import wraps

logger = logging.getLogger("AegisV7_Sheet")

def retry_on_failure(retries=3, delay=3):
    """v7 Overlord Retry Decorator."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            last_err = None
            for attempt in range(retries):
                try:
                    # Auto-reconnect if client or sheet is missing
                    if not self.client or not self.sheet:
                        self.connect()
                    return func(self, *args, **kwargs)
                except Exception as e:
                    last_err = e
                    err_str = str(e).lower()
                    logger.warning(f"Ошибка таблицы ({attempt+1}/{retries}): {e}")
                    
                    # Force reconnect on JWT or Auth errors
                    if any(x in err_str for x in ["jwt", "auth", "signature", "token", "expire"]):
                        self.connect()
                    
                    time.sleep(delay)
            logger.error(f"Критический сбой после {retries} попыток: {last_err}")
            return None
        return wrapper
    return decorator

class SheetManager:
    COL_DEVICE_ID = 1
    COL_INSTANCE = 2
    COL_ACC_NAME = 3
    COL_STATUS = 4
    COL_COOKIE = 5

    def __init__(self, json_key_path, sheet_name):
        self.json_key_path = json_key_path
        self.scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        self.sheet_name = sheet_name
        self.creds = None
        self.client = None
        self.sheet = None

    def connect(self):
        """v7 Reconnection Logic."""
        try:
            self.creds = ServiceAccountCredentials.from_json_keyfile_name(self.json_key_path, self.scope)
            self.client = gspread.authorize(self.creds)
            self.sheet = self.client.open(self.sheet_name).get_worksheet(0)
            logger.info("✅ Подключение к Google Sheets успешно.")
            return True
        except Exception as e:
            logger.error(f"❌ Сбой подключения: {e}")
            return False

    @retry_on_failure()
    def get_my_clones(self, device_id):
        all_records = self.sheet.get_all_values()
        clones = []
        for i, row in enumerate(all_records[1:], start=2):
            if i > len(all_records): break # Safety
            if len(row) < 5: continue
            
            if row[self.COL_DEVICE_ID-1] == device_id:
                clones.append({
                    "row": i,
                    "instance": row[self.COL_INSTANCE-1],
                    "name": row[self.COL_ACC_NAME-1],
                    "status": row[self.COL_STATUS-1],
                    "cookie": row[self.COL_COOKIE-1]
                })
        return clones

    @retry_on_failure()
    def update_status(self, row_index, status):
        self.sheet.update_cell(row_index, self.COL_STATUS, status)
        return True
