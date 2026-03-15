# -*- coding: utf-8 -*-
import json
import os
import logging

logger = logging.getLogger("PersistenceManager")

class PersistenceManager:
    def __init__(self, farm_dir: str):
        self.path = os.path.join(farm_dir, "persistence.json")
        self.data = {
            "auto_restore": True,
            "console_mode": False,
            "target_clones": [],
            "targets": []
        }
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except Exception as e:
                logger.error(f"Failed to load persistence: {e}")

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save persistence: {e}")

    @property
    def auto_restore(self):
        return self.data.get("auto_restore", True)

    @auto_restore.setter
    def auto_restore(self, value: bool):
        self.data["auto_restore"] = value
        self.save()

    @property
    def console_mode(self):
        return self.data.get("console_mode", False)

    @console_mode.setter
    def console_mode(self, value: bool):
        self.data["console_mode"] = value
        self.save()

    @property
    def target_clones(self) -> list:
        val = self.data.get("target_clones", [])
        return val if isinstance(val, list) else []

    @property
    def targets(self) -> list:
        """Alias for target_clones (V3.0 Compatibility)"""
        val = self.data.get("targets", [])
        if not val: # Fallback to target_clones
             return self.target_clones
        return val if isinstance(val, list) else []

    def add_target(self, name: str):
        clones = self.targets
        if name not in clones:
            clones.append(name)
            self.data["targets"] = clones
            self.data["target_clones"] = clones # Sync legacy
            self.save()

    def remove_target(self, name: str):
        clones = self.targets
        if name in clones:
            clones.remove(name)
            self.data["targets"] = clones
            self.data["target_clones"] = clones # Sync legacy
            self.save()
