"""
PySceneDetect wrapper — detect scene cuts to re-initialize trackers.
"""

from __future__ import annotations

from typing import Callable

from utils.logger import log

try:
    from scenedetect import SceneManager, open_video
    from scenedetect.detectors import ContentDetector
    HAS_SCENEDETECT = True
except ImportError:
    HAS_SCENEDETECT = False
    log.warning("PySceneDetect not installed — scene detection disabled.")


def detect_scenes(
    video_path: str,
    threshold: float = 27.0,
    progress_callback: Callable[[int, str], None] = None,
    cancel_flag: Callable[[], bool] = None,
) -> list[tuple[int, int]]:
    """
    Detect scene boundaries in a video.
    Returns list of (start_frame, end_frame) tuples per scene.
    """
    if not HAS_SCENEDETECT:
        log.warning("SceneDetect unavailable; treating entire video as one scene.")
        return []

    log.info("Detecting scenes in %s (threshold=%.1f)", video_path, threshold)
    if progress_callback:
        progress_callback(0, "Detecting scene cuts…")

    video = open_video(video_path)
    scene_mgr = SceneManager()
    scene_mgr.add_detector(ContentDetector(threshold=threshold))
    scene_mgr.detect_scenes(video)

    scene_list = scene_mgr.get_scene_list()

    results = []
    for start_time, end_time in scene_list:
        s = int(start_time.get_frames())
        e = int(end_time.get_frames())
        results.append((s, e))

    log.info("Detected %d scenes.", len(results))
    if progress_callback:
        progress_callback(100, f"Found {len(results)} scenes.")
    return results
