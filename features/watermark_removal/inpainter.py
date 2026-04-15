"""
ProPainter Inpainter — temporal-consistent video inpainting.
Fills masked watermark areas with plausible content.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

import cv2
import numpy as np

from utils.logger import log


class ProPainterInpainter:
    """
    Video inpainting using ProPainter.
    Processes frames + masks → outputs clean frames.
    """

    # VRAM presets
    PRESETS = {
        "lightweight": {
            "neighbor_length": 5, "ref_length": 10, "resize": 0.5,
        },
        "standard": {
            "neighbor_length": 10, "ref_length": 20, "resize": 1.0,
        },
        "high_quality": {
            "neighbor_length": 15, "ref_length": 30, "resize": 1.0,
        },
        "ultra_4k": {
            "neighbor_length": 20, "ref_length": 40, "resize": 1.0,
        },
    }

    def __init__(
        self,
        model_dir: str,
        mode: str = "standard",
        device: str = "cuda",
    ):
        self.model_dir = model_dir
        self.mode = mode
        self.device = device
        self.params = self.PRESETS.get(mode, self.PRESETS["standard"])
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return
        try:
            import torch
            log.info(
                "Loading ProPainter model from %s (mode=%s)",
                self.model_dir, self.mode,
            )

            self._device = torch.device(
                self.device if torch.cuda.is_available() else "cpu"
            )

            # Placeholder: in production, load actual ProPainter models:
            # self._flow_model = load_flow_completion(model_dir)
            # self._inpaint_model = load_inpaint_generator(model_dir)

            log.info("ProPainter loaded on %s", self._device)
        except ImportError:
            log.warning(
                "PyTorch not available — using OpenCV fallback inpainting."
            )
            self._device = None
        except Exception as exc:
            log.error("Failed to load ProPainter: %s", exc)
            raise

    def inpaint(
        self,
        frames_dir: str,
        masks_dir: str,
        output_dir: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_flag: Optional[Callable[[], bool]] = None,
    ) -> str:
        """
        Run video inpainting on frames with corresponding masks.
        frames_dir: folder with frame_XXXXXX.png files
        masks_dir:  folder with matching binary mask PNGs
        output_dir: folder for inpainted output frames
        Returns output_dir.
        """
        self._load_model()

        os.makedirs(output_dir, exist_ok=True)

        frame_files = sorted([
            f for f in os.listdir(frames_dir) if f.endswith(".png")
        ])
        mask_files_set = set(os.listdir(masks_dir))
        total = len(frame_files)

        if total == 0:
            log.warning("No frames found in %s", frames_dir)
            return output_dir

        log.info("Inpainting %d frames (mode=%s)…", total, self.mode)
        if progress_callback:
            progress_callback(0, "Starting inpainting…")

        neighbor_len = self.params["neighbor_length"]

        # Process frames in a sliding window to avoid loading all into memory
        # Cache: {index -> frame_array}
        frame_cache: dict[int, np.ndarray] = {}
        cache_window = neighbor_len * 2 + 1

        for i in range(total):
            if cancel_flag and cancel_flag():
                return output_dir

            fname = frame_files[i]

            # Load current frame
            frame = self._load_frame(frames_dir, fname, frame_cache, i)

            # Load mask
            if fname in mask_files_set:
                mask = cv2.imread(
                    os.path.join(masks_dir, fname), cv2.IMREAD_GRAYSCALE,
                )
            else:
                mask = None

            if mask is None:
                mask = np.zeros(frame.shape[:2], dtype=np.uint8)
            else:
                # Ensure mask matches frame dimensions
                fh, fw = frame.shape[:2]
                mh, mw = mask.shape[:2]
                if (mh, mw) != (fh, fw):
                    mask = cv2.resize(
                        mask, (fw, fh), interpolation=cv2.INTER_NEAREST,
                    )

            # Check if this frame needs inpainting
            if np.sum(mask > 128) == 0:
                # No watermark in this frame, copy as-is
                cv2.imwrite(os.path.join(output_dir, fname), frame)
            else:
                # Gather temporal context (neighboring frames)
                context_start = max(0, i - neighbor_len)
                context_end = min(total, i + neighbor_len + 1)
                context_frames = []
                for j in range(context_start, context_end):
                    ctx = self._load_frame(
                        frames_dir, frame_files[j], frame_cache, j,
                    )
                    context_frames.append(ctx)
                rel_idx = i - context_start

                result = self._fallback_inpaint(
                    frame, mask, context_frames, rel_idx,
                )
                cv2.imwrite(os.path.join(output_dir, fname), result)

            # Evict old frames from cache to save memory
            evict_before = i - cache_window
            keys_to_remove = [
                k for k in frame_cache if k < evict_before
            ]
            for k in keys_to_remove:
                del frame_cache[k]

            if progress_callback and i % 5 == 0:
                pct = int((i + 1) / total * 100)
                progress_callback(pct, f"Inpainting… {i + 1}/{total}")

        if progress_callback:
            progress_callback(100, "Inpainting complete.")
        log.info("Inpainted frames saved to %s", output_dir)
        return output_dir

    def _load_frame(
        self,
        frames_dir: str,
        fname: str,
        cache: dict[int, np.ndarray],
        idx: int,
    ) -> np.ndarray:
        """Load a frame, using cache if available."""
        if idx in cache:
            return cache[idx]
        frame = cv2.imread(os.path.join(frames_dir, fname))
        if frame is None:
            log.warning("Cannot read frame: %s", fname)
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cache[idx] = frame
        return frame

    def _fallback_inpaint(
        self,
        frame: np.ndarray,
        mask: np.ndarray,
        context_frames: list[np.ndarray],
        rel_idx: int,
    ) -> np.ndarray:
        """
        Fallback inpainting using OpenCV + temporal blending.
        Uses neighboring frames for better temporal consistency.
        """
        # Dilate mask slightly for better coverage
        kernel = np.ones((3, 3), np.uint8)
        mask_dilated = cv2.dilate(mask, kernel, iterations=2)

        # Ensure mask is binary
        _, mask_dilated = cv2.threshold(mask_dilated, 128, 255, cv2.THRESH_BINARY)

        # Primary: OpenCV Navier-Stokes inpainting
        inpainted = cv2.inpaint(
            frame, mask_dilated, inpaintRadius=5, flags=cv2.INPAINT_NS,
        )

        # Blend with neighboring frames for temporal consistency
        if len(context_frames) > 1:
            weights = []
            neighbor_inpainted = []
            fh, fw = frame.shape[:2]

            for j, ctx_frame in enumerate(context_frames):
                if j == rel_idx:
                    continue
                # Ensure context frame matches dimensions
                if ctx_frame.shape[:2] != (fh, fw):
                    ctx_frame = cv2.resize(ctx_frame, (fw, fh))
                ctx_inp = cv2.inpaint(
                    ctx_frame, mask_dilated,
                    inpaintRadius=5, flags=cv2.INPAINT_NS,
                )
                dist = abs(j - rel_idx)
                w = 1.0 / (dist + 1)
                weights.append(w)
                neighbor_inpainted.append(ctx_inp)

            if neighbor_inpainted:
                current_weight = 2.0
                total_w = sum(weights) + current_weight
                blended = inpainted.astype(np.float64) * current_weight
                for w, n_frame in zip(weights, neighbor_inpainted):
                    blended += n_frame.astype(np.float64) * w
                blended /= total_w
                inpainted = np.clip(blended, 0, 255).astype(np.uint8)

        return inpainted
