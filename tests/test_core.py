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
        assert len(y
