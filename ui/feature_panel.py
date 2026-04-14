"""
Feature Panel — container widget for each feature's UI.
Currently: Watermark Removal panel with auto/manual mode tabs.
"""

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.downloader import Downloader, VideoMeta
from core.model_manager import ModelManager
from core.settings import Settings
from core.task_queue import TaskQueue, Worker
from core.video_io import VideoInfo, get_video_info
from features.watermark_removal import WatermarkRemovalPipeline
from ui.components import (
    ClickableFrame,
    FileDropZone,
    ModelDownloadDialog,
    ProgressPanel,
    SectionHeader,
    VideoPreview,
)
from utils.logger import log


class WatermarkRemovalPanel(QWidget):
    """Full UI panel for the Watermark Removal feature."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = Settings()
        self.model_mgr = ModelManager()
        self.task_queue = TaskQueue()
        self._current_worker: Optional[Worker] = None
        self._video_path: str = ""
        self._video_info: Optional[VideoInfo] = None
        self._video_meta: Optional[VideoMeta] = None
        self._output_path: str = ""  # FIX: Initialize _output_path

        self._build_ui()

    # ── Build UI ─────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(12)
        scroll.setWidget(container)
        root.addWidget(scroll)

        # ── Section: Input ───────────────────────────────
        layout.addWidget(SectionHeader("📥  Video Input"))

        input_tabs = QTabWidget()
        input_tabs.setMaximumHeight(260)

        # Tab 1: URL
        url_tab = QWidget()
        url_lay = QVBoxLayout(url_tab)
        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste video URL (YouTube, TikTok, Instagram, …)")
        self.url_input.setMinimumHeight(36)
        url_row.addWidget(self.url_input)
        self.fetch_btn = QPushButton("Fetch Info")
        self.fetch_btn.setFixedWidth(100)
        self.fetch_btn.clicked.connect(self._on_fetch_url)
        url_row.addWidget(self.fetch_btn)
        url_lay.addLayout(url_row)

        # Metadata row
        meta_row = QHBoxLayout()
        self.meta_label = QLabel("Paste a URL and click Fetch Info")
        self.meta_label.setStyleSheet("color: #888; font-size: 12px;")
        self.meta_label.setWordWrap(True)
        meta_row.addWidget(self.meta_label, 1)

        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["1080p", "720p", "480p"])
        self.quality_combo.setFixedWidth(100)
        self.quality_combo.setEnabled(False)
        meta_row.addWidget(self.quality_combo)

        self.download_btn = QPushButton("Download")
        self.download_btn.setFixedWidth(100)
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self._on_download_url)
        meta_row.addWidget(self.download_btn)
        url_lay.addLayout(meta_row)

        input_tabs.addTab(url_tab, "🌐  URL")

        # Tab 2: Local file
        file_tab = QWidget()
        file_lay = QVBoxLayout(file_tab)
        self.drop_zone = FileDropZone()
        self.drop_zone.file_dropped.connect(self._on_local_file)
        file_lay.addWidget(self.drop_zone)
        input_tabs.addTab(file_tab, "💾  Local File")

        layout.addWidget(input_tabs)

        # ── Video info bar ───────────────────────────────
        self.info_bar = QLabel("")
        self.info_bar.setStyleSheet(
            "background: #263238; border-radius: 6px; padding: 8px; "
            "font-size: 12px; color: #b0bec5;"
        )
        self.info_bar.setWordWrap(True)
        self.info_bar.hide()
        layout.addWidget(self.info_bar)

        # ── Section: Detection Mode ──────────────────────
        layout.addWidget(SectionHeader("🎯  Detection Mode"))

        mode_tabs = QTabWidget()

        # Auto mode tab
        auto_tab = QWidget()
        auto_lay = QVBoxLayout(auto_tab)
        auto_lay.addWidget(QLabel(
            "YOLOv8 automatically detects watermark position.\n"
            "Falls back to OpenCV analysis if confidence is low."
        ))
        self.auto_preview = VideoPreview(min_h=180)
        auto_lay.addWidget(self.auto_preview)

        auto_btn_row = QHBoxLayout()
        self.auto_detect_btn = QPushButton("▶  Auto Detect & Remove")
        self.auto_detect_btn.setMinimumHeight(40)
        self.auto_detect_btn.setEnabled(False)
        self.auto_detect_btn.setStyleSheet(
            "QPushButton { font-size: 14px; font-weight: bold; }"
        )
        self.auto_detect_btn.clicked.connect(self._on_auto_run)
        auto_btn_row.addWidget(self.auto_detect_btn)
        auto_lay.addLayout(auto_btn_row)
        mode_tabs.addTab(auto_tab, "🤖  Auto (YOLOv8)")

        # Manual mode tab
        manual_tab = QWidget()
        manual_lay = QVBoxLayout(manual_tab)
        manual_lay.addWidget(QLabel(
            "Click on the watermark in the frame below.\n"
            "SAM2 will segment it with pixel-perfect accuracy and track across all frames."
        ))
        self.click_frame = ClickableFrame()
        self.click_frame.setMinimumHeight(240)
        self.click_frame.point_added.connect(self._on_point_added)
        manual_lay.addWidget(self.click_frame)

        manual_btn_row = QHBoxLayout()
        self.clear_pts_btn = QPushButton("Clear Points")
        self.clear_pts_btn.clicked.connect(self.click_frame.clear_points)
        manual_btn_row.addWidget(self.clear_pts_btn)

        self.points_label = QLabel("Points: 0")
        self.points_label.setStyleSheet("color: #80cbc4;")
        manual_btn_row.addWidget(self.points_label)

        manual_btn_row.addStretch()

        self.manual_run_btn = QPushButton("▶  Segment & Remove")
        self.manual_run_btn.setMinimumHeight(40)
        self.manual_run_btn.setEnabled(False)
        self.manual_run_btn.setStyleSheet(
            "QPushButton { font-size: 14px; font-weight: bold; }"
        )
        self.manual_run_btn.clicked.connect(self._on_manual_run)
        manual_btn_row.addWidget(self.manual_run_btn)
        manual_lay.addLayout(manual_btn_row)
        mode_tabs.addTab(manual_tab, "🖱️  Manual (SAM2)")

        layout.addWidget(mode_tabs)

        # ── Section: Progress ────────────────────────────
        layout.addWidget(SectionHeader("📊  Progress"))
        self.progress = ProgressPanel()
        layout.addWidget(self.progress)

        # Cancel button
        cancel_row = QHBoxLayout()
        cancel_row.addStretch()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedWidth(100)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel)
        cancel_row.addWidget(self.cancel_btn)
        layout.addLayout(cancel_row)

        # ── Section: Output ──────────────────────────────
        layout.addWidget(SectionHeader("📤  Output"))
        self.output_label = QLabel("No output yet.")
        self.output_label.setStyleSheet("color: #888; font-size: 12px;")
        self.output_label.setWordWrap(True)
        layout.addWidget(self.output_label)

        out_btn_row = QHBoxLayout()
        self.open_output_btn = QPushButton("Open Output Folder")
        self.open_output_btn.setEnabled(False)
        self.open_output_btn.clicked.connect(self._open_output_folder)
        out_btn_row.addWidget(self.open_output_btn)
        out_btn_row.addStretch()
        layout.addLayout(out_btn_row)

        layout.addStretch()

    # ── URL handlers ─────────────────────────────────────
    def _on_fetch_url(self):
        url = self.url_input.text().strip()
        if not url:
            return
        self.fetch_btn.setEnabled(False)
        self.meta_label.setText("Preparing yt-dlp… (may download on first use)")

        def _fetch(progress_callback=None, cancel_flag=None):
            return Downloader.fetch_metadata(url)

        worker = Worker(_fetch)
        worker.signals.finished.connect(self._on_meta_ready)
        worker.signals.error.connect(lambda e: self._on_meta_error(e))
        self.task_queue.submit(worker)

    def _on_meta_ready(self, meta: VideoMeta):
        self._video_meta = meta
        self.fetch_btn.setEnabled(True)
        self.quality_combo.clear()
        self.quality_combo.addItems(meta.available_qualities or ["1080p"])
        self.quality_combo.setEnabled(True)
        self.download_btn.setEnabled(True)

        dur = f"{meta.duration // 60}:{meta.duration % 60:02d}" if meta.duration else "?"
        self.meta_label.setText(
            f"<b>{meta.title}</b><br>"
            f"Platform: {meta.platform}  •  Duration: {dur}"
        )

    def _on_meta_error(self, err: str):
        self.fetch_btn.setEnabled(True)
        self.meta_label.setText(f"<span style='color:#ef5350'>Error: {err}</span>")

    def _on_download_url(self):
        if not self._video_meta:
            return
        self.download_btn.setEnabled(False)
        self.progress.update_progress(0, "Starting download…")
        quality = self.quality_combo.currentText()

        def _dl(progress_callback=None, cancel_flag=None):
            return Downloader.download(
                self._video_meta.url, "temp",
                quality=quality,
                progress_callback=progress_callback,
                cancel_flag=cancel_flag,
            )

        worker = Worker(_dl)
        worker.signals.progress.connect(self.progress.update_progress)
        worker.signals.finished.connect(self._on_video_ready)
        worker.signals.error.connect(lambda e: self._show_error("Download failed", e))
        self._current_worker = worker
        self.cancel_btn.setEnabled(True)
        self.task_queue.submit(worker)

    # ── Local file handler ───────────────────────────────
    def _on_local_file(self, path: str):
        self._load_video_async(path)

    def _on_video_ready(self, path: str):
        if path:
            self._load_video_async(path)
        self.download_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def _load_video_async(self, path: str):
        """Load video in background thread to prevent UI freeze/crash."""
        if not os.path.isfile(path):
            self._show_error("File not found", f"Cannot find: {path}")
            return

        self.progress.update_progress(0, "Loading video…")
        self.cancel_btn.setEnabled(True)

        def _do_load(progress_callback=None, cancel_flag=None):
            import subprocess
            import traceback

            import numpy as np

            log.info("Loading video: %s", path)

            if progress_callback:
                progress_callback(10, "Reading video info…")

            # Step 1: Get video info (this is fast, just header read)
            try:
                info = get_video_info(path)
            except Exception as exc:
                log.error("get_video_info failed: %s", exc)
                raise RuntimeError(f"Cannot read video info: {exc}")

            if cancel_flag and cancel_flag():
                return None

            if progress_callback:
                progress_callback(30, "Extracting first frame…")

            # Step 2: Try to extract first frame
            frame = None

            # 2a: Try FFmpeg (only if already available, do NOT auto-download here)
            try:
                import shutil

                from core.video_io import _app_bin_dir

                ffmpeg_bin = shutil.which("ffmpeg")
                if not ffmpeg_bin:
                    app_bin = _app_bin_dir()
                    candidate = os.path.join(app_bin, "ffmpeg.exe")
                    if os.path.isfile(candidate):
                        ffmpeg_bin = candidate

                if ffmpeg_bin:
                    cmd = [
                        ffmpeg_bin, "-y",
                        "-i", path,
                        "-vframes", "1",
                        "-f", "image2pipe",
                        "-pix_fmt", "rgb24",
                        "-vcodec", "rawvideo",
                        "-loglevel", "error",
                        "-",
                    ]
                    si = None
                    cf = 0
                    if os.name == "nt":
                        si = subprocess.STARTUPINFO()
                        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        si.wShowWindow = 0
                        cf = subprocess.CREATE_NO_WINDOW

                    proc = subprocess.run(
                        cmd, capture_output=True, timeout=30,
                        startupinfo=si, creationflags=cf,
                    )
                    if proc.returncode == 0 and len(proc.stdout) > 0:
                        raw = np.frombuffer(proc.stdout, dtype=np.uint8)
                        expected = info.width * info.height * 3
                        if expected > 0 and len(raw) >= expected:
                            frame = raw[:expected].reshape(
                                (info.height, info.width, 3)
                            )
                            log.info("Frame extracted via FFmpeg.")
                        else:
                            log.warning(
                                "FFmpeg size mismatch: got %d, expected %d",
                                len(raw), expected,
                            )
                    else:
                        stderr_msg = ""
                        if proc.stderr:
                            stderr_msg = proc.stderr.decode(
                                "utf-8", errors="replace"
                            )[:200]
                        log.warning(
                            "FFmpeg exit %d: %s", proc.returncode, stderr_msg
                        )
                else:
                    log.info("FFmpeg not available yet, trying OpenCV…")
            except subprocess.TimeoutExpired:
                log.warning("FFmpeg timed out.")
            except Exception as exc:
                log.warning("FFmpeg failed: %s", exc)

            if cancel_flag and cancel_flag():
                return None

            # 2b: Fallback to OpenCV (in a separate try block)
            if frame is None:
                try:
                    import cv2

                    log.info("Trying OpenCV frame read…")
                    cap = cv2.VideoCapture(path)
                    if cap.isOpened():
                        ret, bgr = cap.read()
                        cap.release()
                        if ret and bgr is not None:
                            h, w = bgr.shape[:2]
                            if info.width <= 0 or info.height <= 0:
                                info.width = w
                                info.height = h
                            ch = bgr.shape[2] if bgr.ndim == 3 else 1
                            if ch == 4:
                                frame = cv2.cvtColor(bgr, cv2.COLOR_BGRA2RGB)
                            elif ch == 3:
                                frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                            else:
                                frame = cv2.cvtColor(bgr, cv2.COLOR_GRAY2RGB)
                            log.info("Frame extracted via OpenCV (%dx%d).", w, h)
                        else:
                            log.warning("OpenCV read() returned empty.")
                    else:
                        log.warning("OpenCV cannot open: %s", path)
                except Exception as exc:
                    log.warning("OpenCV failed: %s\n%s", exc, traceback.format_exc())

            # 2c: Placeholder if everything failed
            if frame is None:
                pw = max(info.width, 640)
                ph = max(info.height, 480)
                frame = np.zeros((ph, pw, 3), dtype=np.uint8)
                # Simple gray text
                try:
                    import cv2

                    cv2.putText(
                        frame, "Preview not available",
                        (pw // 10, ph // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, (100, 100, 100), 2,
                    )
                except Exception:
                    pass
                log.warning("Using placeholder frame.")

            if progress_callback:
                progress_callback(90, "Preparing preview…")

            rgb = np.ascontiguousarray(frame)
            h, w = rgb.shape[:2]

            if progress_callback:
                progress_callback(100, "Video loaded.")

            log.info("Video ready: %dx%d", w, h)
            return {"path": path, "info": info, "rgb": rgb, "w": w, "h": h}

        def _on_loaded(result):
            self.cancel_btn.setEnabled(False)
            if result is None:
                self.progress.reset()
                return
            try:
                from PyQt6.QtGui import QImage, QPixmap

                self._video_path = result["path"]
                self._video_info = result["info"]
                info = result["info"]

                self.info_bar.setText(
                    f"<b>{os.path.basename(result['path'])}</b>  •  "
                    f"{info.width}×{info.height}  •  {info.fps:.1f} fps  •  "
                    f"{info.frame_count} frames  •  {info.duration:.1f}s"
                )
                self.info_bar.show()

                rgb = result["rgb"]
                w, h = result["w"], result["h"]

                # Create QImage → QPixmap, then release numpy ref
                qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
                pixmap = QPixmap.fromImage(qimg.copy())
                # After .copy(), pixmap owns its own pixel data — safe to drop rgb
                del qimg

                if pixmap.isNull():
                    log.warning("Created pixmap is null, skipping display.")
                    self.progress.reset()
                    return

                # Each widget gets its OWN copy of the pixmap
