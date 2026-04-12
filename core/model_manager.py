"""
Model Manager — auto-download, verify, and load AI models.
Models persist in %APPDATA%/Anz-Creator/models/.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

import requests
import yaml

from utils.logger import log

_APPDATA = os.environ.get("APPDATA", os.path.expanduser("~"))
MODELS_ROOT = os.path.join(_APPDATA, "Anz-Creator", "models")


class ModelManager:
    """Download, cache, and serve model file paths."""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "config.yaml",
            )
        with open(config_path, "r", encoding="utf-8") as f:
            self._cfg = yaml.safe_load(f)
        Path(MODELS_ROOT).mkdir(parents=True, exist_ok=True)
        log.info("ModelManager — root: %s", MODELS_ROOT)

    # ── public API ───────────────────────────────────────
    def model_path(self, family: str, variant: str) -> str:
        """Return local path for a model file."""
        ext = ".pt"
        return os.path.join(MODELS_ROOT, family, f"{variant}{ext}")

    def is_downloaded(self, family: str, variant: str) -> bool:
        return os.path.isfile(self.model_path(family, variant))

    def get_url(self, family: str, variant: str) -> Optional[str]:
        try:
            return self._cfg["models"][family]["options"][variant].get("url")
        except KeyError:
            return None

    def get_size_mb(self, family: str, variant: str) -> int:
        try:
            return self._cfg["models"][family]["options"][variant].get("size_mb", 0)
        except KeyError:
            return 0

    def list_variants(self, family: str) -> list[dict]:
        """Return list of {name, description, size_mb, downloaded}."""
        opts = self._cfg["models"].get(family, {}).get("options", {})
        out = []
        for name, info in opts.items():
            out.append({
                "name": name,
                "description": info.get("description", ""),
                "size_mb": info.get("size_mb", 0),
                "vram_gb": info.get("vram_gb", 0),
                "downloaded": self.is_downloaded(family, name),
            })
        return out

    def default_variant(self, family: str) -> str:
        return self._cfg["models"].get(family, {}).get("default", "")

    def download(
        self,
        family: str,
        variant: str,
        progress_callback: Callable[[int, str], None] = None,
        cancel_flag: Callable[[], bool] = None,
    ) -> str:
        """
        Download a model if not present. Returns local path.
        progress_callback(percent, message)
        """
        dest = self.model_path(family, variant)
        if os.path.isfile(dest):
            log.info("Model already cached: %s", dest)
            return dest

        url = self.get_url(family, variant)
        if not url:
            raise ValueError(f"No download URL for {family}/{variant}")

        Path(os.path.dirname(dest)).mkdir(parents=True, exist_ok=True)
        tmp = dest + ".part"
        size_mb = self.get_size_mb(family, variant)

        log.info("Downloading %s/%s (≈%dMB) from %s", family, variant, size_mb, url)
        if progress_callback:
            progress_callback(0, f"Downloading {variant}…")

        try:
            resp = requests.get(url, stream=True, timeout=30)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0

            with open(tmp, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    if cancel_flag and cancel_flag():
                        log.info("Download cancelled: %s", variant)
                        os.remove(tmp)
                        return ""
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0 and progress_callback:
                        pct = int(downloaded / total * 100)
                        progress_callback(
                            pct,
                            f"Downloading {variant}… {downloaded // 1048576}/{total // 1048576} MB",
                        )

            os.rename(tmp, dest)
            log.info("Model saved: %s", dest)
            if progress_callback:
                progress_callback(100, f"{variant} ready.")
            return dest

        except Exception as exc:
            if os.path.exists(tmp):
                os.remove(tmp)
            log.error("Download failed: %s", exc)
            raise

    def ensure_models(
        self,
        families: list[str],
        settings,
        progress_callback=None,
        cancel_flag=None,
    ) -> dict[str, str]:
        """Ensure all required default models are present. Returns {family: path}."""
        paths = {}
        for fam in families:
            variant = settings.get(f"models.{fam}") or self.default_variant(fam)
            path = self.download(
                fam, variant,
                progress_callback=progress_callback,
                cancel_flag=cancel_flag,
            )
            paths[fam] = path
        return paths
