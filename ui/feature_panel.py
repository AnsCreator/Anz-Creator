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
    QProgressBar,
    QPushButton,
    QRadioButton,
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
        self._output_path: str = ""

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
        self.url_input.setPlaceholderText(
            "Paste video URL (YouTube, TikTok, Instagram, …)"
        )
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
        self.auto_preview = VideoPreview(min_h=180, max_h=360)
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
            "SAM2 will segment it with pixel-perfect accuracy "
            "and track across all frames."
        ))
        self.click_frame = ClickableFrame(min_h=240, max_h=400)
        self.click_frame.point_added.connect(self._on_point_added)
        manual_lay.addWidget(self.click_frame)

        manual_btn_row = QHBoxLayout()
        self.clear_pts_btn = QPushButton("Clear Points")
        self.clear_pts_btn.clicked.connect(self._on_clear_points)
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

    def _on_clear_points(self):
        self.click_frame.clear_points()
        self.points_label.setText("Points: 0")

    # ── URL handlers ─────────────────────────────────────
    def _on_fetch_url(self):
        url = self.url_input.text().strip()
        if not url:
            return
        self.fetch_btn.setEnabled(False)
        self.meta_label.setText(
            "Preparing yt-dlp… (may download on first use)"
        )

        def _fetch(progress_callback=None, cancel_flag=None):
            return Downloader.fetch_metadata(url)

        worker = Worker(_fetch)
        worker.signals.finished.connect(self._on_meta_ready)
        worker.signals.error.connect(self._on_meta_error)
        self.task_queue.submit(worker)

    def _on_meta_ready(self, meta: VideoMeta):
        self._video_meta = meta
        self.fetch_btn.setEnabled(True)
        self.quality_combo.clear()
        self.quality_combo.addItems(meta.available_qualities or ["1080p"])
        self.quality_combo.setEnabled(True)
        self.download_btn.setEnabled(True)

        dur = (
            f"{meta.duration // 60}:{meta.duration % 60:02d}"
            if meta.duration else "?"
        )
        self.meta_label.setText(
            f"<b>{meta.title}</b><br>"
            f"Platform: {meta.platform}  •  Duration: {dur}"
        )

    def _on_meta_error(self, err: str):
        self.fetch_btn.setEnabled(True)
        self.meta_label.setText(
            f"<span style='color:#ef5350'>Error: {err}</span>"
        )

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
        worker.signals.error.connect(
            lambda e: self._show_error("Download failed", e)
        )
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
        """Load video in background thread to prevent UI freeze."""
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

            # Step 1: Get video info
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

            # 2a: Try FFmpeg
            try:
                import shutil

                from core.video_io import _app_bin_dir

                ffmpeg_bin = shutil.which("ffmpeg")
                if not ffmpeg_bin:
                    app_bin = _app_bin_dir()
                    candidate = os.path.join(
                        app_bin,
                        "ffmpeg.exe" if os.name == "nt" else "ffmpeg",
                    )
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
                        cf = getattr(subprocess, "CREATE_NO_WINDOW", 0)

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
            except Exception as exc:
                log.warning("FFmpeg frame extract failed: %s", exc)

            if cancel_flag and cancel_flag():
                return None

            # 2b: Fallback to OpenCV
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
                                frame = cv2.cvtColor(
                                    bgr, cv2.COLOR_BGRA2RGB,
                                )
                            elif ch == 3:
                                frame = cv2.cvtColor(
                                    bgr, cv2.COLOR_BGR2RGB,
                                )
                            else:
                                frame = cv2.cvtColor(
                                    bgr, cv2.COLOR_GRAY2RGB,
                                )
                            log.info(
                                "Frame extracted via OpenCV (%dx%d).", w, h,
                            )
                    else:
                        cap.release()
                except Exception as exc:
                    log.warning(
                        "OpenCV failed: %s\n%s",
                        exc, traceback.format_exc(),
                    )

            # 2c: Placeholder if everything failed
            if frame is None:
                pw = max(info.width, 640)
                ph = max(info.height, 480)
                frame = np.zeros((ph, pw, 3), dtype=np.uint8)
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
                    f"{info.width}×{info.height}  •  "
                    f"{info.fps:.1f} fps  •  "
                    f"{info.frame_count} frames  •  "
                    f"{info.duration:.1f}s"
                )
                self.info_bar.show()

                rgb = result["rgb"]
                w, h = result["w"], result["h"]

                if not rgb.flags["C_CONTIGUOUS"]:
                    import numpy as np
                    rgb = np.ascontiguousarray(rgb)

                bytes_per_line = w * 3
                qimg = QImage(
                    rgb.data, w, h, bytes_per_line,
                    QImage.Format.Format_RGB888,
                )
                pixmap = QPixmap.fromImage(qimg.copy())
                del qimg

                if pixmap.isNull():
                    log.warning(
                        "Created pixmap is null, skipping display."
                    )
                    self.progress.reset()
                    return

                self.click_frame.set_original_size(w, h)
                self.click_frame.reset_points()

                self.auto_preview.set_pixmap_direct(QPixmap(pixmap))
                self.click_frame.set_pixmap_direct(QPixmap(pixmap))

                self.points_label.setText("Points: 0")
                self.auto_detect_btn.setEnabled(True)
                self.manual_run_btn.setEnabled(True)
                self.progress.reset()
                log.info("Video displayed: %s", result["path"])

            except Exception as exc:
                import traceback
                log.error(
                    "Display failed: %s\n%s",
                    exc, traceback.format_exc(),
                )
                self._show_error("Display Error", str(exc))

        def _on_load_error(err):
            self.cancel_btn.setEnabled(False)
            self.progress.reset()
            self._show_error("Cannot open video", err)

        worker = Worker(_do_load)
        worker.signals.finished.connect(_on_loaded)
        worker.signals.error.connect(_on_load_error)
        self._current_worker = worker
        self.task_queue.submit(worker)

    # ── Point tracking ───────────────────────────────────
    def _on_point_added(self, x: int, y: int):
        n = len(self.click_frame.points)
        self.points_label.setText(f"Points: {n}")

    # ── Auto run ─────────────────────────────────────────
    def _on_auto_run(self):
        if not self._video_path:
            return
        self._run_pipeline("auto")

    # ── Manual run ───────────────────────────────────────
    def _on_manual_run(self):
        if not self._video_path:
            return
        pts = self.click_frame.points
        if not pts:
            QMessageBox.warning(
                self, "No Points", "Click on the watermark first."
            )
            return
        self._run_pipeline("manual", click_points=pts)

    # ── Pipeline runner ──────────────────────────────────
    def _run_pipeline(self, mode: str, click_points=None):
        # Import pipeline lazily — it pulls in torch which can be heavy
        # and may not be installed in test-only environments.
        try:
            from features.watermark_removal import WatermarkRemovalPipeline
        except ImportError as exc:
            self._show_error(
                "Missing Dependencies",
                f"Watermark removal requires PyTorch + OpenCV:\n{exc}",
            )
            return

        settings = self.settings
        yolo_var = settings.get("models.yolov8")
        sam2_var = settings.get("models.sam2")
        pp_mode = settings.get("models.propainter") or "standard"

        yolo_path = self.model_mgr.model_path("yolov8", yolo_var)
        sam2_path = self.model_mgr.model_path("sam2", sam2_var)
        pp_dir = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")),
            "Anz-Creator", "models", "propainter",
        )

        from core.video_io import is_ffmpeg_installed
        if not is_ffmpeg_installed():
            QMessageBox.warning(
                self, "FFmpeg Required",
                "FFmpeg is required to process videos.\n"
                "Please go to the Settings tab and download FFmpeg first."
            )
            return

        missing = []
        if mode == "auto" and not os.path.isfile(yolo_path):
            missing.append(("yolov8", yolo_var))
        if mode == "manual" and not os.path.isfile(sam2_path):
            missing.append(("sam2", sam2_var))
        # ProPainter is needed for both modes
        if not self.model_mgr.is_downloaded("propainter", pp_mode):
            missing.append(("propainter", pp_mode))

        if missing:
            model_list = "\n".join(
                f"  • {f}/{v}" for f, v in missing
            )
            reply = QMessageBox.question(
                self, "Models Required",
                f"Required model(s) not found:\n{model_list}\n\n"
                "Download now?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._download_models(
                    missing,
                    lambda: self._run_pipeline(mode, click_points),
                )
            return

        # For manual mode, also verify SAM2 Python package is installed
        if mode == "manual":
            status, details = self._check_sam2_package()
            if status == "missing":
                reply = QMessageBox.question(
                    self, "SAM2 Package Required",
                    "SAM2 Python package is not installed.\n\n"
                    "SAM2 must be installed from GitHub:\n"
                    "  pip install git+https://github.com/facebookresearch/sam2.git\n\n"
                    "Run the installer now? (Requires Git + PyTorch)",
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._install_sam2_package()
                return
            elif status == "restart_required":
                QMessageBox.warning(
                    self, "Restart Required",
                    "SAM2 was installed in a previous step but is not "
                    "visible to the running application.\n\n"
                    "Please CLOSE and REOPEN Anz-Creator to use Manual mode.",
                )
                return
            elif status == "broken":
                self._show_error(
                    "SAM2 Package Error",
                    f"SAM2 is installed but failed to import:\n\n{details}\n\n"
                    "This usually means a missing dependency "
                    "(PyTorch or CUDA toolkit). "
                    "Try reinstalling PyTorch that matches your CUDA version.",
                )
                return

        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        base = os.path.splitext(
            os.path.basename(self._video_path)
        )[0]
        output_path = os.path.join(
            output_dir, f"{base}_no_watermark.mp4",
        )

        pipeline = WatermarkRemovalPipeline(
            yolo_model_path=yolo_path,
            sam2_model_path=sam2_path,
            propainter_model_dir=pp_dir,
            propainter_mode=pp_mode,
            temp_dir="temp",
        )

        self.auto_detect_btn.setEnabled(False)
        self.manual_run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.reset()

        _mode = mode
        _click_points = click_points

        def _work(progress_callback=None, cancel_flag=None):
            if _mode == "auto":
                return pipeline.run_auto(
                    self._video_path, output_path,
                    progress_callback=progress_callback,
                    cancel_flag=cancel_flag,
                )
            else:
                return pipeline.run_manual(
                    self._video_path, output_path,
                    click_points=_click_points,
                    progress_callback=progress_callback,
                    cancel_flag=cancel_flag,
                )

        worker = Worker(_work)
        worker.signals.progress.connect(self.progress.update_progress)
        worker.signals.finished.connect(self._on_pipeline_done)
        worker.signals.error.connect(self._on_pipeline_error)
        self._current_worker = worker
        self.task_queue.submit(worker)

    def _on_pipeline_done(self, result):
        self.auto_detect_btn.setEnabled(True)
        self.manual_run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        if result:
            self.output_label.setText(
                f"<span style='color:#66bb6a'>✓ Output saved:</span> "
                f"{result}"
            )
            self.open_output_btn.setEnabled(True)
            self._output_path = result
        else:
            self.output_label.setText("Pipeline cancelled or failed.")

    def _on_pipeline_error(self, err):
        self.auto_detect_btn.setEnabled(True)
        self.manual_run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._show_error("Pipeline Error", err)

    def _download_models(self, models: list[tuple[str, str]], on_done=None):
        dlg = ModelDownloadDialog(self, title="Downloading Models")
        dlg.show()

        def _dl(progress_callback=None, cancel_flag=None):
            for fam, var in models:
                self.model_mgr.download(
                    fam, var,
                    progress_callback=progress_callback,
                    cancel_flag=cancel_flag,
                )
            return True

        def _on_finished(_result):
            dlg.close()
            if on_done:
                on_done()

        def _on_error(e):
            dlg.close()
            self._show_error("Download Error", str(e))

        worker = Worker(_dl)
        worker.signals.progress.connect(dlg.update)
        worker.signals.finished.connect(_on_finished)
        worker.signals.error.connect(_on_error)
        dlg.cancel_btn.clicked.connect(worker.cancel)
        self.task_queue.submit(worker)

    def _check_sam2_package(self):
        """
        Diagnose SAM2 package state.

        Returns a tuple (status, details):
            ("ok", "")              — usable
            ("missing", "")         — package not installed at all
            ("broken", "<error>")   — installed but fails to import due to
                                      a broken dependency (e.g. missing torch)
            ("restart_required", "") — dist-info present in site-packages but
                                       not importable yet (install happened
                                       in this session without restart)
        """
        import importlib
        import sys

        # First, clear stale failed-import cache (e.g. after running
        # _install_sam2_package during this session).
        try:
            importlib.invalidate_caches()
            for mod_name in list(sys.modules.keys()):
                if (
                    (mod_name == "sam2" or mod_name.startswith("sam2."))
                    and sys.modules[mod_name] is None
                ):
                    # Only drop negative-cache entries; keep successful imports
                    sys.modules.pop(mod_name, None)
        except Exception:
            pass

        try:
            import sam2.build_sam  # noqa: F401
            return ("ok", "")
        except ImportError as exc:
            msg = str(exc)
        except Exception as exc:
            # Some other error (e.g. torch ImportError during sam2 __init__)
            return ("broken", str(exc))

        # Not importable. Is it installed at all? Check dist-info.
        try:
            import importlib.metadata as md
        except ImportError:
            # Python <3.8 fallback (should not happen on supported versions)
            try:
                import importlib_metadata as md  # type: ignore[import-not-found]
            except ImportError:
                return ("missing", msg)

        try:
            md.distribution("SAM-2")
            return ("restart_required", msg)
        except md.PackageNotFoundError:
            pass

        # Try common alternate distribution names
        for name in ("sam2", "segment-anything-2"):
            try:
                md.distribution(name)
                return ("restart_required", msg)
            except md.PackageNotFoundError:
                continue

        return ("missing", msg)

    def _install_sam2_package(self):
        """Install SAM2 Python package from GitHub via pip subprocess."""
        import subprocess
        import sys

        # Prevent double-click / re-entry
        if getattr(self, "_sam2_install_in_progress", False):
            log.info("SAM2 install already in progress — ignoring duplicate request.")
            return
        self._sam2_install_in_progress = True

        dlg = ModelDownloadDialog(self, title="Installing SAM2 Package")
        dlg.update(
            0,
            "Downloading and installing SAM2 from PyPI "
            "(typically 1-3 minutes)…",
        )
        dlg.show()

        def _install(progress_callback=None, cancel_flag=None):
            # Stage-based heuristic progress. SAM2 install has 3 phases:
            # (1) Clone repo, (2) Collect deps, (3) Build/install. We map pip
            # output keywords to a coarse percentage so the user sees movement.
            stage_keywords = [
                ("Cloning into", 5, "Cloning SAM2 repository…"),
                ("Collecting sam", 15, "Preparing SAM2…"),
                ("Collecting ", 25, "Collecting dependencies…"),
                ("Downloading ", 35, "Downloading dependencies…"),
                ("Installing build dependencies", 45, "Installing build deps…"),
                ("Getting requirements", 50, "Resolving requirements…"),
                ("Preparing metadata", 55, "Preparing metadata…"),
                ("Building wheel", 65, "Building SAM2 (may take several minutes)…"),
                ("Building wheels", 65, "Building SAM2 (may take several minutes)…"),
                ("Successfully built", 80, "Build complete. Installing…"),
                ("Installing collected packages", 85, "Installing SAM2…"),
                ("Successfully installed", 95, "Install complete."),
            ]

            if progress_callback:
                progress_callback(2, "Starting pip install…")

            # Prefer PyPI wheel: fast, no git clone, no C++ compile needed.
            # (facebookresearch publishes the `sam2` package to PyPI.)
            # Set SAM2_BUILD_CUDA=0 so the install does not try to build the
            # optional CUDA post-processing extension — that compile step
            # needs the CUDA Toolkit + MSVC Build Tools and is what made
            # earlier attempts appear to hang for 10+ minutes. The post-
            # processing step is optional and disabling it does not affect
            # results for our watermark-removal use case.
            env = os.environ.copy()
            env["SAM2_BUILD_CUDA"] = "0"
            env["SAM2_BUILD_ALLOW_ERRORS"] = "1"

            cmd = [
                sys.executable, "-m", "pip", "install",
                "--no-build-isolation",
                "--progress-bar", "off",
                "--verbose",  # Verbose so we get useful stage hints in stdout
                "sam2",  # from PyPI
            ]

            # Hide console window on Windows via STARTUPINFO.
            creationflags = 0
            startupinfo = None
            if os.name == "nt":
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                if hasattr(subprocess, "STARTUPINFO"):
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= getattr(
                        subprocess, "STARTF_USESHOWWINDOW", 1
                    )
                    startupinfo.wShowWindow = 0  # SW_HIDE

            # Stream stdout line-by-line so the user sees progress in real time,
            # and so we can cancel mid-flight. pip writes to stderr too but
            # merging with stdout keeps things simple.
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,  # line-buffered
                creationflags=creationflags,
                startupinfo=startupinfo,
                env=env,
                # CREATE_NEW_PROCESS_GROUP lets us terminate pip cleanly.
                **(
                    {"start_new_session": True}
                    if os.name != "nt"
                    else {}
                ),
            )

            current_pct = 2
            collected_output: list[str] = []

            try:
                assert proc.stdout is not None
                for line in proc.stdout:
                    if cancel_flag and cancel_flag():
                        log.info("SAM2 install cancelled by user.")
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                        raise RuntimeError("Cancelled")

                    stripped = line.rstrip()
                    if stripped:
                        collected_output.append(stripped)
                        # Keep the tail bounded so we don't eat memory on long
                        # verbose runs.
                        if len(collected_output) > 400:
                            del collected_output[:100]

                    # Update progress if the line matches a known stage
                    for key, pct, label in stage_keywords:
                        if key in stripped and pct > current_pct:
                            current_pct = pct
                            if progress_callback:
                                progress_callback(pct, label)
                            break
            finally:
                try:
                    proc.stdout.close()
                except Exception:
                    pass

            returncode = proc.wait()

            if returncode != 0:
                tail = "\n".join(collected_output[-30:])
                raise RuntimeError(
                    f"pip install failed (exit {returncode}):\n{tail}"
                )

            if progress_callback:
                progress_callback(96, "Verifying install…")

            # Try to make the newly installed package visible to the running
            # interpreter without a restart.
            try:
                import importlib
                import site

                try:
                    importlib.reload(site)
                except Exception:
                    pass
                importlib.invalidate_caches()
                # Drop any cached failed imports from previous attempts
                for mod_name in list(sys.modules.keys()):
                    if mod_name == "sam2" or mod_name.startswith("sam2."):
                        sys.modules.pop(mod_name, None)
            except Exception as exc:
                log.warning("Cache invalidation warning: %s", exc)

            # Verify it actually imports
            try:
                import sam2.build_sam  # noqa: F401
                available_in_session = True
            except ImportError as exc:
                log.warning(
                    "SAM2 installed but not importable in this session: %s", exc
                )
                available_in_session = False

            if progress_callback:
                progress_callback(100, "SAM2 installed.")
            return available_in_session

        def _on_finished(result):
            dlg.close()
            self._sam2_install_in_progress = False
            if result:
                QMessageBox.information(
                    self, "SAM2 Installed",
                    "SAM2 Python package installed successfully.\n"
                    "You can now use Manual mode.",
                )
            else:
                # Install succeeded but import still fails — restart required.
                QMessageBox.warning(
                    self, "Restart Required",
                    "SAM2 package installed successfully, but the running "
                    "application cannot see it yet.\n\n"
                    "Please CLOSE and REOPEN Anz-Creator to use Manual mode.",
                )

        def _on_error(e):
            dlg.close()
            self._sam2_install_in_progress = False
            self._show_error(
                "SAM2 Install Failed",
                f"{e}\n\nPlease install manually from a terminal:\n"
                "  pip install git+https://github.com/facebookresearch/sam2.git\n\n"
                "Requirements: Git and PyTorch must be installed first.",
            )

        worker = Worker(_install)
        worker.signals.progress.connect(dlg.update)
        worker.signals.finished.connect(_on_finished)
        worker.signals.error.connect(_on_error)
        dlg.cancel_btn.clicked.connect(worker.cancel)
        self.task_queue.submit(worker)

    # ── Cancel ───────────────────────────────────────────
    def _on_cancel(self):
        if self._current_worker:
            self._current_worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.progress.update_progress(0, "Cancelling…")

    # ── Output folder ────────────────────────────────────
    def _open_output_folder(self):
        path = self._output_path or "output"
        folder = (
            os.path.dirname(path) if os.path.isfile(path) else "output"
        )
        abs_folder = os.path.abspath(folder)
        if os.name == "nt":
            try:
                os.startfile(abs_folder)  # type: ignore[attr-defined]
            except OSError as exc:
                log.warning("Cannot open folder: %s", exc)
        else:
            import subprocess as sp
            try:
                sp.Popen(["xdg-open", abs_folder])
            except FileNotFoundError:
                try:
                    sp.Popen(["open", abs_folder])
                except FileNotFoundError:
                    log.warning("No file manager found to open: %s", abs_folder)

    # ── Helpers ──────────────────────────────────────────
    def _show_error(self, title: str, msg: str):
        QMessageBox.critical(self, title, str(msg))
        self.progress.update_progress(0, f"Error: {str(msg)[:80]}")


# ── Settings Panel ───────────────────────────────────────
class SettingsPanel(QWidget):
    """Application settings — model selection, manual downloads, paths."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = Settings()
        self.model_mgr = ModelManager()
        self._build_ui()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        layout.addWidget(SectionHeader("⚙️  System Dependencies"))
        layout.addWidget(self._ffmpeg_group())

        layout.addWidget(SectionHeader("🧠  AI Model Settings"))
        layout.addWidget(
            self._model_list_group("YOLOv8 (Auto Detection)", "yolov8")
        )
        layout.addWidget(
            self._model_list_group("SAM2 (Manual Segmentation)", "sam2")
        )
        layout.addWidget(
            self._model_list_group("ProPainter (Inpainting)", "propainter")
        )

        layout.addWidget(SectionHeader("📂  Paths"))
        models_dir = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")),
            "Anz-Creator", "models",
        )
        path_label = QLabel(f"Models stored in: <code>{models_dir}</code>")
        path_label.setWordWrap(True)
        path_label.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(path_label)

        layout.addStretch()

        scroll.setWidget(container)
        root_layout.addWidget(scroll)

    def _ffmpeg_group(self) -> QGroupBox:
        from core.video_io import is_ffmpeg_installed
        group = QGroupBox("FFmpeg Engine")
        group.setStyleSheet(
            "QGroupBox { font-weight: bold; padding-top: 18px; }"
        )
        lay = QVBoxLayout(group)
        lay.setSpacing(6)

        row_widget = QWidget()
        row_lay = QVBoxLayout(row_widget)
        row_lay.setContentsMargins(4, 6, 4, 6)
        row_lay.setSpacing(4)

        top_row = QHBoxLayout()

        name_lbl = QLabel("FFmpeg Essentials (≈80MB)")
        name_lbl.setStyleSheet(
            "font-size: 13px; color: #e0e0e0; font-weight: bold;"
        )
        top_row.addWidget(name_lbl)
        top_row.addStretch()

        status_lbl = QLabel("✅ Ready")
        status_lbl.setStyleSheet(
            "color: #66bb6a; font-weight: bold; font-size: 12px;"
        )

        dl_btn = QPushButton("⬇ Download")
        dl_btn.setFixedSize(110, 28)

        if is_ffmpeg_installed():
            dl_btn.hide()
            top_row.addWidget(status_lbl)
        else:
            status_lbl.hide()
            top_row.addWidget(dl_btn)

        row_lay.addLayout(top_row)

        desc_lbl = QLabel(
            "Required core dependency for video extraction, "
            "audio processing, and saving outputs."
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(
            "color: #888; font-size: 12px; margin-left: 0px;"
        )
        row_lay.addWidget(desc_lbl)

        pbar = QProgressBar()
        pbar.setRange(0, 100)
        pbar.setFixedHeight(14)
        pbar.setStyleSheet(
            "QProgressBar { margin-top: 4px; font-size: 10px; }"
        )
        pbar.hide()
        row_lay.addWidget(pbar)

        dl_btn.clicked.connect(
            lambda checked, b=dl_btn, p=pbar, s=status_lbl:
            self._start_ffmpeg_download(b, p, s)
        )

        lay.addWidget(row_widget)
        return group

    def _start_ffmpeg_download(
        self, btn: QPushButton, pbar: QProgressBar, status_lbl: QLabel,
    ):
        btn.setEnabled(False)
        pbar.setValue(0)
        pbar.show()

        from core.video_io import download_ffmpeg

        def _do_download(progress_callback=None, cancel_flag=None):
            return download_ffmpeg(
                progress_callback=progress_callback,
                cancel_flag=cancel_flag,
            )

        def _on_progress(pct, msg):
            pbar.setValue(pct)
            if "MB" in msg:
                mb_text = msg.split("…")[-1].strip()
                pbar.setFormat(f"%p%  ({mb_text})")
            else:
                pbar.setFormat("%p%")

        def _on_finished(result):
            pbar.hide()
            btn.hide()
            status_lbl.show()
            log.info("FFmpeg manual download complete.")

        def _on_error(err):
            pbar.hide()
            btn.setEnabled(True)
            QMessageBox.critical(self, "Download Error", str(err))

        worker = Worker(_do_download)
        worker.signals.progress.connect(_on_progress)
        worker.signals.finished.connect(_on_finished)
        worker.signals.error.connect(_on_error)
        TaskQueue().submit(worker)

    def _model_list_group(self, title: str, family: str) -> QGroupBox:
        group = QGroupBox(title)
        group.setStyleSheet(
            "QGroupBox { font-weight: bold; padding-top: 18px; }"
        )
        lay = QVBoxLayout(group)
        lay.setSpacing(6)

        variants = self.model_mgr.list_variants(family)
        current = self.settings.get(f"models.{family}")

        for i, v in enumerate(variants):
            row_widget = QWidget()
            row_lay = QVBoxLayout(row_widget)
            row_lay.setContentsMargins(4, 6, 4, 6)
            row_lay.setSpacing(4)

            top_row = QHBoxLayout()

            size_text = (
                f"{v['size_mb']}MB" if v.get("size_mb")
                else f"{v.get('vram_gb', 0)}GB VRAM"
            )
            radio = QRadioButton(f"{v['name']}  ({size_text})")
            radio.setStyleSheet("font-size: 13px; color: #e0e0e0;")
            radio.setMinimumHeight(24)
            radio.setChecked(v["name"] == current)

            radio.toggled.connect(
                lambda checked, f=family, n=v["name"]:
                self.settings.set(f"models.{f}", n) if checked else None
            )
            top_row.addWidget(radio)
            top_row.addStretch()

            status_lbl = QLabel("✅ Ready")
            status_lbl.setStyleSheet(
                "color: #66bb6a; font-weight: bold; font-size: 12px;"
            )

            dl_btn = QPushButton("⬇ Download")
            dl_btn.setFixedSize(110, 28)

            if v["downloaded"]:
                dl_btn.hide()
                top_row.addWidget(status_lbl)
            else:
                status_lbl.hide()
                top_row.addWidget(dl_btn)

            row_lay.addLayout(top_row)

            desc_lbl = QLabel(v["description"])
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet(
                "color: #888; font-size: 12px; margin-left: 22px;"
            )
            row_lay.addWidget(desc_lbl)

            pbar = QProgressBar()
            pbar.setRange(0, 100)
            pbar.setFixedHeight(14)
            pbar.setStyleSheet(
                "QProgressBar { margin-left: 22px; margin-top: 4px; "
                "font-size: 10px; }"
            )
            pbar.hide()
            row_lay.addWidget(pbar)

            dl_btn.clicked.connect(
                lambda checked, f=family, var=v["name"],
                b=dl_btn, p=pbar, s=status_lbl:
                self._start_manual_download(f, var, b, p, s)
            )

            lay.addWidget(row_widget)

            if i < len(variants) - 1:
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setStyleSheet("background-color: #2a2a35;")
                lay.addWidget(line)

        return group

    def _start_manual_download(
        self, family: str, variant: str,
        btn: QPushButton, pbar: QProgressBar, status_lbl: QLabel,
    ):
        btn.setEnabled(False)
        pbar.setValue(0)
        pbar.show()

        def _do_download(progress_callback=None, cancel_flag=None):
            return self.model_mgr.download(
                family, variant,
                progress_callback=progress_callback,
                cancel_flag=cancel_flag,
            )

        def _on_progress(pct, msg):
            pbar.setValue(pct)
            if "MB" in msg:
                mb_text = msg.split("…")[-1].strip()
                pbar.setFormat(f"%p%  ({mb_text})")
            else:
                pbar.setFormat("%p%")

        def _on_finished(result):
            pbar.hide()
            btn.hide()
            status_lbl.show()
            log.info("Manual download complete: %s", result)

        def _on_error(err):
            pbar.hide()
            btn.setEnabled(True)
            QMessageBox.critical(self, "Download Error", str(err))

        worker = Worker(_do_download)
        worker.signals.progress.connect(_on_progress)
        worker.signals.finished.connect(_on_finished)
        worker.signals.error.connect(_on_error)
        TaskQueue().submit(worker)
