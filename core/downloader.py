"""
yt-dlp wrapper for URL-based video download.
Supports YouTube, TikTok, Instagram, and 1000+ platforms.
Auto-installs yt-dlp if not found.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Callable

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


def _normalize_url(url: str) -> str:
    """Ensure URL has https:// prefix."""
    url = url.strip().strip("\"'")
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _subprocess_flags() -> int:
    """Return CREATE_NO_WINDOW on Windows to hide console popups."""
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW
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
    4. Auto-download standalone .exe from GitHub releases
    """
    # App-local location (auto-downloaded binary lives here)
    app_bin_dir = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        "Anz-Creator", "bin",
    )
    app_ytdlp = os.path.join(app_bin_dir, "yt-dlp.exe" if os.name == "nt" else "yt-dlp")
    if os.path.isfile(app_ytdlp):
        log.info("yt-dlp found in app folder: %s", app_ytdlp)
        return app_ytdlp

    # 1. Check PATH
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

    # Check user-level Scripts (pip install --user)
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

    # 3. Auto-download standalone exe from GitHub releases
    log.warning("yt-dlp not found — downloading standalone exe…")
    try:
        import requests

        if os.name == "nt":
            url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
        else:
            url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux"

        os.makedirs(app_bin_dir, exist_ok=True)
        tmp_path = app_ytdlp + ".part"

        log.info("Downloading yt-dlp from %s …", url)
        resp = requests.get(url, stream=True, timeout=60, allow_redirects=True)
        resp.raise_for_status()

        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=256 * 1024):
                f.write(chunk)

        os.rename(tmp_path, app_ytdlp)

        # Make executable on Linux/macOS
        if os.name != "nt":
            os.chmod(app_ytdlp, 0o755)

        log.info("yt-dlp downloaded to: %s", app_ytdlp)
        return app_ytdlp

    except Exception as exc:
        log.error("Failed to download yt-dlp: %s", exc)
        # Clean up partial file
        if os.path.exists(app_ytdlp + ".part"):
            os.remove(app_ytdlp + ".part")

    raise FileNotFoundError(
        "yt-dlp not found and auto-download failed.\n"
        "Please install manually:\n"
        "  pip install yt-dlp\n"
        "Or download from: https://github.com/yt-dlp/yt-dlp/releases"
    )


class Downloader:
    """Thin wrapper around yt-dlp CLI."""

    _ytdlp_path: str = None

    @classmethod
    def _get_ytdlp(cls) -> str:
        if cls._ytdlp_path is None:
            cls._ytdlp_path = _find_ytdlp()
        return cls._ytdlp_path

    # ── metadata ─────────────────────────────────────────
    @staticmethod
    def fetch_metadata(url: str) -> VideoMeta:
        """
        Fetch video metadata (no download) — title, duration, thumbnail, qualities.
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
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
            creationflags=_subprocess_flags(), startupinfo=_startupinfo(),
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "is not recognized" in stderr or "not found" in stderr:
                raise RuntimeError(
                    "yt-dlp not found. Install with: pip install yt-dlp"
                )
            raise RuntimeError(f"yt-dlp error: {stderr}")

        info = json.loads(result.stdout)
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
            quality_map[h] for h in sorted(heights, reverse=True) if h in quality_map
        ]
        if not meta.available_qualities:
            meta.available_qualities = ["best"]

        log.info("Metadata: %s — %ds — %s", meta.title, meta.duration, meta.available_qualities)
        return meta

    # ── download ─────────────────────────────────────────
    @staticmethod
    def download(
        url: str,
        output_dir: str,
        quality: str = "1080p",
        progress_callback: Callable[[int, str], None] = None,
        cancel_flag: Callable[[], bool] = None,
    ) -> str:
        """
        Download video to output_dir. Returns path to downloaded file.
        """
        url = _normalize_url(url)
        ytdlp = Downloader._get_ytdlp()

        os.makedirs(output_dir, exist_ok=True)
        output_template = os.path.join(output_dir, "%(title).80s.%(ext)s")

        height_map = {"4K": "2160", "1080p": "1080", "720p": "720", "480p": "480"}
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
        )

        output_path = ""
        for line in proc.stdout:
            if cancel_flag and cancel_flag():
                proc.kill()
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
                    output_path = line.split("[download]")[-1].split("has already")[0].strip()
                except Exception:
                    pass

        proc.wait()

        # Fallback: find most recent .mp4 in output dir
        if not output_path or not os.path.isfile(output_path):
            mp4_files = [f for f in os.listdir(output_dir) if f.endswith(".mp4")]
            if mp4_files:
                mp4_files.sort(
                    key=lambda f: os.path.getmtime(os.path.join(output_dir, f)),
                    reverse=True,
                )
                output_path = os.path.join(output_dir, mp4_files[0])

        if not output_path or not os.path.isfile(output_path):
            raise RuntimeError("Download completed but output file not found.")

        if progress_callback:
            progress_callback(100, "Download complete.")
        log.info("Downloaded to: %s", output_path)
        return output_path
