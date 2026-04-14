"""
Auto-Updater — check GitHub releases and download updates.
"""

from __future__ import annotations

import os
import sys
from typing import Callable, Optional

import requests

from utils.logger import log

GITHUB_REPO = "AnsCreator/Anz-Creator"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
VERSION_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "version.txt",
)


def get_current_version() -> str:
    """Read current version from version.txt or return default."""
    if os.path.isfile(VERSION_FILE):
        try:
            with open(VERSION_FILE, "r") as f:
                return f.read().strip()
        except Exception:
            pass
    return "v0.0.0.0"


def _parse_version(tag: str) -> tuple[int, ...]:
    """Parse 'v1.0.0.1' into (1, 0, 0, 1)."""
    clean = tag.lstrip("v").strip()
    parts = []
    for p in clean.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    # Pad to 4 parts
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts)


def check_for_update() -> Optional[dict]:
    """
    Check GitHub for a newer release.
    Returns dict with {tag, url, size, body} if update available, else None.
    """
    current = get_current_version()
    log.info("Current version: %s", current)

    try:
        resp = requests.get(GITHUB_API, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        latest_tag = data.get("tag_name", "")
        body = data.get("body", "")

        if not latest_tag:
            return None

        # Compare versions
        current_v = _parse_version(current)
        latest_v = _parse_version(latest_tag)

        if latest_v <= current_v:
            log.info("Already up to date: %s", current)
            return None

        # Find Windows zip asset
        download_url = ""
        size = 0
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if "Windows" in name and name.endswith(".zip"):
                download_url = asset.get("browser_download_url", "")
                size = asset.get("size", 0)
                break

        if not download_url:
            log.warning("No Windows asset found in release %s", latest_tag)
            return None

        log.info("Update available: %s → %s", current, latest_tag)
        return {
            "tag": latest_tag,
            "url": download_url,
            "size": size,
            "body": body,
        }

    except Exception as exc:
        log.warning("Update check failed: %s", exc)
        return None


def download_update(
    url: str,
    progress_callback: Callable[[int, str], None] = None,
    cancel_flag: Callable[[], bool] = None,
) -> str:
    """
    Download update zip to temp folder.
    Returns path to downloaded zip.
    """
    update_dir = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        "Anz-Creator", "updates",
    )
    os.makedirs(update_dir, exist_ok=True)
    dest = os.path.join(update_dir, "update.zip")

    log.info("Downloading update from %s", url)
    if progress_callback:
        progress_callback(0, "Downloading update…")

    try:
        resp = requests.get(url, stream=True, timeout=120, allow_redirects=True)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0

        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=256 * 1024):
                if cancel_flag and cancel_flag():
                    log.info("Update download cancelled.")
                    return ""
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0 and progress_callback:
                    pct = int(downloaded / total * 100)
                    progress_callback(
                        pct,
                        f"Downloading… {downloaded // 1048576}/{total // 1048576} MB",
                    )

        if progress_callback:
            progress_callback(100, "Download complete.")
        log.info("Update downloaded to: %s", dest)
        return dest

    except Exception as exc:
        log.error("Update download failed: %s", exc)
        if os.path.exists(dest):
            os.remove(dest)
        raise


def apply_update(zip_path: str) -> str:
    """
    Create a batch script that will:
    1. Wait for the app to close
    2. Extract update over current installation
    3. Restart the app
    Returns path to the batch script.
    """
    if not os.path.isfile(zip_path):
        raise FileNotFoundError(f"Update zip not found: {zip_path}")

    # Determine app directory
    if getattr(sys, "frozen", False):
        # PyInstaller bundle
        app_dir = os.path.dirname(sys.executable)
        app_exe = sys.executable
    else:
        # Running from source
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_exe = f'"{sys.executable}" "{os.path.join(app_dir, "main.py")}"'

    # Create updater batch script
    update_dir = os.path.dirname(zip_path)
    batch_path = os.path.join(update_dir, "update.bat")

    batch_content = '@echo off\r\n'
    batch_content += 'echo Anz-Creator Updater\r\n'
    batch_content += 'echo Waiting for application to close...\r\n'
    batch_content += 'timeout /t 5 /nobreak > nul\r\n'
    batch_content += 'echo.\r\n'
    batch_content += 'echo Extracting update...\r\n'
    batch_content += (
        'powershell -Command "'
        "Expand-Archive -Path '"
        + zip_path.replace("'", "''")
        + "' -DestinationPath '"
        + app_dir.replace("'", "''")
        + "' -Force"
        + '"\r\n'
    )
    batch_content += 'echo.\r\n'
    batch_content += 'echo Cleaning up...\r\n'
    batch_content += 'del "' + zip_path + '" 2>nul\r\n'
    batch_content += 'echo.\r\n'
    batch_content += 'echo Starting Anz-Creator...\r\n'
    if getattr(sys, "frozen", False):
        batch_content += 'start "" "' + app_exe + '"\r\n'
    else:
        batch_content += (
            'start "" "'
            + sys.executable
            + '" "'
            + os.path.join(app_dir, "main.py")
            + '"\r\n'
        )
    batch_content += 'echo Update complete!\r\n'
    batch_content += 'del "%~f0" 2>nul\r\n'
    batch_content += 'exit\r\n'

    with open(batch_path, "w", encoding="utf-8") as f:
        f.write(batch_content)

    log.info("Update script created: %s", batch_path)
    return batch_path
