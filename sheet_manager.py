# -*- coding: utf-8 -*-
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import logging

logger = logging.getLogger("AegisV6_Sheet")

class SheetManager:
    # Column mapping (A=1, B=2, ...)
    COL_DEVICE_ID = 1
    COL_INSTANCE = 2
    COL_ACC_NAME = 3
    COL_STATUS = 4
    COL_COOKIE = 5

    def __init__(self, json_key_path, sheet_name):
        self.scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        self.creds = ServiceAccountCredentials.from_json_keyfile_name(json_key_path, self.scope)
        self.client = gspread.authorize(self.creds)
        self.sheet_name = sheet_name
        self.sheet = None

    def connect(self):
        try:
            self.sheet = self.client.open(self.sheet_name).get_worksheet(0)
            return True
        except Exception as e:
            logger.error(f"Sheet connection failed: {e}")
            return False

    def get_my_clones(self, device_id):
        """Fetches all rows matching DEVICE_ID."""
        try:
            all_records = self.sheet.get_all_values()
            clones = []
            for i, row in enumerate(all_records[1:], start=2): # Start from row 2 (header = 1)
                if row[self.COL_DEVICE_ID-1] == device_id:
                    clones.append({
                        "row": i,
                        "instance": row[self.COL_INSTANCE-1],
                        "name": row[self.COL_ACC_NAME-1],
                        "status": row[self.COL_STATUS-1],
                        "cookie": row[self.COL_COOKIE-1]
                    })
            return clones
        except Exception as e:
            logger.error(f"Error fetching clones: {e}")
            return []

    def update_status(self, row_index, status):
        """Updates the Status column (D) for a specific row."""
        try:
            self.sheet.update_cell(row_index, self.COL_STATUS, status)
            return True
        except Exception as e:
            logger.error(f"Error updating status: {e}")
            return False

if __name__ == "__main__":
    # Test stub
    logging.basicConfig(level=logging.INFO)
    test_manager = SheetManager("creds.json", "AegisFarmOS")
    if test_manager.connect():
        print(f"Clones for DEV_1: {test_manager.get_my_clones('DEV_1')}")
