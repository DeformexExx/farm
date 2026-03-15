# -*- coding: utf-8 -*-
import json
import os
import logging

logger = logging.getLogger("PersistenceManager")

class PersistenceManager:
    def __init__(self, farm_dir: str):
        self.path = os.path.join(farm_dir, "persistence.json")
        self.targets = {} # EXPLICIT ATTRIBUTE V3.0 AS DICT
        self.auto_restore = True
        self.console_mode = False
        
        self.data = {
            "auto_restore": True,
            "console_mode": False,
            "target_clones": [], # Legacy
            "targets": {} # V3.0
        }
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded_data = json.load(f)
                    self.data.update(loaded_data)
                    # Sync attributes from dictionary
                    self.auto_restore = self.data.get("auto_restore", True)
                    self.console_mode = self.data.get("console_mode", False)
                    
                    # Sync targets: ensure it is a dict
                    raw_targets = self.data.get("targets", self.data.get("target_clones", []))
                    if isinstance(raw_targets, list):
                        self.targets = {name: True for name in raw_targets}
                    else:
                        self.targets = raw_targets if isinstance(raw_targets, dict) else {}
            except Exception as e:
                logger.error(f"Failed to load persistence: {e}")

    def save(self):
        try:
            # Sync dictionary from attributes before saving
            self.data["auto_restore"] = self.auto_restore
            self.data["console_mode"] = self.console_mode
            self.data["targets"] = self.targets
            # Keep legacy list in sync for older versions or other tools
            self.data["target_clones"] = list(self.targets.keys())
            
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save persistence: {e}")

    def add_target(self, name: str):
        self.targets[name] = True
        self.save()

    def remove_target(self, name: str):
        if name in self.targets:
            del self.targets[name]
            self.save()
