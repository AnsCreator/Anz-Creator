"""
FFmpeg wrapper — extract frames from video and rebuild video from frames.
"""

from __future__ import annotations

import os
import subprocess
from typing import Callable

from utils.logger import log


def _subprocess_flags():
    """Return (creationflags, startupinfo) to hide console on Windows."""
    cf = 0
    si = None
    if os.name == "nt":
        cf = subprocess.CREATE_NO_WINDOW
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
    return cf, si


def _find_ffmpeg() -> str:
    """Find ffmpeg, preferring app-local then PATH."""
    import shutil

    found = shutil.which("ffmpeg")
    if found:
        return found

    app_bin = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        "Anz-Creator", "bin",
    )
    for name in ("ffmpeg.exe", "ffmpeg"):
        p = os.path.join(app_bin, name)
        if os.path.isfile(p):
            return p

    return "ffmpeg"


def _find_ffprobe() -> str:
    """Find ffprobe, preferring app-local then PATH."""
    import shutil

    found = shutil.which("ffprobe")
    if found:
        return found

    app_bin = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        "Anz-Creator", "bin",
    )
    for name in ("ffprobe.exe", "ffprobe"):
        p = os.path.join(app_bin, name)
        if os.path.isfile(p):
            return p

    return "ffprobe"


class FFmpegWrapper:
    """Thin wrapper over ffmpeg CLI for frame-based video processing."""

    # ── Extract all frames ───────────────────────────────
    @staticmethod
    def extract_frames(
        video_path: str,
        output_dir: str,
        pattern: str = "frame_%06d.png",
        progress_callback: Callable[[int, str], None] = None,
        cancel_flag: Callable[[], bool] = None,
    ) -> str:
        """
        Extract all frames as PNG images.
        Returns output_dir path.
        """
        os.makedirs(output_dir, exist_ok=True)
        out_pattern = os.path.join(output_dir, pattern)

        ffmpeg = _find_ffmpeg()
        cf, si = _subprocess_flags()

        cmd = [
            ffmpeg,
            "-y", "-i", video_path,
            "-vsync", "0",
            out_pattern,
        ]

        log.info("Extracting frames: %s → %s", video_path, output_dir)
        if progress_callback:
            progress_callback(0, "Extracting frames…")

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                creationflags=cf, startupinfo=si,
            )
            for line in proc.stdout:
                if cancel_flag and cancel_flag():
                    proc.kill()
                    return output_dir
            proc.wait()

            if proc.returncode != 0:
                log.warning("FFmpeg extract exited with code %d", proc.returncode)

        except FileNotFoundError:
            log.error("FFmpeg not found: %s", ffmpeg)
            raise RuntimeError(
                "FFmpeg not found. Install with: choco install ffmpeg\n"
                "Or download from: https://ffmpeg.org/download.html"
            )

        count = len([f for f in os.listdir(output_dir) if f.endswith(".png")])
        log.info("Extracted %d frames to %s", count, output_dir)
        if progress_callback:
            progress_callback(100, f"Extracted {count} frames.")
        return output_dir

    # ── Rebuild video from frames ────────────────────────
    @staticmethod
    def rebuild_video(
        frames_dir: str,
        original_video: str,
        output_path: str,
        fps: float = 30.0,
        pattern: str = "frame_%06d.png",
        crf: int = 18,
        preset: str = "medium",
        progress_callback: Callable[[int, str], None] = None,
        cancel_flag: Callable[[], bool] = None,
    ) -> str:
        """
        Rebuild video from frames, copying audio from original.
        """
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        frames_pattern = os.path.join(frames_dir, pattern)

        ffmpeg = _find_ffmpeg()
        cf, si = _subprocess_flags()

        cmd = [
            ffmpeg, "-y",
            "-framerate", str(fps),
            "-i", frames_pattern,
            "-i", original_video,
            "-map", "0:v",
            "-map", "1:a?",       # audio if present
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", preset,
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        log.info("Rebuilding video → %s", output_path)
        if progress_callback:
            progress_callback(0, "Rebuilding video…")

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                creationflags=cf, startupinfo=si,
            )
            for line in proc.stdout:
                if cancel_flag and cancel_flag():
                    proc.kill()
                    return ""
            proc.wait()

            if proc.returncode != 0:
                log.warning("FFmpeg rebuild exited with code %d", proc.returncode)

        except FileNotFoundError:
            log.error("FFmpeg not found: %s", ffmpeg)
            raise RuntimeError("FFmpeg not found.")

        if progress_callback:
            progress_callback(100, "Video rebuilt.")
        log.info("Output video: %s", output_path)
        return output_path

    # ── Get video FPS ────────────────────────────────────
    @staticmethod
    def get_fps(video_path: str) -> float:
        ffprobe = _find_ffprobe()
        cf, si = _subprocess_flags()

        cmd = [
            ffprobe, "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "csv=p=0",
            video_path,
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10,
                creationflags=cf, startupinfo=si,
            )
            num, den = result.stdout.strip().split("/")
            return float(num) / float(den)
        except Exception:
            return 30.0
