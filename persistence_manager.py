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
        self.targets: dict      = {}   # {clone_name: True}  — managed clones
        self.active_clones: list = []  # [clone_name, …]    — currently running
        self.auto_restore: bool  = True
        self.console_mode: bool  = False
        # ────────────────────────────────────────────────────────────────────

        self.load()

    # ──────────────────────────────────────────────────────────────────────
    def load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)

            self.auto_restore  = d.get("auto_restore", True)
            self.console_mode  = d.get("console_mode", False)

            # active_clones: simple list of running clone names
            ac = d.get("active_clones", [])
            self.active_clones = ac if isinstance(ac, list) else []

            # targets: dict migration from legacy list
            raw = d.get("targets", d.get("target_clones", []))
            if isinstance(raw, list):
                self.targets = {n: True for n in raw}
            elif isinstance(raw, dict):
                self.targets = raw
            else:
                self.targets = {}

            # Ensure active_clones and targets are in sync
            for n in self.active_clones:
                if n not in self.targets:
                    self.targets[n] = True

        except Exception as e:
            logger.error(f"PersistenceManager.load(): {e}")

    # ──────────────────────────────────────────────────────────────────────
    def save(self):
        try:
            payload = {
                "auto_restore":  self.auto_restore,
                "console_mode":  self.console_mode,
                "active_clones": self.active_clones,
                "targets":       self.targets,
                "target_clones": list(self.targets.keys()),  # legacy compat
            }
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"PersistenceManager.save(): {e}")

    # ──────────────────────────────────────────────────────────────────────
    def add_target(self, name: str):
        self.targets[name] = True
        if name not in self.active_clones:
            self.active_clones.append(name)
        self.save()

    def remove_target(self, name: str):
        self.targets.pop(name, None)
        if name in self.active_clones:
            self.active_clones.remove(name)
        self.save()
