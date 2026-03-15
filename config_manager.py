# -*- coding: utf-8 -*-
import os
import json
import logging

logger = logging.getLogger("ConfigManager")

class ConfigManager:
    def __init__(self, device_id: str, farm_dir: str):
        self.device_id = device_id
        self.farm_dir = farm_dir
        self.config_file = os.path.join(farm_dir, f"{device_id}.json")
        self.bot_token_file = os.path.join(farm_dir, "config.json")
        
        self.bot_token = ""
        self.admin_ids = []
        self.clones_data = []
        
        self.reload()

    def reload(self):
        """Перезагружает оба конфигурационных файла с диска"""
        self._load_bot_config()
        self._load_clones_config()
        logger.info("Configs reloaded successfully.")

    def _load_bot_config(self):
        if os.path.exists(self.bot_token_file):
            try:
                with open(self.bot_token_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.bot_token = data.get("bot_token", "")
                    self.admin_ids = data.get("admin_ids", [])
            except Exception as e:
                logger.error(f"Failed to load user bot config: {e}")
        else:
            logger.warning(f"Bot config not found: {self.bot_token_file}")

    def _load_clones_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # {DEVICE_ID}.json might wrap clones in "clones" key or be a list
                    self.clones_data = data.get("clones", []) if isinstance(data, dict) else data
            except Exception as e:
                logger.error(f"Failed to parse clones JSON: {e}")
        else:
            logger.warning(f"Clones config file not found: {self.config_file}")
            self.clones_data = []

    def get_clone(self, clone_name: str) -> dict:
        """Возвращает словарь с данными клона по имени"""
        for c in self.clones_data:
            if c.get("name") == clone_name:
                return c
        return {}
