"""
Watermark Detector — Auto mode using YOLOv8 + OpenCV fallback.
Outputs binary masks for detected watermarks.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

import cv2
import numpy as np

from utils.logger import log


class WatermarkDetector:
    """
    Detect watermarks in video frames.
    Primary: YOLOv8 object detection.
    Fallback: OpenCV frequency/alpha analysis for low-confidence results.
    """

    def __init__(self, model_path: str, confidence_threshold: float = 0.3):
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return
        try:
            from ultralytics import YOLO
            self._model = YOLO(self.model_path)
            log.info("YOLOv8 model loaded: %s", self.model_path)
        except ImportError:
            log.error(
                "ultralytics package not installed. "
                "Install with: pip install ultralytics"
            )
            raise
        except Exception as exc:
            log.error("Failed to load YOLOv8: %s", exc)
            raise

    # ── Main detection pipeline ──────────────────────────
    def detect_and_generate_masks(
        self,
        frames_dir: str,
        masks_dir: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_flag: Optional[Callable[[], bool]] = None,
    ) -> str:
        """
        Detect watermarks in all frames, generate binary masks.
        Returns masks_dir.
        """
        self._load_model()
        os.makedirs(masks_dir, exist_ok=True)

        frame_files = sorted([
            f for f in os.listdir(frames_dir) if f.endswith(".png")
        ])
        total = len(frame_files)

        if total == 0:
            log.warning("No frames found in %s", frames_dir)
            return masks_dir

        log.info("Detecting watermarks in %d frames…", total)

        for i, fname in enumerate(frame_files):
            if cancel_flag and cancel_flag():
                return masks_dir

            frame_path = os.path.join(frames_dir, fname)
            frame = cv2.imread(frame_path)

            if frame is None:
                log.warning(
                    "Cannot read frame: %s, generating empty mask", fname,
                )
                # Create empty mask with default size
                mask = np.zeros((480, 640), dtype=np.uint8)
                cv2.imwrite(os.path.join(masks_dir, fname), mask)
                continue

            h, w = frame.shape[:2]

            # Run YOLOv8
            bbox = self._yolo_detect(frame)

            # Fallback to OpenCV if YOLO confidence is low
            if bbox is None:
                bbox = self._opencv_fallback(frame)

            # Generate mask
            mask = np.zeros((h, w), dtype=np.uint8)
            if bbox is not None:
                x1, y1, x2, y2 = bbox
                # Expand bbox slightly for better coverage
                pad = 5
                x1 = max(0, x1 - pad)
                y1 = max(0, y1 - pad)
                x2 = min(w, x2 + pad)
                y2 = min(h, y2 + pad)
                mask[y1:y2, x1:x2] = 255

            mask_path = os.path.join(masks_dir, fname)
            cv2.imwrite(mask_path, mask)

            if progress_callback and i % 10 == 0:
                pct = int((i + 1) / total * 100)
                progress_callback(
                    pct, f"Detecting watermarks… {i + 1}/{total}",
                )

        if progress_callback:
            progress_callback(100, "Watermark detection complete.")
        log.info("Masks saved to %s", masks_dir)
        return masks_dir

    # ── YOLOv8 detection ─────────────────────────────────
    def _yolo_detect(
        self, frame: np.ndarray,
    ) -> Optional[tuple[int, int, int, int]]:
        """Run YOLO and return (x1, y1, x2, y2) or None."""
        try:
            results = self._model(frame, verbose=False)
            if not results or len(results[0].boxes) == 0:
                return None

            # Pick highest confidence detection
            boxes = results[0].boxes
            confs = boxes.conf.cpu().numpy()

            if len(confs) == 0:
                return None

            best_idx = confs.argmax()

            if confs[best_idx] < self.confidence_threshold:
                return None

            xyxy = boxes.xyxy[best_idx].cpu().numpy().astype(int)
            return (int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3]))
        except Exception as exc:
            log.warning("YOLO detection failed on frame: %s", exc)
            return None

    # ── OpenCV fallback (frequency analysis) ─────────────
    @staticmethod
    def _opencv_fallback(
        frame: np.ndarray,
    ) -> Optional[tuple[int, int, int, int]]:
        """
        Use high-frequency + alpha analysis to find semi-transparent
        watermarks. Checks corners and edges where watermarks typically
        appear.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # Focus on typical watermark regions (corners, bottom, top-right)
        regions = [
            ("bottom_right", (int(w * 0.6), int(h * 0.8), w, h)),
            ("bottom_left", (0, int(h * 0.8), int(w * 0.4), h)),
            ("top_right", (int(w * 0.6), 0, w, int(h * 0.2))),
            ("top_left", (0, 0, int(w * 0.4), int(h * 0.2))),
        ]

        best_score = 0.0
        best_bbox = None

        for _name, (rx1, ry1, rx2, ry2) in regions:
            roi = gray[ry1:ry2, rx1:rx2]

            # Skip empty ROIs
            if roi.size == 0:
                continue

            # Edge density as watermark indicator
            edges = cv2.Canny(roi, 100, 200)
            score = float(np.mean(edges)) / 255.0

            # Watermarks often have distinctive high-freq patterns
            laplacian = cv2.Laplacian(roi, cv2.CV_64F)
            freq_score = float(np.std(laplacian)) / 255.0

            combined = score * 0.5 + freq_score * 0.5

            if combined > best_score and combined > 0.05:
                best_score = combined
                best_bbox = (rx1, ry1, rx2, ry2)

        return best_bbox
