"""
Feature Panel — container widget for each feature's UI.
Currently: Watermark Removal panel with auto/manual mode tabs.
"""

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel,
    QPushButton, QComboBox, QLineEdit, QGroupBox, QFrame,
    QMessageBox, QScrollArea,
)

from ui.components import (
    ProgressPanel, VideoPreview, ClickableFrame, FileDropZone,
    SectionHeader, ModelDownloadDialog,
)
from core.task_queue import TaskQueue, Worker
from core.downloader import Downloader, VideoMeta
from core.video_io import get_video_info, read_frame, VideoInfo
from core.settings import Settings
from core.model_manager import ModelManager
from features.watermark_removal import WatermarkRemovalPipeline
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
        self.meta_label.setText("Fetching…")

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
        self._load_video(path)

    def _on_video_ready(self, path: str):
        if path:
            self._load_video(path)
        self.download_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def _load_video(self, path: str):
        try:
            if not os.path.isfile(path):
                self._show_error("File not found", f"Cannot find: {path}")
                return

            self._video_path = path
            self._video_info = get_video_info(path)
            info = self._video_info

            self.info_bar.setText(
                f"<b>{os.path.basename(path)}</b>  •  "
                f"{info.width}×{info.height}  •  {info.fps:.1f} fps  •  "
                f"{info.frame_count} frames  •  {info.duration:.1f}s"
            )
            self.info_bar.show()

            # Show first frame in previews
            frame = read_frame(path, 0)
            self.auto_preview.set_frame(frame)
            self.click_frame.set_frame(frame)

            self.auto_detect_btn.setEnabled(True)
            self.manual_run_btn.setEnabled(True)
            self.progress.reset()
            log.info("Video loaded: %s", path)
        except Exception as exc:
            import traceback
            log.error("Failed to load video: %s\n%s", exc, traceback.format_exc())
            self._show_error("Cannot open video", str(exc))

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
            QMessageBox.warning(self, "No Points", "Click on the watermark first.")
            return
        self._run_pipeline("manual", click_points=pts)

    # ── Pipeline runner ──────────────────────────────────
    def _run_pipeline(self, mode: str, click_points=None):
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

        # Check models exist
        missing = []
        if mode == "auto" and not os.path.isfile(yolo_path):
            missing.append(("yolov8", yolo_var))
        if mode == "manual" and not os.path.isfile(sam2_path):
            missing.append(("sam2", sam2_var))

        if missing:
            model_list = "\n".join(f"  • {f}/{v}" for f, v in missing)
            reply = QMessageBox.question(
                self, "Models Required",
                f"Required model(s) not found:\n{model_list}\n\nDownload now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._download_models(missing, lambda: self._run_pipeline(mode, click_points))
            return

        output_dir = os.path.join("output")
        os.makedirs(output_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(self._video_path))[0]
        output_path = os.path.join(output_dir, f"{base}_no_watermark.mp4")

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

        def _work(progress_callback=None, cancel_flag=None):
            if mode == "auto":
                return pipeline.run_auto(
                    self._video_path, output_path,
                    progress_callback=progress_callback,
                    cancel_flag=cancel_flag,
                )
            else:
                return pipeline.run_manual(
                    self._video_path, output_path,
                    click_points=click_points,
                    progress_callback=progress_callback,
                    cancel_flag=cancel_flag,
                )

        worker = Worker(_work)
        worker.signals.progress.connect(self.progress.update_progress)
        worker.signals.finished.connect(lambda r: self._on_pipeline_done(r))
        worker.signals.error.connect(lambda e: self._on_pipeline_error(e))
        self._current_worker = worker
        self.task_queue.submit(worker)

    def _on_pipeline_done(self, result):
        self.auto_detect_btn.setEnabled(True)
        self.manual_run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        if result:
            self.output_label.setText(
                f"<span style='color:#66bb6a'>✓ Output saved:</span> {result}"
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

    # ── Download models ──────────────────────────────────
    def _download_models(self, models: list[tuple[str, str]], on_done=None):
        dlg = ModelDownloadDialog(self)
        dlg.show()

        def _dl(progress_callback=None, cancel_flag=None):
            for fam, var in models:
                self.model_mgr.download(
                    fam, var,
                    progress_callback=progress_callback,
                    cancel_flag=cancel_flag,
                )
            return True

        worker = Worker(_dl)
        worker.signals.progress.connect(dlg.update)
        worker.signals.finished.connect(lambda _: (dlg.close(), on_done() if on_done else None))
        worker.signals.error.connect(lambda e: (dlg.close(), self._show_error("Download Error", e)))
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
        path = getattr(self, "_output_path", "output")
        folder = os.path.dirname(path) if os.path.isfile(path) else "output"
        os.startfile(folder) if os.name == "nt" else os.system(f'xdg-open "{folder}"')

    # ── Helpers ──────────────────────────────────────────
    def _show_error(self, title: str, msg: str):
        QMessageBox.critical(self, title, msg)
        self.progress.update_progress(0, f"Error: {msg[:80]}")


# ── Settings Panel ───────────────────────────────────────
class SettingsPanel(QWidget):
    """Application settings — model selection, paths, preferences."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = Settings()
        self.model_mgr = ModelManager()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        layout.addWidget(SectionHeader("🧠  AI Model Settings"))

        # YOLOv8
        layout.addWidget(self._model_group(
            "YOLOv8 (Auto Detection)", "yolov8",
        ))

        # SAM2
        layout.addWidget(self._model_group(
            "SAM2 (Manual Segmentation)", "sam2",
        ))

        # ProPainter
        layout.addWidget(self._model_group(
            "ProPainter (Inpainting)", "propainter",
        ))

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

    def _model_group(self, title: str, family: str) -> QGroupBox:
        group = QGroupBox(title)
        lay = QVBoxLayout(group)

        combo = QComboBox()
        variants = self.model_mgr.list_variants(family)
        current = self.settings.get(f"models.{family}")

        for v in variants:
            size = f"{v['size_mb']}MB" if v["size_mb"] else f"{v['vram_gb']}GB VRAM"
            status = " ✓" if v["downloaded"] else ""
            label = f"{v['name']}  ({size}) — {v['description']}{status}"
            combo.addItem(label, v["name"])
            if v["name"] == current:
                combo.setCurrentIndex(combo.count() - 1)

        combo.currentIndexChanged.connect(
            lambda idx, f=family, c=combo: self._on_model_changed(f, c.itemData(idx))
        )
        lay.addWidget(combo)
        return group

    def _on_model_changed(self, family: str, variant: str):
        self.settings.set(f"models.{family}", variant)
        log.info("Model changed: %s → %s", family, variant)

        if not self.model_mgr.is_downloaded(family, variant):
            reply = QMessageBox.question(
                self, "Download Model",
                f"{variant} is not downloaded yet.\nDownload now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                dlg = ModelDownloadDialog(self)
                dlg.show()
                worker = Worker(
                    lambda pc=None, cf=None: self.model_mgr.download(
                        family, variant, progress_callback=pc, cancel_flag=cf,
                    )
                )
                worker.signals.progress.connect(dlg.update)
                worker.signals.finished.connect(lambda _: dlg.close())
                worker.signals.error.connect(lambda e: (
                    dlg.close(),
                    QMessageBox.critical(self, "Error", e),
                ))
                dlg.cancel_btn.clicked.connect(worker.cancel)
                TaskQueue().submit(worker)
