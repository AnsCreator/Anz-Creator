"""
Video read/write utilities (metadata, frame access).
"""

from __future__ import annotations

import os
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


def get_video_info(path: str) -> VideoInfo:
    """Read video metadata using OpenCV."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Video file not found: {path}")
    # Use numpy-based open for Unicode path support on Windows
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {path}")
    info = VideoInfo(
        path=path,
        width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        fps=cap.get(cv2.CAP_PROP_FPS) or 30.0,
        frame_count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        duration=0,
        codec=_fourcc_to_str(int(cap.get(cv2.CAP_PROP_FOURCC))),
    )
    info.duration = info.frame_count / info.fps if info.fps > 0 else 0
    cap.release()
    log.info("Video info: %dx%d @ %.1ffps, %d frames", info.width, info.height, info.fps, info.frame_count)
    return info


def read_frame(path: str, frame_idx: int) -> np.ndarray:
    """Read a single frame by index. Returns a contiguous BGR numpy array."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Video file not found: {path}")
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {path}")
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        raise IOError(f"Cannot read frame {frame_idx} from {path}")
    return np.ascontiguousarray(frame)


def iter_frames(path: str) -> Generator[tuple[int, np.ndarray], None, None]:
    """Yield (index, frame) tuples."""
    cap = cv2.VideoCapture(path)
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        yield idx, frame
        idx += 1
    cap.release()


def _fourcc_to_str(code: int) -> str:
    return "".join(chr((code >> (8 * i)) & 0xFF) for i in range(4))
