"""
Unit tests for Anz-Creator core modules.
"""

import os
import sys

import pytest
import yaml

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _has_module(module_name: str) -> bool:
    """Check if a module can be imported."""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


class TestSettings:
    """Test core.settings module."""

    def setup_method(self):
        """Reset singleton before each test."""
        from core.settings import Settings
        Settings.reset_instance()

    def test_default_values(self):
        from core.settings import Settings
        s = Settings()
        assert s.get("models.yolov8") is not None
        assert s.get("models.sam2") is not None
        assert s.get("models.propainter") is not None

    def test_get_nonexistent_key(self):
        from core.settings import Settings
        s = Settings()
        assert s.get("does.not.exist") is None
        assert s.get("does.not.exist", "fallback") == "fallback"

    def test_set_and_get(self):
        from core.settings import Settings
        s = Settings()
        s.set("test.key", "hello")
        assert s.get("test.key") == "hello"

    def test_deep_merge_preserves_defaults(self):
        from core.settings import Settings
        s = Settings()
        assert s.get("ui.theme") == "dark_teal.xml"
        assert s.get("video.default_quality") == "1080p"


class TestConfig:
    """Test config.yaml structure."""

    def test_config_loads(self):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config.yaml",
        )
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)

        assert cfg["app"]["name"] == "Anz-Creator"
        assert "models" in cfg
        assert "yolov8" in cfg["models"]
        assert "sam2" in cfg["models"]
        assert "propainter" in cfg["models"]

    def test_yolov8_variants(self):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config.yaml",
        )
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)

        yolo = cfg["models"]["yolov8"]
        assert yolo["default"] == "yolov8m"
        assert len(yolo["options"]) == 4
        assert "yolov8n" in yolo["options"]
        assert "yolov8x" in yolo["options"]

    def test_sam2_variants(self):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config.yaml",
        )
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)

        sam2 = cfg["models"]["sam2"]
        assert sam2["default"] == "sam2_hiera_base_plus"
        assert len(sam2["options"]) == 4

    def test_propainter_modes(self):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config.yaml",
        )
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)

        pp = cfg["models"]["propainter"]
        assert pp["default"] == "standard"
        assert pp["options"]["standard"]["vram_gb"] == 6


class TestModelManager:
    """Test core.model_manager module."""

    def test_list_variants(self):
        from core.model_manager import ModelManager
        mm = ModelManager()
        variants = mm.list_variants("yolov8")
        assert len(variants) == 4
        names = [v["name"] for v in variants]
        assert "yolov8m" in names

    def test_default_variant(self):
        from core.model_manager import ModelManager
        mm = ModelManager()
        assert mm.default_variant("yolov8") == "yolov8m"
        assert mm.default_variant("sam2") == "sam2_hiera_base_plus"
        assert mm.default_variant("propainter") == "standard"

    def test_model_path(self):
        from core.model_manager import ModelManager
        mm = ModelManager()
        path = mm.model_path("yolov8", "yolov8m")
        assert path.endswith("yolov8m.pt")
        assert "yolov8" in path

    def test_get_url(self):
        from core.model_manager import ModelManager
        mm = ModelManager()
        url = mm.get_url("yolov8", "yolov8m")
        assert url is not None
        assert url.startswith("https://")

    def test_nonexistent_family(self):
        from core.model_manager import ModelManager
        mm = ModelManager()
        assert mm.list_variants("nonexistent") == []
        assert mm.default_variant("nonexistent") == ""
        assert mm.get_url("nonexistent", "x") is None


class TestFFmpegWrapper:
    """Test utils.ffmpeg_wrapper module."""

    def test_class_exists(self):
        from utils.ffmpeg_wrapper import FFmpegWrapper
        assert hasattr(FFmpegWrapper, "extract_frames")
        assert hasattr(FFmpegWrapper, "rebuild_video")
        assert hasattr(FFmpegWrapper, "get_fps")


class TestDownloader:
    """Test core.downloader module (no network)."""

    def test_class_exists(self):
        from core.downloader import Downloader
        assert hasattr(Downloader, "fetch_metadata")
        assert hasattr(Downloader, "download")

    def test_video_meta_defaults(self):
        from core.downloader import VideoMeta
        meta = VideoMeta()
        assert meta.url == ""
        assert meta.title == ""
        assert meta.duration == 0
        assert meta.available_qualities == []

    def test_normalize_url(self):
        from core.downloader import _normalize_url
        assert _normalize_url("youtube.com/watch?v=x") == "https://youtube.com/watch?v=x"
        assert _normalize_url("https://example.com") == "https://example.com"
        assert _normalize_url("  ") == ""


class TestTaskQueue:
    """Test core.task_queue module."""

    def test_worker_signals(self):
        from core.task_queue import Worker

        def dummy(progress_callback=None, cancel_flag=None):
            return 42

        w = Worker(dummy)
        assert hasattr(w.signals, "started")
        assert hasattr(w.signals, "progress")
        assert hasattr(w.signals, "finished")
        assert hasattr(w.signals, "error")
        assert hasattr(w.signals, "cancelled")

    def test_worker_cancel(self):
        from core.task_queue import Worker

        def dummy(progress_callback=None, cancel_flag=None):
            return None

        w = Worker(dummy)
        assert not w.is_cancelled
        w.cancel()
        assert w.is_cancelled


class TestWatermarkDetector:
    """Test features.watermark_removal.detector module."""

    def test_opencv_fallback_exists(self):
        pytest.importorskip("cv2")
        # Skip if torch not available (required for sam2 import chain)
        if not _has_module("torch"):
            pytest.skip("torch not installed")
        from features.watermark_removal.detector import WatermarkDetector
        assert hasattr(WatermarkDetector, "_opencv_fallback")

    def test_opencv_fallback_no_crash(self):
        pytest.importorskip("cv2")
        if not _has_module("torch"):
            pytest.skip("torch not installed")

        import numpy as np

        from features.watermark_removal.detector import WatermarkDetector

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = WatermarkDetector._opencv_fallback(frame)
        assert result is None


class TestInpainterPresets:
    """Test ProPainter preset configurations."""

    def test_presets_exist(self):
        pytest.importorskip("cv2")
        from features.watermark_removal.inpainter import ProPainterInpainter
        presets = ProPainterInpainter.PRESETS
        assert "lightweight" in presets
        assert "standard" in presets
        assert "high_quality" in presets
        assert "ultra_4k" in presets

    def test_standard_preset_values(self):
        pytest.importorskip("cv2")
        from features.watermark_removal.inpainter import ProPainterInpainter
        std = ProPainterInpainter.PRESETS["standard"]
        assert std["neighbor_length"] == 10
        assert std["ref_length"] == 20
        assert std["resize"] == 1.0


class TestUpdater:
    """Test core.updater module."""

    def test_parse_version(self):
        from core.updater import _parse_version
        assert _parse_version("v1.0.0.1") == (1, 0, 0, 1)
        assert _parse_version("v2.3.4.5") == (2, 3, 4, 5)
        assert _parse_version("v1.0") == (1, 0, 0, 0)
        assert _parse_version("") == (0, 0, 0, 0)

    def test_get_current_version(self):
        from core.updater import get_current_version
        ver = get_current_version()
        assert ver.startswith("v")
