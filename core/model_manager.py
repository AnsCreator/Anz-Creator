"""
Model Manager — auto-download, verify, and load AI models.
Models persist in %APPDATA%/Anz-Creator/models/.
Pre-bundled models take priority.
"""

from __future__ import annotations

import hashlib
import os
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

import requests
import yaml

from utils.logger import log

_APPDATA = os.environ.get("APPDATA", os.path.expanduser("~"))
MODELS_ROOT = os.path.join(_APPDATA, "Anz-Creator", "models")


def _get_bundled_models_path() -> str:
    """Get path to bundled models (when running as exe)."""
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, "models")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")


def _compute_sha256(filepath: str) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _verify_checksum(filepath: str, expected_sha256: str) -> bool:
    """Verify that file matches expected SHA-256."""
    if not expected_sha256:
        return True  # No checksum provided, skip verification
    actual = _compute_sha256(filepath)
    if actual != expected_sha256:
        log.error("Checksum mismatch for %s", filepath)
        log.error("Expected: %s", expected_sha256)
        log.error("Got:      %s", actual)
        return False
    return True


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

    def model_path(self, family: str, variant: str) -> str:
        """Return local path for a model file."""
        ext = ".pt"
        bundled_path = os.path.join(_get_bundled_models_path(), family, f"{variant}{ext}")

        # Return bundled path if exists
        if os.path.isfile(bundled_path):
            log.info("Using bundled model: %s", bundled_path)
            return bundled_path

        return os.path.join(MODELS_ROOT, family, f"{variant}{ext}")

    def is_downloaded(self, family: str, variant: str) -> bool:
        path = self.model_path(family, variant)
        return os.path.isfile(path) and os.path.getsize(path) > 0

    def get_url(self, family: str, variant: str) -> Optional[str]:
        try:
            return self._cfg["models"][family]["options"][variant].get("url")
        except (KeyError, TypeError):
            return None

    def get_checksum(self, family: str, variant: str) -> Optional[str]:
        """Get expected SHA-256 checksum from config."""
        try:
            return self._cfg["models"][family]["options"][variant].get("sha256")
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
        """Download a model if not present. Verifies checksum. Returns local path."""
        dest = self.model_path(family, variant)
        expected_checksum = self.get_checksum(family, variant)

        # Already have it (bundled or downloaded) – verify checksum if present
        if self.is_downloaded(family, variant):
            if expected_checksum and not _verify_checksum(dest, expected_checksum):
                log.warning("Cached model %s has invalid checksum, redownloading...", dest)
                os.remove(dest)
            else:
                log.info("Model already available: %s", dest)
                if progress_callback:
                    progress_callback(100, f"{variant} ready.")
                return dest

        url = self.get_url(family, variant)
        if not url:
            raise ValueError(f"No download URL for {family}/{variant}")

        with self._download_lock:
            # Re-check after acquiring lock
            if self.is_downloaded(family, variant):
                if expected_checksum and not _verify_checksum(dest, expected_checksum):
                    os.remove(dest)
                else:
                    log.info("Model already cached (after lock): %s", dest)
                    if progress_callback:
                        progress_callback(100, f"{variant} ready.")
                    return dest

            Path(os.path.dirname(dest)).mkdir(parents=True, exist_ok=True)
            tmp = dest + ".part"
            size_mb = self.get_size_mb(family, variant)

            log.info("Downloading %s/%s (≈%dMB) from %s", family, variant, size_mb, url)
            if progress_callback:
                progress_callback(0, f"Downloading {variant}…")

            # --- Download with resume support ---
            headers = {}
            existing_size = 0
            if os.path.exists(tmp):
                existing_size = os.path.getsize(tmp)
                if existing_size > 0:
                    headers["Range"] = f"bytes={existing_size}-"
                    log.info("Resuming download from byte %d", existing_size)

            try:
                resp = requests.get(url, stream=True, timeout=(15, 30), headers=headers)
                if resp.status_code == 416:
                    # Range not satisfiable, start over
                    log.warning("Resume failed, starting fresh")
                    os.remove(tmp)
                    existing_size = 0
                    resp = requests.get(url, stream=True, timeout=(15, 30))
                resp.raise_for_status()

                total = int(resp.headers.get("content-length", 0)) + existing_size
                downloaded = existing_size

                mode = "ab" if existing_size > 0 else "wb"
                with open(tmp, mode) as f:
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

                if os.path.getsize(tmp) == 0:
                    os.remove(tmp)
                    raise RuntimeError(f"Downloaded file is empty: {variant}")

                # Verify checksum before renaming
                if expected_checksum and not _verify_checksum(tmp, expected_checksum):
                    os.remove(tmp)
                    raise RuntimeError(f"Checksum verification failed for {variant}")

                os.rename(tmp, dest)
                log.info("Model saved and verified: %s", dest)
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
