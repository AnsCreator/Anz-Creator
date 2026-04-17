"""
yt-dlp wrapper for URL-based video download.
Supports YouTube, TikTok, Instagram, and 1000+ platforms.
Auto-downloads yt-dlp standalone binary if not found.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import urlparse

import requests

from utils.logger import log


@dataclass
class VideoMeta:
    """Metadata fetched from a URL before downloading."""
    url: str = ""
    title: str = ""
    duration: int = 0           # seconds
    thumbnail: str = ""
    platform: str = ""
    available_qualities: list[str] = field(default_factory=list)
    formats: list[dict] = field(default_factory=list)


# Process-wide lock to prevent two threads in the same process from
# trying to download yt-dlp concurrently.
_YTDLP_DOWNLOAD_LOCK = threading.Lock()


def _normalize_url(url: str) -> str:
    """Ensure URL has https:// prefix and validate scheme."""
    url = url.strip().strip("\"'")
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")
    return url


def _subprocess_flags() -> int:
    """Return CREATE_NO_WINDOW on Windows to hide console popups."""
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def _startupinfo():
    """Return STARTUPINFO that hides the window on Windows."""
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        return si
    return None


def _find_ytdlp() -> str:
    """
    Find yt-dlp executable. Search order:
    1. Bundled in app data folder (previously auto-downloaded)
    2. System PATH
    3. Python Scripts folder (pip install location on Windows)
    4. Auto-download standalone binary from GitHub releases
    """
    app_bin_dir = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        "Anz-Creator", "bin",
    )
    exe_name = "yt-dlp.exe" if os.name == "nt" else "yt-dlp"
    app_ytdlp = os.path.join(app_bin_dir, exe_name)

    # 0. Check app-local location
    if os.path.isfile(app_ytdlp) and os.path.getsize(app_ytdlp) > 0:
        log.info("yt-dlp found in app folder: %s", app_ytdlp)
        return app_ytdlp

    # 1. Check system PATH
    found = shutil.which("yt-dlp")
    if found:
        log.info("yt-dlp found in PATH: %s", found)
        return found

    # 2. Check Python Scripts folder
    scripts_dir = os.path.join(os.path.dirname(sys.executable), "Scripts")
    for name in ("yt-dlp.exe", "yt-dlp"):
        p = os.path.join(scripts_dir, name)
        if os.path.isfile(p):
            log.info("yt-dlp found in Scripts: %s", p)
            return p

    # Check user-level Scripts (pip install --user) on Windows
    if os.name == "nt":
        user_base = os.environ.get("APPDATA", "")
        user_scripts_candidates = [
            os.path.join(user_base, "Python", "Scripts"),
            os.path.join(
                os.path.expanduser("~"),
                "AppData", "Roaming", "Python", "Scripts",
            ),
        ]
        for d in user_scripts_candidates:
            p = os.path.join(d, "yt-dlp.exe")
            if os.path.isfile(p):
                log.info("yt-dlp found: %s", p)
                return p

    # 3. Auto-download standalone binary from GitHub
    with _YTDLP_DOWNLOAD_LOCK:
        # Re-check after acquiring lock
        if os.path.isfile(app_ytdlp) and os.path.getsize(app_ytdlp) > 0:
            return app_ytdlp

        log.warning("yt-dlp not found — downloading standalone binary…")
        os.makedirs(app_bin_dir, exist_ok=True)

        if os.name == "nt":
            url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
        elif sys.platform == "darwin":
            url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos"
        else:
            url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux"

        # Download to a unique temp file, then atomic-rename into place
        tmp_fd, tmp_path = tempfile.mkstemp(
            prefix="yt-dlp-", suffix=".part", dir=app_bin_dir,
        )
        os.close(tmp_fd)

        try:
            log.info("Downloading yt-dlp from %s …", url)
            resp = requests.get(
                url, stream=True, timeout=60, allow_redirects=True,
                headers={"User-Agent": "Anz-Creator"},
            )
            resp.raise_for_status()

            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=256 * 1024):
                    if chunk:
                        f.write(chunk)

            if os.path.getsize(tmp_path) == 0:
                raise RuntimeError("Downloaded yt-dlp file is empty")

            # Atomic replace on both Windows and POSIX
            os.replace(tmp_path, app_ytdlp)

            if os.name != "nt":
                os.chmod(app_ytdlp, 0o755)

            log.info("yt-dlp downloaded to: %s", app_ytdlp)
            return app_ytdlp

        except Exception as exc:
            log.error("Failed to download yt-dlp: %s", exc)
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            raise


class Downloader:
    """Thin wrapper around yt-dlp CLI."""

    _ytdlp_path: Optional[str] = None
    _ytdlp_lock = threading.Lock()

    @classmethod
    def _get_ytdlp(cls) -> str:
        with cls._ytdlp_lock:
            if cls._ytdlp_path is None:
                cls._ytdlp_path = _find_ytdlp()
            return cls._ytdlp_path

    # ── metadata ─────────────────────────────────────────
    @staticmethod
    def fetch_metadata(url: str) -> VideoMeta:
        """
        Fetch video metadata (no download) — title, duration, thumbnail,
        qualities.
        """
        url = _normalize_url(url)
        if not url:
            raise ValueError("URL is empty.")

        ytdlp = Downloader._get_ytdlp()
        log.info("Fetching metadata for: %s", url)

        cmd = [
            ytdlp,
            "--dump-json",
            "--no-download",
            "--no-playlist",
            url,
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60,
                creationflags=_subprocess_flags(), startupinfo=_startupinfo(),
                encoding="utf-8", errors="replace",
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("yt-dlp timed out fetching metadata. Try again.")
        except FileNotFoundError:
            raise RuntimeError(
                "yt-dlp not found. Install with: pip install yt-dlp"
            )

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            if "is not recognized" in stderr or "not found" in stderr:
                raise RuntimeError(
                    "yt-dlp not found. Install with: pip install yt-dlp"
                )
            raise RuntimeError(f"yt-dlp error: {stderr[:500]}")

        stdout = (result.stdout or "").strip()
        if not stdout:
            raise RuntimeError("yt-dlp returned empty output.")

        try:
            info = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Failed to parse yt-dlp output: {exc}")

        meta = VideoMeta(
            url=url,
            title=info.get("title", "Unknown"),
            duration=info.get("duration") or 0,
            thumbnail=info.get("thumbnail", ""),
            platform=info.get("extractor", "unknown"),
        )

        # Collect available heights
        heights = set()
        for fmt in info.get("formats", []):
            h = fmt.get("height")
            if h and fmt.get("vcodec", "none") != "none":
                heights.add(h)

        quality_map = {2160: "4K", 1080: "1080p", 720: "720p", 480: "480p"}
        meta.available_qualities = [
            quality_map[h]
            for h in sorted(heights, reverse=True)
            if h in quality_map
        ]
        if not meta.available_qualities:
            meta.available_qualities = ["best"]

        log.info(
            "Metadata: %s — %ds — %s",
            meta.title, meta.duration, meta.available_qualities,
        )
        return meta

    # ── download ─────────────────────────────────────────
    @staticmethod
    def download(
        url: str,
        output_dir: str,
        quality: str = "1080p",
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_flag: Optional[Callable[[], bool]] = None,
    ) -> str:
        """
        Download video to output_dir. Returns path to downloaded file.
        """
        url = _normalize_url(url)
        ytdlp = Downloader._get_ytdlp()

        os.makedirs(output_dir, exist_ok=True)
        output_template = os.path.join(output_dir, "%(title).80s.%(ext)s")

        height_map = {
            "4K": "2160", "1080p": "1080", "720p": "720", "480p": "480",
        }
        h = height_map.get(quality, "1080")

        cmd = [
            ytdlp,
            "-f", f"bestvideo[height<={h}]+bestaudio/best[height<={h}]",
            "--merge-output-format", "mp4",
            "-o", output_template,
            "--no-playlist",
            "--newline",
            url,
        ]

        log.info("Downloading: %s @ %s", url, quality)
        if progress_callback:
            progress_callback(0, "Starting download…")

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
            creationflags=_subprocess_flags(), startupinfo=_startupinfo(),
            encoding="utf-8", errors="replace",
        )

        output_path = ""
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                if cancel_flag and cancel_flag():
                    proc.kill()
                    proc.wait(timeout=5)
                    log.info("Download cancelled.")
                    return ""

                line = line.strip()
                # Parse yt-dlp progress lines: "[download]  45.2% of ~100MiB …"
                if "[download]" in line and "%" in line:
                    try:
                        pct_str = line.split("%")[0].split()[-1]
                        pct = min(int(float(pct_str)), 100)
                        if progress_callback:
                            progress_callback(pct, f"Downloading… {pct}%")
                    except (ValueError, IndexError):
                        pass
                if "Destination:" in line:
                    output_path = line.split("Destination:")[-1].strip()
                if "has already been downloaded" in line:
                    try:
                        output_path = (
                            line.split("[download]")[-1]
                            .split("has already")[0]
                            .strip()
                        )
                    except Exception:
                        pass
                # yt-dlp may also report merge destination
                if "[Merger] Merging formats into" in line:
                    try:
                        merge_path = line.split("into")[-1].strip().strip('"')
                        if merge_path:
                            output_path = merge_path
                    except Exception:
                        pass
        finally:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

        # Fallback: find most recent .mp4 in output dir
        if not output_path or not os.path.isfile(output_path):
            try:
                mp4_files = [
                    f for f in os.listdir(output_dir)
                    if f.endswith(".mp4")
                ]
                if mp4_files:
                    mp4_files.sort(
                        key=lambda f: os.path.getmtime(
                            os.path.join(output_dir, f)
                        ),
                        reverse=True,
                    )
                    output_path = os.path.join(output_dir, mp4_files[0])
            except OSError as exc:
                log.warning("Error listing output dir: %s", exc)

        if not output_path or not os.path.isfile(output_path):
            raise RuntimeError("Download completed but output file not found.")

        if progress_callback:
            progress_callback(100, "Download complete.")
        log.info("Downloaded to: %s", output_path)
        return output_path
