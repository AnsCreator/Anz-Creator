"""
Model Manager — auto-download, verify, and load AI models.
Models persist in %APPDATA%/Anz-Creator/models/.
Includes auto-install for SAM2 package.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

import requests
import yaml

from utils.logger import log

_APPDATA = os.environ.get("APPDATA", os.path.expanduser("~"))
MODELS_ROOT = os.path.join(_APPDATA, "Anz-Creator", "models")


def _pip_install(package: str, quiet: bool = True) -> bool:
    """Install a pip package programmatically."""
    try:
        cmd = [sys.executable, "-m", "pip", "install"]
        if quiet:
            cmd.append("-q")
        cmd.append(package)

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        subprocess.check_call(cmd, creationflags=creationflags)
        return True
    except Exception as e:
        log.error("Failed to install %s: %s", package, e)
        return False


def _ensure_sam2_installed() -> bool:
    """Auto-install SAM2 if not present."""
    try:
        import sam2  # noqa: F401
        return True
    except ImportError:
        log.info("SAM2 not found — installing automatically…")
        success = _pip_install(
            "git+https://github.com/facebookresearch/segment-anything-2.git"
        )
        if success:
            log.info("SAM2 installed successfully.")
        else:
            log.error("SAM2 auto-install failed.")
        return success


class ModelManager:
    """Download, cache, and serve model file paths."""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "config.yaml",
            )
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self._cfg = yaml.safe_load(f) or {}
        except Exception as exc:
            log.error("Failed to load config: %s", exc)
            self._cfg = {}
        Path(MODELS_ROOT).mkdir(parents=True, exist_ok=True)
        self._download_lock = threading.Lock()
        log.info("ModelManager — root: %s", MODELS_ROOT)

    # ── public API ───────────────────────────────────────
    def model_path(self, family: str, variant: str) -> str:
        """Return local path for a model file."""
        ext = ".pt"
        return os.path.join(MODELS_ROOT, family, f"{variant}{ext}")

    def is_downloaded(self, family: str, variant: str) -> bool:
        path = self.model_path(family, variant)
        return os.path.isfile(path) and os.path.getsize(path) > 0

    def get_url(self, family: str, variant: str) -> Optional[str]:
        try:
            return self._cfg["models"][family]["options"][variant].get("url")
        except (KeyError, TypeError):
            return None

    def get_size_mb(self, family: str, variant: str) -> int:
        try:
            return self._cfg["models"][family]["options"][variant].get("size_mb", 0)
        except (KeyError, TypeError):
            return 0

    def list_variants(self, family: str) -> list[dict]:
        """Return list of {name, description, size_mb, downloaded}."""
        try:
            opts = self._cfg.get("models", {}).get(family, {}).get("options", {})
        except (AttributeError, TypeError):
            return []
        out = []
        for name, info in opts.items():
            if not isinstance(info, dict):
                continue
            out.append({
                "name": name,
                "description": info.get("description", ""),
                "size_mb": info.get("size_mb", 0),
                "vram_gb": info.get("vram_gb", 0),
                "downloaded": self.is_downloaded(family, name),
            })
        return out

    def default_variant(self, family: str) -> str:
        try:
            return self._cfg.get("models", {}).get(family, {}).get("default", "")
        except (AttributeError, TypeError):
            return ""

    def download(
        self,
        family: str,
        variant: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_flag: Optional[Callable[[], bool]] = None,
    ) -> str:
        """
        Download a model if not present. Returns local path.
        progress_callback(percent, message)
        Thread-safe: only one download per model at a time.
        """
        # Auto-install SAM2 package if needed
        if family == "sam2":
            if progress_callback:
                progress_callback(0, "Checking SAM2 installation…")
            if not _ensure_sam2_installed():
                raise RuntimeError(
                    "Failed to install SAM2 automatically.\n"
                    "Please install manually:\n"
                    "  pip install git+https://github.com/facebookresearch/segment-anything-2.git"
                )

        dest = self.model_path(family, variant)
        if self.is_downloaded(family, variant):
            log.info("Model already cached: %s", dest)
            if progress_callback:
                progress_callback(100, f"{variant} ready (cached).")
            return dest

        url = self.get_url(family, variant)
        if not url:
            raise ValueError(f"No download URL for {family}/{variant}")

        with self._download_lock:
            # Re-check after acquiring lock (another thread may have downloaded it)
            if self.is_downloaded(family, variant):
                log.info("Model already cached (after lock): %s", dest)
                if progress_callback:
                    progress_callback(100, f"{variant} ready (cached).")
                return dest

            Path(os.path.dirname(dest)).mkdir(parents=True, exist_ok=True)
            tmp = dest + ".part"
            size_mb = self.get_size_mb(family, variant)

            log.info("Downloading %s/%s (≈%dMB) from %s", family, variant, size_mb, url)
            if progress_callback:
                progress_callback(0, f"Downloading {variant}…")

            try:
                resp = requests.get(url, stream=True, timeout=(15, 30))
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                downloaded = 0

                with open(tmp, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 256):
                        if cancel_flag and cancel_flag():
                            log.info("Download cancelled: %s", variant)
                            f.close()
                            if os.path.exists(tmp):
                                os.remove(tmp)
                            return ""
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0 and progress_callback:
                            pct = int(downloaded / total * 100)
                            progress_callback(
                                pct,
                                f"Downloading {variant}… "
                                f"{downloaded // 1048576}/{total // 1048576} MB",
                            )

                # Verify download isn't empty/corrupt
                if os.path.getsize(tmp) == 0:
                    os.remove(tmp)
                    raise RuntimeError(f"Downloaded file is empty: {variant}")

                os.rename(tmp, dest)
                log.info("Model saved: %s", dest)
                if progress_callback:
                    progress_callback(100, f"{variant} ready.")
                return dest

            except Exception as exc:
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                log.error("Download failed: %s", exc)
                raise

    def ensure_models(
        self,
        families: list[str],
        settings,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_flag: Optional[Callable[[], bool]] = None,
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
