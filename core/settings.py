"""
Persistent user settings backed by a YAML file in %APPDATA%.
"""

import os
import threading
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
    """Singleton-style settings store with thread safety."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                # Double-check locking
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._data = {}
                    inst._save_lock = threading.Lock()
                    inst._data_lock = threading.RLock()  # Reentrant lock for data access
                    inst._load()
                    cls._instance = inst
        return cls._instance

    def _load(self):
        """Load settings from disk. Must hold _data_lock."""
        with self._data_lock:
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
            # Deep merge with defaults (protect with lock)
            self._data = _deep_merge(_DEFAULT, self._data)

    def save(self):
        """Save settings to disk atomically."""
        with self._save_lock:
            with self._data_lock:
                data_copy = self._data.copy()  # Avoid mutation during save
            try:
                Path(_SETTINGS_DIR).mkdir(parents=True, exist_ok=True)
                tmp_file = _SETTINGS_FILE + ".tmp"
                with open(tmp_file, "w", encoding="utf-8") as f:
                    yaml.dump(data_copy, f, default_flow_style=False)
                # Atomic rename
                if os.path.exists(_SETTINGS_FILE):
                    os.replace(tmp_file, _SETTINGS_FILE)
                else:
                    os.rename(tmp_file, _SETTINGS_FILE)
                log.debug("Settings saved.")
            except Exception as exc:
                log.error("Failed to save settings: %s", exc)
                tmp_file = _SETTINGS_FILE + ".tmp"
                if os.path.exists(tmp_file):
                    try:
                        os.remove(tmp_file)
                    except OSError:
                        pass

    def get(self, dotpath: str, default: Any = None) -> Any:
        with self._data_lock:
            keys = dotpath.split(".")
            node = self._data
            for k in keys:
                if isinstance(node, dict) and k in node:
                    node = node[k]
                else:
                    return default
            return node

    def get_path(self, dotpath: str, default: Any = None) -> Any:
        """Return config value with env vars expanded (e.g. %APPDATA%)."""
        val = self.get(dotpath, default)
        if isinstance(val, str):
            return os.path.expandvars(os.path.expanduser(val))
        return val

    def set(self, dotpath: str, value: Any):
        with self._data_lock:
            keys = dotpath.split(".")
            node = self._data
            for k in keys[:-1]:
                node = node.setdefault(k, {})
            node[keys[-1]] = value
        self.save()

    @property
    def data(self) -> dict:
        with self._data_lock:
            return self._data.copy()

    @classmethod
    def reset_instance(cls):
        with cls._lock:
            cls._instance = None


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge two dictionaries recursively. Does not modify inputs."""
    merged = base.copy()
    for k, v in override.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged
