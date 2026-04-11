"""
yt-dlp wrapper for URL-based video download.
Supports YouTube, TikTok, Instagram, and 1000+ platforms.
"""

from __future__ import annotations

import os
import json
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Optional

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


class Downloader:
    """Thin wrapper around yt-dlp CLI."""

    YT_DLP = "yt-dlp"

    # ── metadata ─────────────────────────────────────────
    @staticmethod
    def fetch_metadata(url: str) -> VideoMeta:
        """
        Fetch video metadata (no download) — title, duration, thumbnail, qualities.
        """
        log.info("Fetching metadata for: %s", url)
        cmd = [
            Downloader.YT_DLP,
            "--dump-json",
            "--no-download",
            "--no-playlist",
            url,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp metadata error: {result.stderr.strip()}")

        info = json.loads(result.stdout)
        meta = VideoMeta(
            url=url,
            title=info.get("title", "Unknown"),
            duration=info.get("duration", 0),
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
        os.makedirs(output_dir, exist_ok=True)
        output_template = os.path.join(output_dir, "%(title).80s.%(ext)s")

        height_map = {"4K": "2160", "1080p": "1080", "720p": "720", "480p": "480"}
        h = height_map.get(quality, "1080")

        cmd = [
            Downloader.YT_DLP,
            "-f", f"bestvideo[height<={h}]+bestaudio/best[height<={h}]",
            "--merge-output-format", "mp4",
            "-o", output_template,
            "--no-playlist",
            "--newline",            # one progress line per update
            url,
        ]

        log.info("Downloading: %s @ %s", url, quality)
        if progress_callback:
            progress_callback(0, "Starting download…")

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )

        output_path = ""
        for line in proc.stdout:
            if cancel_flag and cancel_flag():
                proc.kill()
                log.info("Download cancelled.")
                return ""

            line = line.strip()
            # Parse yt-dlp progress lines like "[download]  45.2% of ~100MiB …"
            if "[download]" in line and "%" in line:
                try:
                    pct_str = line.split("%")[0].split()[-1]
                    pct = int(float(pct_str))
                    if progress_callback:
                        progress_callback(pct, f"Downloading… {pct}%")
                except (ValueError, IndexError):
                    pass
            # Capture final merged path
            if "[Merger]" in line or "has already been downloaded" in line:
                pass
            if "Destination:" in line:
                output_path = line.split("Destination:")[-1].strip()

        proc.wait()

        # If yt-dlp doesn't print Destination, find the file
        if not output_path or not os.path.isfile(output_path):
            for f in os.listdir(output_dir):
                if f.endswith(".mp4"):
                    output_path = os.path.join(output_dir, f)
                    break

        if progress_callback:
            progress_callback(100, "Download complete.")
        log.info("Downloaded to: %s", output_path)
        return output_path
