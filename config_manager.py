# -*- coding: utf-8 -*-
import json
import os
import logging

logger = logging.getLogger("AegisJSON")

class ConfigManager:
    """Aegis v7.1 JSON Data Layer."""
    def __init__(self, device_id):
        self.device_id = device_id
        self.filename = f"{device_id}.json"
        self.clones = []

    def load(self):
        """Loads configuration from local JSON."""
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r', encoding='utf-8') as f:
                    self.clones = json.load(f)
                logger.info(f"✅ Конфиг {self.filename} загружен ({len(self.clones)} клонов)")
                return True
            except Exception as e:
                logger.error(f"❌ Ошибка парсинга {self.filename}: {e}")
        else:
            logger.warning(f"⚠️ Файл {self.filename} не найден.")
            self.clones = []
        return False

    def save(self):
        """Saves current state to local JSON."""
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(self.clones, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения {self.filename}: {e}")
            return False

    def update_status(self, instance_name, status):
        """Updates the status of a specific clone in JSON."""
        for clone in self.clones:
            if clone.get("name") == instance_name:
                clone["status"] = status
                self.save()
                return True
        return False

    def get_clones(self):
        return self.clones
