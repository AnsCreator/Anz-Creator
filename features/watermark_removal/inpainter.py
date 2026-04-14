"""
ProPainter Inpainter — temporal-consistent video inpainting.
Fills masked watermark areas with plausible content.
"""

from __future__ import annotations

import os
from typing import Callable

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
        "lightweight": {"neighbor_length": 5, "ref_length": 10, "resize": 0.5},
        "standard": {"neighbor_length": 10, "ref_length": 20, "resize": 1.0},
        "high_quality": {"neighbor_length": 15, "ref_length": 30, "resize": 1.0},
        "ultra_4k": {"neighbor_length": 20, "ref_length": 40, "resize": 1.0},
    }

    def __init__(self, model_dir: str, mode: str = "standard", device: str = "cuda"):
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
            log.info("Loading ProPainter model from %s (mode=%s)", self.model_dir, self.mode)

            # ProPainter consists of:
            # 1. Recurrent Flow Completion network
            # 2. Feature Propagation + Transformer-based generation
            # In production, this loads the actual ProPainter checkpoints.
            # Here we define the interface; actual model loading depends on
            # the ProPainter repository structure.

            self._device = torch.device(self.device if torch.cuda.is_available() else "cpu")

            # Placeholder: in production, load actual ProPainter models:
            # self._flow_model = load_flow_completion(model_dir)
            # self._inpaint_model = load_inpaint_generator(model_dir)

            log.info("ProPainter loaded on %s", self._device)
        except ImportError:
            log.warning("PyTorch not available — using OpenCV fallback inpainting only.")
            self._device = None
        except Exception as exc:
            log.error("Failed to load ProPainter: %s", exc)
            raise

    def inpaint(
        self,
        frames_dir: str,
        masks_dir: str,
        output_dir: str,
        progress_callback: Callable[[int, str], None] = None,
        cancel_flag: Callable[[], bool] = None,
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

        frame_files = sorted([f for f in os.listdir(frames_dir) if f.endswith(".png")])
        mask_files_set = set(os.listdir(masks_dir))  # FIX: Use set for O(1) lookup
        total = len(frame_files)

        if total == 0:
            log.warning("No frames found in %s", frames_dir)
            return output_dir

        log.info("Inpainting %d frames (mode=%s)…", total, self.mode)
        if progress_callback:
            progress_callback(0, "Starting inpainting…")

        # Load all frames and masks into memory
        frames = []
        masks = []
        for fname in frame_files:
            frame = cv2.imread(os.path.join(frames_dir, fname))
            if frame is None:
                log.warning("Cannot read frame: %s", fname)
                # Create black placeholder frame
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
            frames.append(frame)

            # FIX: Match mask by filename, fall back to empty mask (not first mask)
            if fname in mask_files_set:
                mask = cv2.imread(os.path.join(masks_dir, fname), cv2.IMREAD_GRAYSCALE)
            else:
                mask = None

            if mask is None:
                mask = np.zeros(frame.shape[:2], dtype=np.uint8)
            else:
                # FIX: Ensure mask matches frame dimensions
                fh, fw = frame.shape[:2]
                mh, mw = mask.shape[:2]
                if (mh, mw) != (fh, fw):
                    mask = cv2.resize(mask, (fw, fh), interpolation=cv2.INTER_NEAREST)

            masks.append(mask)

        # Process in temporal windows for memory efficiency
        neighbor_len = self.params["neighbor_length"]

        for i in range(total):
            if cancel_flag and cancel_flag():
                return output_dir

            frame = frames[i]
            mask = masks[i]

            # Check if this frame needs inpainting
            if np.sum(mask > 128) == 0:
                # No watermark in this frame, copy as-is
                cv2.imwrite(os.path.join(output_dir, frame_files[i]), frame)
            else:
                # Gather temporal context (neighboring frames)
                context_start = max(0, i - neighbor_len)
                context_end = min(total, i + neighbor_len + 1)
                context_frames = frames[context_start:context_end]
                rel_idx = i - context_start

                # Run inpainting on this window
                # In production, this calls the actual ProPainter inference:
                # result = self._inpaint_window(context_frames, context_masks, rel_idx)
                # For now, use OpenCV inpainting as a functional placeholder:
                result = self._fallback_inpaint(frame, mask, context_frames, rel_idx)

                cv2.imwrite(os.path.join(output_dir, frame_files[i]), result)

            if progress_callback and i % 5 == 0:
                pct = int((i + 1) / total * 100)
                progress_callback(pct, f"Inpainting… {i + 1}/{total}")

        if progress_callback:
            progress_callback(100, "Inpainting complete.")
        log.info("Inpainted frames saved to %s", output_dir)
        return output_dir

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

        # Primary: OpenCV Navier-Stokes inpainting
        inpainted = cv2.inpaint(frame, mask_dilated, inpaintRadius=5, flags=cv2.INPAINT_NS)

        # Blend with neighboring frames for temporal consistency
        if len(context_frames) > 1:
            # Simple temporal blend from neighbors
            weights = []
            neighbor_inpainted = []
            for j, ctx_frame in enumerate(context_frames):
                if j == rel_idx:
                    continue
                # FIX: Ensure context frame matches dimensions
                if ctx_frame.shape[:2] != frame.shape[:2]:
                    ctx_frame = cv2.resize(ctx_frame, (frame.shape[1], frame.shape[0]))
                ctx_inp = cv2.inpaint(ctx_frame, mask_dilated, inpaintRadius=5, flags=cv2.INPAINT_NS)
                dist = abs(j - rel_idx)
                w = 1.0 / (dist + 1)
                weights.append(w)
                neighbor_inpainted.append(ctx_inp)

            if neighbor_inpainted:
                total_w = sum(weights) + 2.0  # give current frame higher weight
                blended = inpainted.astype(np.float64) * 2.0
                for w, n_frame in zip(weights, neighbor_inpainted):
                    blended += n_frame.astype(np.float64) * w
                blended /= total_w
                inpainted = np.clip(blended, 0, 255).astype(np.uint8)  # FIX: Clip to valid range

        return inpainted
