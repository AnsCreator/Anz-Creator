"""
Persistent user settings backed by a YAML file in %APPDATA%.
"""

import os
from pathlib import Path
from typing import Any
import yaml
from utils.logger import log

_DEFAULT = {
    "models": {
        "yolov8": "yolov8m",
        "sam2": "sam2_hiera_base_plus",
        "propainter": "standard",
    },
    "video": {
        "default_quality": "1080p",
        "default_format": "mp4",
    },
    "ui": {
        "theme": "dark_teal.xml",
        "sidebar_collapsed": False,
    },
    "paths": {
        "last_output_dir": "",
    },
}

_SETTINGS_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "Anz-Creator",
)
_SETTINGS_FILE = os.path.join(_SETTINGS_DIR, "settings.yaml")


class Settings:
    """Singleton-style settings store."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._data = {}
            inst._load()
            cls._instance = inst
        return cls._instance

    def _load(self):
        Path(_SETTINGS_DIR).mkdir(parents=True, exist_ok=True)
        if os.path.isfile(_SETTINGS_FILE):
            try:
                with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    loaded = yaml.safe_load(f)
                    self._data = loaded if isinstance(loaded, dict) else {}
                log.info("Settings loaded from %s", _SETTINGS_FILE)
            except Exception as exc:
                log.warning("Failed to read settings, using defaults: %s", exc)
                self._data = {}
        self._data = _deep_merge(_DEFAULT, self._data)

    def save(self):
        try:
            Path(_SETTINGS_DIR).mkdir(parents=True, exist_ok=True)
            with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
                yaml.dump(self._data, f, default_flow_style=False)
            log.debug("Settings saved.")
        except Exception as exc:
            log.error("Failed to save settings: %s", exc)

    def get(self, dotpath: str, default: Any = None) -> Any:
        keys = dotpath.split(".")
        node = self._data
        for k in keys:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                return default
        return node

    # PERBAIKAN: Fungsi khusus path untuk membaca %APPDATA%
    def get_path(self, dotpath: str, default: Any = None) -> str:
        """Mengembalikan nilai konfigurasi dan mengekstrak env vars (e.g. %APPDATA%)."""
        val = self.get(dotpath, default)
        if isinstance(val, str):
            return os.path.expandvars(os.path.expanduser(val))
        return val

    def set(self, dotpath: str, value: Any):
        keys = dotpath.split(".")
        node = self._data
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value
        self.save()

    @property
    def data(self) -> dict:
        return self._data

    @classmethod
    def reset_instance(cls):
        cls._instance = None

def _deep_merge(base: dict, override: dict) -> dict:
    merged = base.copy()
    for k, v in override.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged
