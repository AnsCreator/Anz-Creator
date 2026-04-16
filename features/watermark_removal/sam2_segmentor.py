"""
SAM2 Segmentor — Manual mode for pixel-perfect watermark segmentation.
User clicks on watermark → SAM2 segments + propagates across frames.
"""

from __future__ import annotations

import os
import sys
from typing import Callable, Optional

import cv2
import numpy as np
import torch

from utils.logger import log


class SAM2Segmentor:
    """
    Interactive segmentation using Meta's SAM2.
    """

    def __init__(self, model_path: str, device: str = "cuda"):
        self.model_path = model_path
        self.device = device if torch.cuda.is_available() else "cpu"
        self._predictor = None
        self._video_predictor = None

    def _find_sam2_config(self) -> str:
        """
        Locate the correct SAM2 YAML config file for the current checkpoint.
        Searches the SAM2 package directory for a file containing '_target_'
        that matches the expected model size.
        """
        if getattr(sys, 'frozen', False):
            base_dir = sys._MEIPASS
        else:
            import sam2
            base_dir = os.path.dirname(sam2.__file__)

        model_name = os.path.basename(self.model_path).lower()
        if "tiny" in model_name:
            target_patterns = ["sam2_hiera_t.yaml", "sam2_hiera_tiny.yaml"]
        elif "small" in model_name:
            target_patterns = ["sam2_hiera_s.yaml", "sam2_hiera_small.yaml"]
        elif "large" in model_name:
            target_patterns = ["sam2_hiera_l.yaml", "sam2_hiera_large.yaml"]
        else:
            target_patterns = ["sam2_hiera_b+.yaml", "sam2_hiera_base.yaml", "sam2_hiera_b_plus.yaml"]

        # Walk the base directory for a config file that contains '_target_' (actual model config)
        for root, _, files in os.walk(base_dir):
            for file in files:
                if any(file.endswith(pat) for pat in target_patterns):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            if "_target_" in f.read():
                                return filepath
                    except Exception:
                        continue

        # Fallback: any YAML with '_target_' in the sam2 folder
        for root, _, files in os.walk(base_dir):
            for file in files:
                if file.endswith(".yaml"):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            if "_target_" in f.read():
                                log.warning("Using fallback config: %s", filepath)
                                return filepath
                    except Exception:
                        continue

        raise FileNotFoundError(f"Could not find SAM2 config for {self.model_path} in {base_dir}")

    def _load_model(self):
        """Load SAM2 model using official builder with explicit config."""
        if self._predictor is not None and self._video_predictor is not None:
            return

        log.info("Loading SAM2 from %s on %s", self.model_path, self.device)

        try:
            # Gunakan builder khusus video dari SAM2
            from sam2.build_sam import build_sam2_video_predictor
            from sam2.sam2_image_predictor import SAM2ImagePredictor

            # Find the correct config file based on checkpoint name
            config_file = self._find_sam2_config()
            log.info("Using SAM2 config: %s", config_file)

            # 1. Build Video Predictor terlebih dahulu (Ini akan menghasilkan objek SAM2Base)
            self._video_predictor = build_sam2_video_predictor(
                config_file=config_file,
                ckpt_path=self.model_path,
                device=self.device,
                apply_postprocessing=True,
            )

            # 2. Image Predictor dapat menggunakan/membungkus objek Video Predictor secara langsung
            # Ini sangat menghemat VRAM karena tidak perlu load bobot model dua kali
            self._predictor = SAM2ImagePredictor(self._video_predictor)
            
            log.info("SAM2 predictors ready")

        except Exception as e:
            log.error("Failed to load SAM2: %s", e)
            raise

    def segment_frame(
        self,
        frame: np.ndarray,
        click_points: list[tuple[int, int]],
        click_labels: Optional[list[int]] = None,
    ) -> np.ndarray:
        self._load_model()

        if not click_points:
            raise ValueError("At least one click point is required.")

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

        if len(scores) == 0:
            log.warning("SAM2 returned no masks")
            return np.zeros(frame.shape[:2], dtype=np.uint8)

        best_idx = scores.argmax()
        mask = masks[best_idx]
        binary_mask = (mask > 0.5).astype(np.uint8) * 255
        log.info("SAM2 segmented mask — %d pixels", np.sum(mask > 0.5))
        return binary_mask

    def propagate_masks(
        self,
        frames_dir: str,
        initial_mask: np.ndarray,
        masks_dir: str,
        scene_cuts: Optional[list[int]] = None,
        click_points: Optional[list[tuple[int, int]]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_flag: Optional[Callable[[], bool]] = None,
    ) -> str:
        self._load_model()

        os.makedirs(masks_dir, exist_ok=True)

        frame_files = sorted([f for f in os.listdir(frames_dir) if f.endswith(".png")])
        total = len(frame_files)

        if total == 0:
            log.warning("No frames found in %s", frames_dir)
            return masks_dir

        log.info("Propagating masks across %d frames…", total)

        if progress_callback:
            progress_callback(0, "Propagating masks…")

        state = self._video_predictor.init_state(video_path=frames_dir)

        mask_tensor = torch.from_numpy(initial_mask.astype(np.float32) / 255.0).to(self.device)

        self._video_predictor.add_new_mask(
            inference_state=state,
            frame_idx=0,
            obj_id=1,
            mask=mask_tensor,
        )

        if scene_cuts and click_points:
            for sc_frame in scene_cuts:
                if 0 < sc_frame < total:
                    frame_path = os.path.join(frames_dir, frame_files[sc_frame])
                    frame = cv2.imread(frame_path)
                    if frame is not None:
                        try:
                            re_mask = self.segment_frame(frame, click_points)
                            re_mask_tensor = torch.from_numpy(re_mask.astype(np.float32) / 255.0).to(self.device)
                            self._video_predictor.add_new_mask(
                                inference_state=state,
                                frame_idx=sc_frame,
                                obj_id=1,
                                mask=re_mask_tensor,
                            )
                        except Exception as exc:
                            log.warning("Re-init at scene cut %d failed: %s", sc_frame, exc)

        for frame_idx, obj_ids, masks in self._video_predictor.propagate_in_video(state):
            if cancel_flag and cancel_flag():
                return masks_dir

            if frame_idx >= total:
                break

            mask_data = masks[0].cpu().numpy().squeeze()
            mask_np = (mask_data > 0.5).astype(np.uint8) * 255
            mask_path = os.path.join(masks_dir, frame_files[frame_idx])
            cv2.imwrite(mask_path, mask_np)

            if progress_callback and frame_idx % 10 == 0:
                pct = int((frame_idx + 1) / total * 100)
                progress_callback(pct, f"Propagating masks… {frame_idx + 1}/{total}")

        if progress_callback:
            progress_callback(100, "Mask propagation complete.")
        log.info("Masks saved to %s", masks_dir)
        return masks_dir
