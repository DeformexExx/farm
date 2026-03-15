# -*- coding: utf-8 -*-
# persistence_manager.py — Project Aegis V3.0
import json
import os
import logging

logger = logging.getLogger("PersistenceManager")

class PersistenceManager:
    def __init__(self, farm_dir: str):
        self.path = os.path.join(farm_dir, "persistence.json")

        # ── V3.0 ATOMIC INITIALISATION ──────────────────────────────────────
        self.targets: dict  = {}   # {clone_name: True}  — NEVER a list
        self.auto_restore: bool = True
        self.console_mode: bool = False
        # ────────────────────────────────────────────────────────────────────

        self.load()

    # ──────────────────────────────────────────────────────────────────────
    def load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)

            self.auto_restore = d.get("auto_restore", True)
            self.console_mode = d.get("console_mode", False)

            # Migrate legacy list → dict
            raw = d.get("targets", d.get("target_clones", []))
            if isinstance(raw, list):
                self.targets = {n: True for n in raw}
            elif isinstance(raw, dict):
                self.targets = raw
            else:
                self.targets = {}

        except Exception as e:
            logger.error(f"PersistenceManager.load(): {e}")

    # ──────────────────────────────────────────────────────────────────────
    def save(self):
        try:
            payload = {
                "auto_restore": self.auto_restore,
                "console_mode": self.console_mode,
                "targets": self.targets,
                "target_clones": list(self.targets.keys()),  # legacy compat
            }
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"PersistenceManager.save(): {e}")

    # ──────────────────────────────────────────────────────────────────────
    def add_target(self, name: str):
        self.targets[name] = True
        self.save()

    def remove_target(self, name: str):
        self.targets.pop(name, None)
        self.save()
