import os
import threading
from pathlib import Path
import yaml
from typing import Any

_DEFAULT = {
    "models": {
        "yolov8": "yolov8m",
        "sam2": "sam2_hiera_base_plus", # Default model SAM2
        "propainter": "standard",
    }
}

_SETTINGS_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "Anz-Creator",
)
_SETTINGS_FILE = os.path.join(_SETTINGS_DIR, "settings.yaml")

class Settings:
    """Singleton untuk menyimpan pengaturan pengguna secara permanen di %APPDATA%."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._data = {}
                    inst._save_lock = threading.Lock()
                    inst._data_lock = threading.RLock()
                    inst._load()
                    cls._instance = inst
        return cls._instance

    def _load(self):
        with self._data_lock:
            Path(_SETTINGS_DIR).mkdir(parents=True, exist_ok=True)
            if os.path.isfile(_SETTINGS_FILE):
                try:
                    with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                        loaded = yaml.safe_load(f)
                        self._data = loaded if isinstance(loaded, dict) else {}
                except Exception:
                    self._data = {}
            # Gabungkan dengan default
            self._data = _deep_merge(_DEFAULT, self._data)

    def save(self):
        with self._save_lock:
            with self._data_lock:
                data_copy = self._data.copy()
            try:
                Path(_SETTINGS_DIR).mkdir(parents=True, exist_ok=True)
                tmp_file = _SETTINGS_FILE + ".tmp"
                with open(tmp_file, "w", encoding="utf-8") as f:
                    yaml.dump(data_copy, f, default_flow_style=False)
                os.replace(tmp_file, _SETTINGS_FILE) if os.path.exists(_SETTINGS_FILE) else os.rename(tmp_file, _SETTINGS_FILE)
            except Exception:
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

    def set(self, dotpath: str, value: Any):
        with self._data_lock:
            keys = dotpath.split(".")
            node = self._data
            for k in keys[:-1]:
                node = node.setdefault(k, {})
            node[keys[-1]] = value
        self.save()

def _deep_merge(base: dict, override: dict) -> dict:
    merged = base.copy()
    for k, v in override.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged
