"""Model Manager — auto-download, verify, and load AI models."""

from __future__ import annotations

import hashlib
import os
import sys
import threading
from pathlib import Path
from typing import Callable, Optional, List

import requests
import yaml

from utils.logger import log

_APPDATA = os.environ.get("APPDATA", os.path.expanduser("~"))
MODELS_ROOT = os.path.join(_APPDATA, "Anz-Creator", "models")


def _get_bundled_models_path() -> str:
    """Return path to bundled models (if PyInstaller frozen) or dev models dir."""
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        return os.path.join(mei, "models")
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"
    )


def _compute_sha256(filepath: str) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _verify_checksum(filepath: str, expected_sha256: str) -> bool:
    if not expected_sha256:
        return True
    actual = _compute_sha256(filepath)
    if actual != expected_sha256:
        log.error("Checksum mismatch for %s", filepath)
        return False
    return True


def _download_file(
    url: str,
    dest_path: str,
    description: str = "",
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_flag: Optional[Callable[[], bool]] = None,
) -> str:
    """Download a single file to dest_path with progress reporting."""
    Path(os.path.dirname(dest_path)).mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path + ".part"

    # Support resume
    headers = {}
    resume_pos = 0
    if os.path.isfile(tmp_path):
        resume_pos = os.path.getsize(tmp_path)
        headers["Range"] = f"bytes={resume_pos}-"

    try:
        with requests.get(url, stream=True, headers=headers, timeout=30) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("Content-Length", 0)) + resume_pos
            mode = "ab" if resume_pos else "wb"
            downloaded = resume_pos

            with open(tmp_path, mode) as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if cancel_flag and cancel_flag():
                        log.info("Download cancelled: %s", description or dest_path)
                        raise RuntimeError("Cancelled")
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size > 0:
                            pct = int((downloaded / total_size) * 100)
                            label = description or os.path.basename(dest_path)
                            progress_callback(pct, f"{label}: {pct}%")

        # Atomic rename
        if os.path.exists(dest_path):
            os.remove(dest_path)
        os.rename(tmp_path, dest_path)
        return dest_path
    except Exception:
        # Keep .part file for resume on next attempt
        raise


class ModelManager:
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
        ext = ".pt" if family != "propainter" else ".pth"
        bundled_path = os.path.join(
            _get_bundled_models_path(), family, f"{variant}{ext}"
        )
        if os.path.isfile(bundled_path):
            return bundled_path
        return os.path.join(MODELS_ROOT, family, f"{variant}{ext}")

    def _extra_file_path(self, family: str, filename: str) -> str:
        """Path for an auxiliary file that lives in the same family folder."""
        return os.path.join(MODELS_ROOT, family, filename)

    def is_downloaded(self, family: str, variant: str) -> bool:
        """Check main model AND all extra files are present."""
        main = self.model_path(family, variant)
        if not (os.path.isfile(main) and os.path.getsize(main) > 0):
            return False
        for extra in self._get_extra_files(family, variant):
            path = self._extra_file_path(family, extra["name"])
            if not (os.path.isfile(path) and os.path.getsize(path) > 0):
                return False
        return True

    def get_url(self, family: str, variant: str) -> Optional[str]:
        try:
            return self._cfg["models"][family]["options"][variant].get("url")
        except (KeyError, TypeError):
            return None

    def _get_extra_files(self, family: str, variant: str) -> List[dict]:
        """Return list of extra files (e.g. ProPainter auxiliary weights)."""
        try:
            extras = self._cfg["models"][family]["options"][variant].get(
                "extra_files", []
            )
            return extras if isinstance(extras, list) else []
        except (KeyError, TypeError):
            return []

    def get_checksum(self, family: str, variant: str) -> Optional[str]:
        try:
            return self._cfg["models"][family]["options"][variant].get("sha256")
        except (KeyError, TypeError):
            return None

    def get_size_mb(self, family: str, variant: str) -> int:
        try:
            base = self._cfg["models"][family]["options"][variant].get("size_mb", 0)
            extras = self._get_extra_files(family, variant)
            return base + sum(e.get("size_mb", 0) for e in extras)
        except (KeyError, TypeError):
            return 0

    def list_variants(self, family: str) -> list[dict]:
        try:
            opts = self._cfg.get("models", {}).get(family, {}).get("options", {})
        except (AttributeError, TypeError):
            return []
        out = []
        for name, info in opts.items():
            if not isinstance(info, dict):
                continue
            out.append(
                {
                    "name": name,
                    "description": info.get("description", ""),
                    "size_mb": self.get_size_mb(family, name),
                    "vram_gb": info.get("vram_gb", 0),
                    "downloaded": self.is_downloaded(family, name),
                }
            )
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
        """Download a model (and any extra files). Returns main model path."""
        with self._download_lock:
            main_dest = self.model_path(family, variant)
            url = self.get_url(family, variant)
            if not url:
                raise ValueError(f"No download URL for {family}/{variant}")

            size_mb = self.get_size_mb(family, variant)
            log.info(
                "Downloading %s/%s (≈%dMB) from %s", family, variant, size_mb, url
            )

            extras = self._get_extra_files(family, variant)
            total_files = 1 + len(extras)

            # Main file
            if not (os.path.isfile(main_dest) and os.path.getsize(main_dest) > 0):
                def main_progress(pct: int, msg: str):
                    if progress_callback:
                        # Scale to overall progress
                        overall = pct // total_files
                        progress_callback(overall, f"[1/{total_files}] {msg}")

                _download_file(
                    url,
                    main_dest,
                    description=f"{family}/{variant}",
                    progress_callback=main_progress,
                    cancel_flag=cancel_flag,
                )

            # Extra files
            for idx, extra in enumerate(extras, start=2):
                extra_url = extra.get("url")
                extra_name = extra.get("name")
                if not extra_url or not extra_name:
                    continue
                extra_dest = self._extra_file_path(family, extra_name)
                if os.path.isfile(extra_dest) and os.path.getsize(extra_dest) > 0:
                    log.info("Skipping existing extra file: %s", extra_name)
                    continue

                def extra_progress(pct: int, msg: str, idx=idx):
                    if progress_callback:
                        base_pct = ((idx - 1) * 100) // total_files
                        overall = base_pct + (pct // total_files)
                        progress_callback(overall, f"[{idx}/{total_files}] {msg}")

                _download_file(
                    extra_url,
                    extra_dest,
                    description=extra_name,
                    progress_callback=extra_progress,
                    cancel_flag=cancel_flag,
                )

            # Verify checksum if provided
            expected_sha = self.get_checksum(family, variant)
            if expected_sha and not _verify_checksum(main_dest, expected_sha):
                os.remove(main_dest)
                raise RuntimeError(
                    f"Checksum verification failed for {family}/{variant}"
                )

            log.info("Model saved and verified: %s", main_dest)
            if progress_callback:
                progress_callback(100, f"{variant} ready.")
            return main_dest

    def ensure_models(
        self,
        families: List[str],
        settings,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_flag: Optional[Callable[[], bool]] = None,
    ) -> dict:
        """Ensure all needed models are downloaded. Returns dict family→path."""
        out = {}
        for family in families:
            variant = settings.get(f"models.{family}", self.default_variant(family))
            if not variant:
                continue
            path = self.download(
                family, variant, progress_callback=progress_callback, cancel_flag=cancel_flag
            )
            out[family] = path
        return out
