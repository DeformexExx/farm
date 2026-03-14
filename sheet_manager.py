# -*- coding: utf-8 -*-
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import logging
import time
from functools import wraps

logger = logging.getLogger("AegisV6_Sheet")

def retry_on_failure(retries=3, delay=2):
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            last_err = None
            for attempt in range(retries):
                try:
                    return func(self, *args, **kwargs)
                except Exception as e:
                    last_err = e
                    logger.warning(f"Sheet operation failed (attempt {attempt+1}/{retries}): {e}")
                    if "JWT" in str(e) or "auth" in str(e).lower():
                        self.refresh_creds()
                    time.sleep(delay)
            logger.error(f"Sheet operation failed after {retries} attempts: {last_err}")
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
        self.creds = ServiceAccountCredentials.from_json_keyfile_name(json_key_path, self.scope)
        self.client = gspread.authorize(self.creds)
        self.sheet_name = sheet_name
        self.sheet = None

    def refresh_creds(self):
        try:
            self.creds = ServiceAccountCredentials.from_json_keyfile_name(self.json_key_path, self.scope)
            self.client = gspread.authorize(self.creds)
            self.sheet = self.client.open(self.sheet_name).get_worksheet(0)
            logger.info("Credentials refreshed successfully.")
        except Exception as e:
            logger.error(f"Failed to refresh credentials: {e}")

    @retry_on_failure()
    def connect(self):
        self.sheet = self.client.open(self.sheet_name).get_worksheet(0)
        return True

    @retry_on_failure()
    def get_my_clones(self, device_id):
        all_records = self.sheet.get_all_values()
        clones = []
        for i, row in enumerate(all_records[1:], start=2):
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
