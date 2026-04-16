"""
Auto-Updater — check GitHub releases and download updates.
Supports Windows, macOS, and Linux.
"""

from __future__ import annotations

import os
import sys
import tempfile
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

        current_v = _parse_version(current)
        latest_v = _parse_version(latest_tag)

        if latest_v <= current_v:
            log.info("Already up to date: %s", current)
            return None

        # Find platform-specific asset
        download_url = ""
        size = 0
        platform_keywords = _get_platform_asset_keywords()
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if any(kw in name for kw in platform_keywords) and name.endswith(".zip"):
                download_url = asset.get("browser_download_url", "")
                size = asset.get("size", 0)
                break

        if not download_url:
            log.warning("No asset found for this platform in release %s", latest_tag)
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


def _get_platform_asset_keywords() -> list[str]:
    """Return keywords to identify the correct asset for current OS."""
    if sys.platform == "win32":
        return ["Windows", "win64", "win32"]
    elif sys.platform == "darwin":
        return ["macOS", "darwin", "mac"]
    else:
        return ["Linux", "linux"]


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

    # Resume support
    headers = {}
    existing_size = 0
    if os.path.exists(tmp):
        existing_size = os.path.getsize(tmp)
        if existing_size > 0:
            headers["Range"] = f"bytes={existing_size}-"
            log.info("Resuming update download from byte %d", existing_size)

    try:
        resp = requests.get(url, stream=True, timeout=120, allow_redirects=True, headers=headers)
        if resp.status_code == 416:
            os.remove(tmp)
            existing_size = 0
            resp = requests.get(url, stream=True, timeout=120, allow_redirects=True)
        resp.raise_for_status()

        total = int(resp.headers.get("content-length", 0)) + existing_size
        downloaded = existing_size

        mode = "ab" if existing_size > 0 else "wb"
        with open(tmp, mode) as f:
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


def apply_update(zip_path: str) -> str:
    """
    Create a platform-specific update script and return its path.
    """
    if not os.path.isfile(zip_path):
        raise FileNotFoundError(f"Update zip not found: {zip_path}")

    if sys.platform == "win32":
        return _create_windows_updater(zip_path)
    elif sys.platform == "darwin":
        return _create_macos_updater(zip_path)
    else:
        return _create_linux_updater(zip_path)


def _escape_batch_path(path: str) -> str:
    """Escape a path for safe use in a Windows batch script."""
    return path.replace("^", "^^").replace("&", "^&").replace("|", "^|")


def _create_windows_updater(zip_path: str) -> str:
    """Create Windows batch script for updating."""
    if getattr(sys, "frozen", False):
        app_dir = os.path.dirname(sys.executable)
        app_exe = sys.executable
        app_pid = os.getpid()
    else:
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_exe = sys.executable
        app_pid = os.getpid()

    update_dir = os.path.dirname(zip_path)
    batch_path = os.path.join(update_dir, "update.bat")

    ps_zip = zip_path.replace("'", "''")
    ps_app = app_dir.replace("'", "''")

    lines = [
        '@echo off',
        'chcp 65001 >nul 2>&1',
        'title Anz-Creator Updater',
        'echo ========================================',
        'echo   Anz-Creator Auto-Updater',
        'echo ========================================',
        'echo.',
        f'echo Stopping Anz-Creator (PID {app_pid})...',
        f'taskkill /F /PID {app_pid} >nul 2>&1',
        'echo Waiting for process to exit...',
        'set /a TRIES=0',
        ':WAIT_LOOP',
        f'tasklist /FI "PID eq {app_pid}" 2>nul | find "{app_pid}" >nul 2>&1',
        'if errorlevel 1 goto PROCESS_DEAD',
        'set /a TRIES+=1',
        'if %TRIES% GEQ 30 (',
        '    echo ERROR: Process did not exit after 30 seconds.',
        '    pause',
        '    exit /b 1',
        ')',
        'timeout /t 1 /nobreak >nul',
        'goto WAIT_LOOP',
        ':PROCESS_DEAD',
        'echo Process terminated.',
        'timeout /t 3 /nobreak >nul',
        'echo Cleaning up temp files...',
        'for /d %%D in ("%LOCALAPPDATA%\\Temp\\_MEI*") do rd /s /q "%%D" >nul 2>&1',
        'echo Extracting update...',
        "powershell -NoProfile -Command \""
        f"try {{ Expand-Archive -Path '{ps_zip}'"
        f" -DestinationPath '{ps_app}' -Force;"
        " Write-Host 'Extraction successful.' }}"
        " catch { Write-Host ('Extraction failed: ' + $_.Exception.Message);"
        " Read-Host 'Press Enter to exit'; exit 1 }\"",
        'if errorlevel 1 (',
        '    echo Update extraction failed!',
        '    pause',
        '    exit /b 1',
        ')',
        'echo Cleaning up...',
        f'del "{_escape_batch_path(zip_path)}" >nul 2>&1',
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
        'echo.',
        'echo ========================================',
        'echo   Update complete!',
        'echo ========================================',
        'timeout /t 2 /nobreak >nul',
        'del "%~f0" >nul 2>&1',
        'exit',
    ])

    batch_content = "\r\n".join(lines) + "\r\n"
    with open(batch_path, "w", encoding="utf-8") as f:
        f.write(batch_content)

    log.info("Windows update script created: %s", batch_path)
    return batch_path


def _create_macos_updater(zip_path: str) -> str:
    """Create macOS shell script for updating."""
    if getattr(sys, "frozen", False):
        app_dir = os.path.dirname(sys.executable)
        app_exe = sys.executable
    else:
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_exe = sys.executable

    update_dir = os.path.dirname(zip_path)
    script_path = os.path.join(update_dir, "update.sh")
    pid = os.getpid()

    script_content = f"""#!/bin/bash
echo "Stopping Anz-Creator (PID {pid})..."
kill -9 {pid} 2>/dev/null
sleep 3

echo "Extracting update..."
unzip -o "{zip_path}" -d "{app_dir}"

rm -f "{zip_path}"

echo "Restarting Anz-Creator..."
if [[ "{app_exe}" == *.app/Contents/MacOS/* ]]; then
    open "$(dirname "$(dirname "{app_exe}")")"
else
    "{app_exe}" "$(dirname "{app_dir}")/main.py" &
fi

rm -- "$0"
"""
    with open(script_path, "w") as f:
        f.write(script_content)
    os.chmod(script_path, 0o755)
    log.info("macOS update script created: %s", script_path)
    return script_path


def _create_linux_updater(zip_path: str) -> str:
    """Create Linux shell script for updating."""
    if getattr(sys, "frozen", False):
        app_dir = os.path.dirname(sys.executable)
        app_exe = sys.executable
    else:
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_exe = sys.executable

    update_dir = os.path.dirname(zip_path)
    script_path = os.path.join(update_dir, "update.sh")
    pid = os.getpid()

    script_content = f"""#!/bin/bash
echo "Stopping Anz-Creator (PID {pid})..."
kill -9 {pid} 2>/dev/null
sleep 3

echo "Extracting update..."
unzip -o "{zip_path}" -d "{app_dir}"

rm -f "{zip_path}"

echo "Restarting Anz-Creator..."
"{app_exe}" "{app_dir}/main.py" &

rm -- "$0"
"""
    with open(script_path, "w") as f:
        f.write(script_content)
    os.chmod(script_path, 0o755)
    log.info("Linux update script created: %s", script_path)
    return script_path
