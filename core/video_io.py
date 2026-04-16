"""
Video read/write utilities (metadata, frame access).
Uses OpenCV with ffprobe fallback for robust metadata reading.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Generator

import cv2
import numpy as np

from utils.logger import log


@dataclass
class VideoInfo:
    path: str
    width: int
    height: int
    fps: float
    frame_count: int
    duration: float  # seconds
    codec: str


def _subprocess_silent():
    """Return (creationflags, startupinfo) to hide console on Windows."""
    cf = 0
    si = None
    if os.name == "nt":
        cf = subprocess.CREATE_NO_WINDOW
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
    return cf, si


def _app_bin_dir() -> str:
    return os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        "Anz-Creator", "bin",
    )


def is_ffmpeg_installed() -> bool:
    """Check if FFmpeg is available in system PATH or local app bin."""
    if shutil.which("ffmpeg"):
        return True
    app_bin = _app_bin_dir()
    p = os.path.join(app_bin, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    return os.path.isfile(p)


def download_ffmpeg(progress_callback=None, cancel_flag=None) -> str:
    """Trigger manual download of FFmpeg."""
    app_bin = _app_bin_dir()
    return _auto_download_ffmpeg(app_bin, progress_callback, cancel_flag)


def _find_ffprobe() -> str:
    """Find ffprobe executable."""
    found = shutil.which("ffprobe")
    if found:
        return found
    app_bin = _app_bin_dir()
    for name in ("ffprobe.exe", "ffprobe"):
        p = os.path.join(app_bin, name)
        if os.path.isfile(p):
            return p
    return "ffprobe"


def _find_ffmpeg() -> str:
    """Find ffmpeg executable."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    app_bin = _app_bin_dir()
    for name in ("ffmpeg.exe", "ffmpeg"):
        p = os.path.join(app_bin, name)
        if os.path.isfile(p):
            return p
    return "ffmpeg"


def _auto_download_ffmpeg(app_bin: str, progress_callback=None, cancel_flag=None) -> str:
    """
    Download FFmpeg for Windows from GitHub or gyan.dev fallback.
    Downloads to disk, extracts ffmpeg.exe + ffprobe.exe to app_bin.
    """
    import zipfile

    import requests

    SOURCES = [
        (
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/"
            "latest/ffmpeg-master-latest-win64-gpl.zip",
            "GitHub BtbN",
        ),
        (
            "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
            "Gyan.dev",
        ),
    ]

    os.makedirs(app_bin, exist_ok=True)
    ffmpeg_dest = os.path.join(app_bin, "ffmpeg.exe")

    if os.path.isfile(ffmpeg_dest):
        if progress_callback:
            progress_callback(100, "FFmpeg already installed.")
        return ffmpeg_dest

    zip_path = os.path.join(app_bin, "ffmpeg_download.zip")

    for url, source_name in SOURCES:
        log.info("Downloading FFmpeg from %s…", source_name)
        if progress_callback:
            progress_callback(0, f"Connecting to {source_name}…")

        try:
            resp = requests.get(
                url, stream=True, timeout=(15, 60), allow_redirects=True,
                headers={"User-Agent": "Anz-Creator/1.0"},
            )
            resp.raise_for_status()

            total = int(resp.headers.get("content-length", 0))
            downloaded = 0

            with open(zip_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=256 * 1024):
                    if cancel_flag and cancel_flag():
                        f.close()
                        if os.path.exists(zip_path):
                            os.remove(zip_path)
                        raise RuntimeError("FFmpeg download cancelled.")

                    f.write(chunk)
                    downloaded += len(chunk)

                    if total > 0 and progress_callback:
                        pct = downloaded * 100 // total
                        dl_mb = downloaded // 1048576
                        tot_mb = total // 1048576
                        progress_callback(pct, f"Downloading FFmpeg… {dl_mb}/{tot_mb} MB")

            log.info("Download complete. Extracting…")
            if progress_callback:
                progress_callback(95, "Extracting FFmpeg… (Please wait)")
            break

        except Exception as exc:
            log.warning("FFmpeg download from %s failed: %s", source_name, exc)
            if os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except OSError:
                    pass
            continue
    else:
        log.error("All FFmpeg download sources failed.")
        raise RuntimeError("Failed to download FFmpeg from all sources.")

    # Extract only the binaries we need
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.namelist():
                basename = os.path.basename(member)
                if basename in ("ffmpeg.exe", "ffprobe.exe"):
                    target = os.path.join(app_bin, basename)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    log.info("Extracted: %s", target)

        os.remove(zip_path)

        if os.path.isfile(ffmpeg_dest):
            log.info("FFmpeg ready: %s", ffmpeg_dest)
            if progress_callback:
                progress_callback(100, "FFmpeg installation complete.")
            return ffmpeg_dest

    except zipfile.BadZipFile as exc:
        log.error("FFmpeg zip is corrupt: %s", exc)
        if os.path.exists(zip_path):
            os.remove(zip_path)
        raise RuntimeError(f"Corrupt zip file: {exc}")
    except Exception as exc:
        log.error("FFmpeg extraction failed: %s", exc)
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except OSError:
                pass
        raise

    return "ffmpeg"


def get_video_info(path: str) -> VideoInfo:
    """Read video metadata. Tries OpenCV first, falls back to ffprobe."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Video file not found: {path}")

    # Try OpenCV first (fast)
    width, height, fps, frame_count, codec = 0, 0, 0.0, 0, ""
    cap = None
    try:
        cap = cv2.VideoCapture(path)
        if cap.isOpened():
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            codec = _fourcc_to_str(int(cap.get(cv2.CAP_PROP_FOURCC)))
    except Exception as exc:
        log.warning("OpenCV metadata failed: %s", exc)
    finally:
        if cap is not None:
            cap.release()

    # If OpenCV returned invalid data, try ffprobe
    if width <= 0 or height <= 0 or fps <= 0:
        log.info("OpenCV returned %dx%d — trying ffprobe…", width, height)
        try:
            cf, si = _subprocess_silent()
            cmd = [
                _find_ffprobe(),
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries",
                "stream=width,height,r_frame_rate,nb_frames,codec_name",
                "-show_entries", "format=duration",
                "-of", "json",
                path,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10,
                creationflags=cf, startupinfo=si,
                encoding="utf-8", errors="replace",
            )
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                streams = data.get("streams", [])
                stream = streams[0] if streams else {}
                fmt = data.get("format", {})

                width = int(stream.get("width", 0)) or width
                height = int(stream.get("height", 0)) or height
                codec = stream.get("codec_name", codec) or codec

                # Parse r_frame_rate like "30/1" or "30000/1001"
                rfr = stream.get("r_frame_rate", "")
                if "/" in rfr:
                    parts = rfr.split("/")
                    if len(parts) == 2:
                        try:
                            num_f = float(parts[0])
                            den_f = float(parts[1])
                            if den_f > 0:
                                fps = num_f / den_f
                        except ValueError:
                            pass
                elif rfr:
                    try:
                        fps = float(rfr)
                    except ValueError:
                        pass

                nb = stream.get("nb_frames", "")
                if nb and nb != "N/A":
                    try:
                        frame_count = int(nb)
                    except ValueError:
                        pass

                dur_str = fmt.get("duration", "")
                if dur_str and fps > 0 and frame_count <= 0:
                    try:
                        frame_count = int(float(dur_str) * fps)
                    except ValueError:
                        pass

                log.info(
                    "ffprobe info: %dx%d @ %.1ffps, %d frames, codec=%s",
                    width, height, fps, frame_count, codec,
                )
        except Exception as exc:
            log.warning("ffprobe failed: %s", exc)

    # Final defaults
    fps = fps if fps > 0 else 30.0
    width = width if width > 0 else 640
    height = height if height > 0 else 480

    duration = frame_count / fps if fps > 0 and frame_count > 0 else 0.0

    info = VideoInfo(
        path=path,
        width=width,
        height=height,
        fps=fps,
        frame_count=frame_count,
        duration=duration,
        codec=codec,
    )
    log.info(
        "Video info: %dx%d @ %.1ffps, %d frames (%.1fs)",
        info.width, info.height, info.fps, info.frame_count, info.duration,
    )
    return info


def read_frame(path: str, frame_idx: int) -> np.ndarray:
    """Read a single frame by index. Returns a contiguous BGR numpy array."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Video file not found: {path}")
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {path}")
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            raise IOError(f"Cannot read frame {frame_idx} from {path}")
        return np.ascontiguousarray(frame)
    finally:
        cap.release()


def iter_frames(path: str) -> Generator[tuple[int, np.ndarray], None, None]:
    """Yield (index, frame) tuples."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        log.warning("Cannot open video for iteration: %s", path)
        return
    idx = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            yield idx, frame
            idx += 1
    finally:
        cap.release()


def _fourcc_to_str(code: int) -> str:
    try:
        return "".join(chr((code >> (8 * i)) & 0xFF) for i in range(4))
    except (ValueError, OverflowError):
        return "unknown"
