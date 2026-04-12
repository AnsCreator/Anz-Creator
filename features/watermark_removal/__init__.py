"""
Watermark Removal Feature — plugin entry point.
Orchestrates the full pipeline: detect/segment → inpaint → rebuild.
"""

from __future__ import annotations

import os
import shutil
from typing import Callable

from utils.ffmpeg_wrapper import FFmpegWrapper
from utils.scene_detector import detect_scenes
from core.video_io import get_video_info

from .detector import WatermarkDetector
from .sam2_segmentor import SAM2Segmentor
from .inpainter import ProPainterInpainter


class WatermarkRemovalPipeline:
    """
    Full watermark removal pipeline.
    Modes: 'auto' (YOLO) or 'manual' (SAM2 click-based).
    """

    def __init__(
        self,
        yolo_model_path: str = "",
        sam2_model_path: str = "",
        propainter_model_dir: str = "",
        propainter_mode: str = "standard",
        temp_dir: str = "temp",
        device: str = "cuda",
    ):
        self.temp_dir = temp_dir
        self.frames_dir = os.path.join(temp_dir, "frames")
        self.masks_dir = os.path.join(temp_dir, "masks")
        self.output_frames_dir = os.path.join(temp_dir, "output")
        self.device = device

        self.detector = WatermarkDetector(yolo_model_path) if yolo_model_path else None
        self.segmentor = SAM2Segmentor(sam2_model_path, device=device) if sam2_model_path else None
        self.inpainter = ProPainterInpainter(propainter_model_dir, mode=propainter_mode, device=device)

    def clean_temp(self):
        """Remove temporary files."""
        for d in [self.frames_dir, self.masks_dir, self.output_frames_dir]:
            if os.path.exists(d):
                shutil.rmtree(d)
            os.makedirs(d, exist_ok=True)

    # ── Full auto pipeline ───────────────────────────────
    def run_auto(
        self,
        video_path: str,
        output_path: str,
        progress_callback: Callable[[int, str], None] = None,
        cancel_flag: Callable[[], bool] = None,
    ) -> str:
        """Run full auto-detection pipeline."""
        self.clean_temp()
        info = get_video_info(video_path)

        # Step 1: Extract frames
        _emit(progress_callback, 5, "Step 1/4: Extracting frames…")
        FFmpegWrapper.extract_frames(video_path, self.frames_dir, cancel_flag=cancel_flag)
        if cancel_flag and cancel_flag():
            return ""

        # Step 2: Detect watermarks
        _emit(progress_callback, 25, "Step 2/4: Detecting watermarks…")
        self.detector.detect_and_generate_masks(
            self.frames_dir, self.masks_dir,
            progress_callback=lambda p, m: _emit(progress_callback, 25 + int(p * 0.25), m),
            cancel_flag=cancel_flag,
        )
        if cancel_flag and cancel_flag():
            return ""

        # Step 3: Inpaint
        _emit(progress_callback, 50, "Step 3/4: Inpainting…")
        self.inpainter.inpaint(
            self.frames_dir, self.masks_dir, self.output_frames_dir,
            progress_callback=lambda p, m: _emit(progress_callback, 50 + int(p * 0.35), m),
            cancel_flag=cancel_flag,
        )
        if cancel_flag and cancel_flag():
            return ""

        # Step 4: Rebuild video
        _emit(progress_callback, 85, "Step 4/4: Rebuilding video…")
        result = FFmpegWrapper.rebuild_video(
            self.output_frames_dir, video_path, output_path,
            fps=info.fps, cancel_flag=cancel_flag,
        )

        _emit(progress_callback, 100, "Done!")
        return result

    # ── Manual pipeline (SAM2-based) ─────────────────────
    def run_manual(
        self,
        video_path: str,
        output_path: str,
        click_points: list[tuple[int, int]],
        click_labels: list[int] = None,
        progress_callback: Callable[[int, str], None] = None,
        cancel_flag: Callable[[], bool] = None,
    ) -> str:
        """Run manual SAM2-based pipeline with user click points."""
        self.clean_temp()
        info = get_video_info(video_path)

        # Step 1: Extract frames
        _emit(progress_callback, 5, "Step 1/5: Extracting frames…")
        FFmpegWrapper.extract_frames(video_path, self.frames_dir, cancel_flag=cancel_flag)
        if cancel_flag and cancel_flag():
            return ""

        # Step 2: Detect scene cuts
        _emit(progress_callback, 15, "Step 2/5: Detecting scene cuts…")
        scenes = detect_scenes(video_path)
        scene_start_frames = [s for s, _ in scenes] if scenes else []

        # Step 3: SAM2 segment + propagate
        _emit(progress_callback, 20, "Step 3/5: Segmenting watermark…")
        import cv2
        first_frame = cv2.imread(
            os.path.join(self.frames_dir,
                         sorted(os.listdir(self.frames_dir))[0])
        )
        initial_mask = self.segmentor.segment_frame(first_frame, click_points, click_labels)

        _emit(progress_callback, 30, "Step 3/5: Propagating mask…")
        self.segmentor.propagate_masks(
            self.frames_dir, initial_mask, self.masks_dir,
            scene_cuts=scene_start_frames,
            click_points=click_points,
            progress_callback=lambda p, m: _emit(progress_callback, 30 + int(p * 0.25), m),
            cancel_flag=cancel_flag,
        )
        if cancel_flag and cancel_flag():
            return ""

        # Step 4: Inpaint
        _emit(progress_callback, 55, "Step 4/5: Inpainting…")
        self.inpainter.inpaint(
            self.frames_dir, self.masks_dir, self.output_frames_dir,
            progress_callback=lambda p, m: _emit(progress_callback, 55 + int(p * 0.30), m),
            cancel_flag=cancel_flag,
        )
        if cancel_flag and cancel_flag():
            return ""

        # Step 5: Rebuild video
        _emit(progress_callback, 85, "Step 5/5: Rebuilding video…")
        result = FFmpegWrapper.rebuild_video(
            self.output_frames_dir, video_path, output_path,
            fps=info.fps, cancel_flag=cancel_flag,
        )

        _emit(progress_callback, 100, "Done!")
        return result


def _emit(cb, pct, msg):
    if cb:
        cb(pct, msg)
