"""
SAM2 Segmentor — Manual mode for pixel-perfect watermark segmentation.
User clicks on watermark → SAM2 segments + propagates across frames.
"""

from __future__ import annotations

import os
import cv2
import numpy as np
from typing import Callable

from utils.logger import log


class SAM2Segmentor:
    """
    Interactive segmentation using Meta's SAM2.
    1. User provides click points on the first frame.
    2. SAM2 generates pixel-precise mask for frame 0.
    3. SAM2 video predictor propagates mask across all frames.
    """

    def __init__(self, model_path: str, device: str = "cuda"):
        self.model_path = model_path
        self.device = device
        self._predictor = None
        self._video_predictor = None

    def _load_model(self):
        if self._predictor is not None:
            return
        try:
            import torch  # noqa: F401 — required by sam2
            from sam2.build_sam import build_sam2
            from sam2.sam2_image_predictor import SAM2ImagePredictor
            from sam2.sam2_video_predictor import SAM2VideoPredictor

            log.info("Loading SAM2 from %s on %s", self.model_path, self.device)
            # Use appropriate config based on model variant
            model_cfg = "sam2_hiera_b+.yaml"  # default for base+
            if "tiny" in self.model_path:
                model_cfg = "sam2_hiera_t.yaml"
            elif "small" in self.model_path:
                model_cfg = "sam2_hiera_s.yaml"
            elif "large" in self.model_path:
                model_cfg = "sam2_hiera_l.yaml"

            sam2_model = build_sam2(model_cfg, self.model_path, device=self.device)
            self._predictor = SAM2ImagePredictor(sam2_model)
            self._video_predictor = SAM2VideoPredictor(sam2_model)
            log.info("SAM2 loaded successfully.")
        except Exception as exc:
            log.error("Failed to load SAM2: %s", exc)
            raise

    # ── Segment first frame from click points ────────────
    def segment_frame(
        self,
        frame: np.ndarray,
        click_points: list[tuple[int, int]],
        click_labels: list[int] = None,
    ) -> np.ndarray:
        """
        Segment watermark in a single frame given user click points.
        click_points: [(x, y), ...] — positive clicks on the watermark.
        click_labels: [1, 1, ...] 1=foreground, 0=background.
        Returns binary mask (H, W) uint8 with 255 for watermark.
        """
        self._load_model()

        if click_labels is None:
            click_labels = [1] * len(click_points)

        self._predictor.set_image(frame)

        point_coords = np.array(click_points, dtype=np.float32)
        point_labels = np.array(click_labels, dtype=np.int32)

        masks, scores, _ = self._predictor.predict(
            point_coords=point_coords,
            point_labels=point_labels,
            multimask_output=True,
        )

        # Pick best mask (highest score)
        best_idx = scores.argmax()
        mask = masks[best_idx]

        # Convert to uint8 binary mask
        binary_mask = (mask > 0.5).astype(np.uint8) * 255
        log.info("SAM2 segmented mask — %d pixels", np.sum(mask > 0.5))
        return binary_mask

    # ── Propagate mask across all frames ─────────────────
    def propagate_masks(
        self,
        frames_dir: str,
        initial_mask: np.ndarray,
        masks_dir: str,
        scene_cuts: list[int] = None,
        click_points: list[tuple[int, int]] = None,
        progress_callback: Callable[[int, str], None] = None,
        cancel_flag: Callable[[], bool] = None,
    ) -> str:
        """
        Propagate the initial mask to all frames using SAM2 video predictor.
        Re-initializes at scene cuts if provided.
        Returns masks_dir.
        """
        self._load_model()
        import torch

        os.makedirs(masks_dir, exist_ok=True)

        frame_files = sorted([
            f for f in os.listdir(frames_dir) if f.endswith(".png")
        ])
        total = len(frame_files)
        log.info("Propagating masks across %d frames…", total)

        if progress_callback:
            progress_callback(0, "Propagating masks…")

        # Initialize video predictor
        state = self._video_predictor.init_state(video_path=frames_dir)

        # Add initial mask at frame 0
        _, _, _ = self._video_predictor.add_new_mask(
            inference_state=state,
            frame_idx=0,
            obj_id=1,
            mask=torch.from_numpy(initial_mask.astype(np.float32) / 255.0).to(self.device),
        )

        # Re-init at scene cuts if provided
        if scene_cuts:
            for sc_frame in scene_cuts:
                if sc_frame < total:
                    frame = cv2.imread(os.path.join(frames_dir, frame_files[sc_frame]))
                    if click_points:
                        re_mask = self.segment_frame(frame, click_points)
                        self._video_predictor.add_new_mask(
                            inference_state=state,
                            frame_idx=sc_frame,
                            obj_id=1,
                            mask=torch.from_numpy(re_mask.astype(np.float32) / 255.0).to(self.device),
                        )

        # Propagate
        for frame_idx, obj_ids, masks in self._video_predictor.propagate_in_video(state):
            if cancel_flag and cancel_flag():
                return masks_dir

            mask_np = (masks[0].cpu().numpy().squeeze() > 0.5).astype(np.uint8) * 255
            mask_path = os.path.join(masks_dir, frame_files[frame_idx])
            cv2.imwrite(mask_path, mask_np)

            if progress_callback and frame_idx % 10 == 0:
                pct = int((frame_idx + 1) / total * 100)
                progress_callback(pct, f"Propagating masks… {frame_idx + 1}/{total}")

        if progress_callback:
            progress_callback(100, "Mask propagation complete.")
        log.info("Masks saved to %s", masks_dir)
        return masks_dir
