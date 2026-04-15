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
            with open(VERSION_FILE, "r", encoding="utf-8") as f:
                ver = f.read().strip()
                if ver:
                    return ver
        except Exception:
            pass
    return "v0.0.0.0"


def _parse_version(tag: str) -> tuple[int, ...]:
    """Parse 'v1.0.0.1' into (1, 0, 0, 1)."""
    clean = tag.lstrip("v").strip()
    if not clean:
        return (0, 0, 0, 0)
    parts = []
    for p in clean.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    # Pad to 4 parts
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def check_for_update() -> Optional[dict]:
    """
    Check GitHub for a newer release.
    Returns dict with {tag, url, size, body} if update available, else None.
    """
    current = get_current_version()
    log.info("Current version: %s", current)

    try:
        resp = requests.get(
            GITHUB_API, timeout=10,
            headers={"User-Agent": "Anz-Creator"},
        )
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

    except requests.exceptions.RequestException as exc:
        log.warning("Update check failed (network): %s", exc)
        return None
    except (ValueError, KeyError) as exc:
        log.warning("Update check failed (parse): %s", exc)
        return None


def download_update(
    url: str,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_flag: Optional[Callable[[], bool]] = None,
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
    tmp = dest + ".part"

    log.info("Downloading update from %s", url)
    if progress_callback:
        progress_callback(0, "Downloading update…")

    try:
        resp = requests.get(url, stream=True, timeout=120, allow_redirects=True)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0

        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=256 * 1024):
                if cancel_flag and cancel_flag():
                    log.info("Update download cancelled.")
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
                        f"Downloading… {downloaded // 1048576}/"
                        f"{total // 1048576} MB",
                    )

        # Move complete download to final path
        if os.path.exists(dest):
            os.remove(dest)
        os.rename(tmp, dest)

        if progress_callback:
            progress_callback(100, "Download complete.")
        log.info("Update downloaded to: %s", dest)
        return dest

    except Exception as exc:
        log.error("Update download failed: %s", exc)
        for path in (tmp, dest):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        raise


def _escape_batch_path(path: str) -> str:
    """Escape a path for safe use in a Windows batch script."""
    # Replace characters that could be interpreted by cmd.exe
    # The safest approach is to quote the path
    return path.replace("^", "^^").replace("&", "^&").replace("|", "^|")


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
        app_exe = sys.executable

    # Create updater batch script
    update_dir = os.path.dirname(zip_path)
    batch_path = os.path.join(update_dir, "update.bat")

    # Escape paths for PowerShell single-quoted strings
    ps_zip = zip_path.replace("'", "''")
    ps_app = app_dir.replace("'", "''")

    lines = [
        '@echo off',
        'echo Anz-Creator Updater',
        'echo Waiting for application to close...',
        'timeout /t 5 /nobreak > nul',
        'echo.',
        'echo Extracting update...',
        f"powershell -Command \"Expand-Archive -Path '{ps_zip}'"
        f" -DestinationPath '{ps_app}' -Force\"",
        'echo.',
        'echo Cleaning up...',
        f'del "{_escape_batch_path(zip_path)}" 2>nul',
        'echo.',
        'echo Starting Anz-Creator...',
    ]

    if getattr(sys, "frozen", False):
        lines.append(f'start "" "{_escape_batch_path(app_exe)}"')
    else:
        main_py = os.path.join(app_dir, "main.py")
        lines.append(
            f'start "" "{_escape_batch_path(app_exe)}"'
            f' "{_escape_batch_path(main_py)}"'
        )

    lines.extend([
        'echo Update complete!',
        'del "%~f0" 2>nul',
        'exit',
    ])

    batch_content = "\r\n".join(lines) + "\r\n"

    with open(batch_path, "w", encoding="utf-8") as f:
        f.write(batch_content)

    log.info("Update script created: %s", batch_path)
    return batch_path
