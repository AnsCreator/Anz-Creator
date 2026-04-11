# ⚡ Anz-Creator

AI-powered video processing toolkit built with PyQt6. Features watermark removal using YOLOv8, SAM2, and ProPainter.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Install FFmpeg (required)
# Windows: choco install ffmpeg  OR  download from https://ffmpeg.org
# Linux:   sudo apt install ffmpeg

# 3. Install yt-dlp
pip install yt-dlp

# 4. Run
python main.py
```

## Features

### Watermark Removal
Two detection modes:

**Auto Mode (YOLOv8)**
- Automatic watermark detection using object detection
- OpenCV fallback for edge cases
- One-click operation

**Manual Mode (SAM2)**
- Click on watermark for pixel-perfect segmentation
- SAM2 tracks the mask across all frames
- Scene-cut aware re-initialization

**Inpainting (ProPainter)**
- Temporal-consistent video inpainting
- No flickering between frames
- Configurable quality presets (4GB–12GB VRAM)

### Video Input
- **URL**: YouTube, TikTok, Instagram, 1000+ platforms via yt-dlp
- **Local file**: Drag & drop or browse

## AI Models

Models auto-download on first use to `%APPDATA%/Anz-Creator/models/`.

| Model | Options | Default |
|-------|---------|---------|
| YOLOv8 | nano (6MB), small (22MB), **medium (52MB)**, xlarge (131MB) | medium |
| SAM2 | tiny (38MB), small (46MB), **base+ (81MB)**, large (224MB) | base+ |
| ProPainter | lightweight (4GB), **standard (6GB)**, high (8GB), ultra (12GB) | standard |

## Project Structure

```
Anz-Creator/
├── main.py                  # Entry point
├── config.yaml              # Global configuration
├── ui/
│   ├── main_window.py       # Shell + sidebar navigation
│   ├── feature_panel.py     # Feature panels (watermark, settings)
│   └── components/          # Reusable widgets
├── core/
│   ├── task_queue.py        # QThreadPool background tasks
│   ├── model_manager.py     # Auto-download + model cache
│   ├── downloader.py        # yt-dlp wrapper
│   ├── video_io.py          # Video metadata + frame I/O
│   └── settings.py          # Persistent settings
├── features/
│   └── watermark_removal/
│       ├── detector.py      # YOLOv8 + OpenCV auto detection
│       ├── sam2_segmentor.py # SAM2 manual segmentation
│       └── inpainter.py     # ProPainter inpainting
├── utils/
│   ├── ffmpeg_wrapper.py    # Frame extract + video rebuild
│   ├── scene_detector.py    # PySceneDetect wrapper
│   └── logger.py            # Logging
└── models/                  # Auto-downloaded AI models
```

## Build Windows Installer

```bash
pip install pyinstaller
pyinstaller anz_creator.spec
```

Output in `dist/Anz-Creator/`.

## Tech Stack

- **UI**: PyQt6 + qt-material (dark_teal)
- **Download**: yt-dlp
- **Video I/O**: FFmpeg
- **Detection**: Ultralytics YOLOv8 + OpenCV
- **Segmentation**: SAM2 (Meta AI)
- **Inpainting**: ProPainter (PyTorch)
- **Threading**: QThreadPool
- **Config**: PyYAML

## Architecture

Plugin-based: each feature is a standalone module in `features/`. Core engine provides shared services (threading, model management, download) without knowing feature implementation details. New features follow the same folder pattern.
