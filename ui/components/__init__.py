# ── Settings Panel ───────────────────────────────────────
from __future__ import annotations

import os

from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from core.model_manager import ModelManager
from core.settings import Settings
from core.task_queue import TaskQueue, Worker
from ui.components import ModelDownloadDialog, SectionHeader
from utils.logger import log

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
        path_label = QLabel(
            f"Models stored in: <code>{models_dir}</code>"
        )
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
            size = (
                f"{v['size_mb']}MB"
                if v.get("size_mb") else f"{v.get('vram_gb', 0)}GB VRAM"
            )
            status = " ✓" if v["downloaded"] else ""
            label = (
                f"{v['name']}  ({size}) — {v['description']}{status}"
            )
            combo.addItem(label, v["name"])
            if v["name"] == current:
                combo.setCurrentIndex(combo.count() - 1)

        # Capture family for lambda
        _family = family
        combo.currentIndexChanged.connect(
            lambda idx, f=_family, c=combo: self._on_model_changed(
                f, c.itemData(idx),
            )
        )
        lay.addWidget(combo)
        return group

    def _on_model_changed(self, family: str, variant: str):
        if variant is None:
            return
        self.settings.set(f"models.{family}", variant)
        log.info("Model changed: %s → %s", family, variant)

        if not self.model_mgr.is_downloaded(family, variant):
            reply = QMessageBox.question(
                self, "Download Model",
                f"{variant} is not downloaded yet.\nDownload now?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                dlg = ModelDownloadDialog(self)
                dlg.show()

                _fam = family
                _var = variant

                def _do_download(
                    progress_callback=None, cancel_flag=None,
                ):
                    return self.model_mgr.download(
                        _fam, _var,
                        progress_callback=progress_callback,
                        cancel_flag=cancel_flag,
                    )

                worker = Worker(_do_download)
                worker.signals.progress.connect(dlg.update)
                worker.signals.finished.connect(lambda _: dlg.close())
                worker.signals.error.connect(lambda e: (
                    dlg.close(),
                    QMessageBox.critical(self, "Error", str(e)),
                ))
                dlg.cancel_btn.clicked.connect(worker.cancel)
                TaskQueue().submit(worker)


# ── Styled Progress Bar ─────────────────────────────────
class ProgressPanel(QWidget):
    """Animated progress bar with status label."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)

        self.label = QLabel("Ready")
        self.label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self.label)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(True)
        self.bar.setFixedHeight(22)
        layout.addWidget(self.bar)

    def update_progress(self, percent: int, message: str = ""):
        self.bar.setValue(max(0, min(100, percent)))
        if message:
            self.label.setText(message)

    def reset(self):
        self.bar.setValue(0)
        self.label.setText("Ready")


# ── Video Preview Widget ────────────────────────────────
class VideoPreview(QLabel):
    """Display a video thumbnail with aspect ratio preservation.

    The infinite-zoom bug occurs when setPixmap() changes QLabel's
    sizeHint, which triggers a layout recalculation, which triggers
    resizeEvent, which calls _fit() again - infinite loop.

    Fix: use Expanding size policy so QLabel never requests a resize
    based on pixmap content, and track the last fitted size to skip
    redundant refits.
    """

    def __init__(self, parent=None, min_h: int = 240, max_h: int = 400):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(min_h)
        self.setMaximumHeight(max_h)
        # Expanding horizontally, Fixed vertically — prevents the widget
        # from growing unbounded inside a QScrollArea.
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.setStyleSheet(
            "background: #1a1a2e; border: 2px dashed #444; "
            "border-radius: 8px;"
        )
        self.setText("No video loaded")
        self._pixmap: Optional[QPixmap] = None
        self._fitting = False
        self._last_fit_size: tuple[int, int] = (0, 0)
        self._resize_timer: Optional[QTimer] = None

    def set_pixmap_direct(self, pixmap: QPixmap):
        """Set pixmap directly. This is the ONLY way to set the preview."""
        try:
            if pixmap is not None and not pixmap.isNull():
                self._pixmap = QPixmap(pixmap)
                self._last_fit_size = (0, 0)  # Force refit
                self.setText("")
                self._do_fit()  # Fit immediately, no timer
        except Exception:
            pass

    def set_pixmap_file(self, path: str):
        try:
            pm = QPixmap(path)
            if not pm.isNull():
                self.set_pixmap_direct(pm)
        except Exception:
            pass

    def _schedule_fit(self):
        """Debounce resize-triggered fits."""
        if self._fitting:
            return
        if self._resize_timer is None:
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self._do_fit)
        self._resize_timer.start(50)  # 50ms debounce

    def _do_fit(self):
        """Scale pixmap to fit widget while preserving aspect ratio."""
        if self._fitting:
            return
        self._fitting = True
        try:
            if self._pixmap is None or self._pixmap.isNull():
                return

            w = self.width()
            h = self.height()
            if w <= 0 or h <= 0:
                return

            # Skip if size hasn't actually changed
            if (w, h) == self._last_fit_size:
                return
            self._last_fit_size = (w, h)

            scaled = self._pixmap.scaled(
                QSize(w, h),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if not scaled.isNull():
                super().setPixmap(scaled)
        except Exception:
            pass
        finally:
            self._fitting = False

    def resizeEvent(self, event):
        """Rescale pixmap on resize, but only if not already fitting."""
        super().resizeEvent(event)
        if not self._fitting:
            self._schedule_fit()

    def setPixmap(self, pixmap):
        """Block external setPixmap to prevent bypassing our scaling."""
        if self._fitting:
            super().setPixmap(pixmap)
        # else: ignored — use set_pixmap_direct() instead


# ── Clickable Frame for SAM2 manual mode ─────────────────
class ClickableFrame(VideoPreview):
    """Video preview that captures user click coordinates."""
    point_added = pyqtSignal(int, int)

    def __init__(self, parent=None, min_h: int = 240, max_h: int = 400):
        super().__init__(parent, min_h=min_h, max_h=max_h)
        self._points: list[tuple[int, int]] = []
        self._original_size: tuple[int, int] = (0, 0)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setStyleSheet(
            "background: #1a1a2e; border: 2px solid #00bfa5; "
            "border-radius: 8px;"
        )
        self._drawing = False

    def set_pixmap_direct(self, pixmap: QPixmap):
        """Override to also clear points when new image is set."""
        try:
            if pixmap is not None and not pixmap.isNull():
                self._points.clear()
                super().set_pixmap_direct(pixmap)
        except Exception:
            pass

    def set_original_size(self, width: int, height: int):
        """Set original image dimensions for coordinate mapping."""
        self._original_size = (width, height)

    def mousePressEvent(self, event: QMouseEvent):
        try:
            if not (self._pixmap and not self._pixmap.isNull()):
                return
            if event.button() != Qt.MouseButton.LeftButton:
                return

            current_pm = self.pixmap()
            if current_pm is None or current_pm.isNull():
                return

            x_off = (self.width() - current_pm.width()) // 2
            y_off = (self.height() - current_pm.height()) // 2
            cx = int(event.pos().x()) - x_off
            cy = int(event.pos().y()) - y_off

            if not (0 <= cx < current_pm.width()):
                return
            if not (0 <= cy < current_pm.height()):
                return

            ow, oh = self._original_size
            if ow <= 0 or oh <= 0:
                return

            ox = int(cx / current_pm.width() * ow)
            oy = int(cy / current_pm.height() * oh)
            ox = max(0, min(ow - 1, ox))
            oy = max(0, min(oh - 1, oy))
            self._points.append((ox, oy))
            self.point_added.emit(ox, oy)
            self._redraw_points()
        except Exception:
            pass

    def _redraw_points(self):
        """Redraw points on the current image."""
        if self._drawing:
            return
        self._drawing = True
        try:
            if not self._pixmap or self._pixmap.isNull():
                return

            ow, oh = self._original_size
            if ow <= 0 or oh <= 0:
                return

            base_pm = QPixmap(self._pixmap)
            if base_pm.isNull():
                return

            w = self.width()
            h = self.height()
            if w <= 0 or h <= 0:
                return

            scaled_pm = base_pm.scaled(
                QSize(w, h),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if scaled_pm.isNull():
                return

            painter = QPainter(scaled_pm)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            for ox, oy in self._points:
                sx = int(ox / ow * scaled_pm.width())
                sy = int(oy / oh * scaled_pm.height())

                painter.setBrush(QColor(0, 191, 165, 200))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(sx - 6, sy - 6, 12, 12)

                painter.setBrush(QColor(255, 255, 255))
                painter.drawEllipse(sx - 3, sy - 3, 6, 6)

            painter.end()

            # Set directly via QLabel.setPixmap, bypassing our override
            self._fitting = True
            super(VideoPreview, self).setPixmap(scaled_pm)
            self._fitting = False

        except Exception:
            pass
        finally:
            self._drawing = False

    def clear_points(self):
        self._points.clear()
        self._last_fit_size = (0, 0)  # Force refit to clear dots
        self._do_fit()

    @property
    def points(self) -> list[tuple[int, int]]:
        return list(self._points)


# ── Drag-drop file input ────────────────────────────────
class FileDropZone(QFrame):
    """Drag & drop zone for local video files."""
    file_dropped = pyqtSignal(str)

    SUPPORTED = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(80)
        self.setStyleSheet(
            "QFrame { border: 2px dashed #555; border-radius: 10px; "
            "background: #1e1e2e; }"
        )
        layout = QVBoxLayout(self)
        self._label = QLabel("📂  Drag & drop video here  or  Browse")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(
            "color: #aaa; font-size: 13px; border: none;"
        )
        layout.addWidget(self._label)

        btn = QPushButton("Browse Files")
        btn.setFixedWidth(140)
        btn.clicked.connect(self._browse)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video", "",
            "Video files (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv)",
        )
        if path:
            self.file_dropped.emit(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(
                "QFrame { border: 2px solid #00bfa5; "
                "border-radius: 10px; background: #263238; }"
            )

    def dragLeaveEvent(self, event):
        self.setStyleSheet(
            "QFrame { border: 2px dashed #555; border-radius: 10px; "
            "background: #1e1e2e; }"
        )

    def dropEvent(self, event):
        self.dragLeaveEvent(event)
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            ext = os.path.splitext(path)[1].lower()
            if ext in self.SUPPORTED:
                self.file_dropped.emit(path)
                return
        QMessageBox.warning(self, "Unsupported", "Please drop a video file.")


# ── Model download dialog ───────────────────────────────
class ModelDownloadDialog(QDialog):
    """Dialog showing model download progress."""

    def __init__(self, parent=None, title="Downloading Models"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(450)
        self.setModal(True)

        layout = QVBoxLayout(self)
        self.info_label = QLabel("Preparing…")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.progress = ProgressPanel()
        layout.addWidget(self.progress)

        self.cancel_btn = QPushButton("Cancel")
        layout.addWidget(
            self.cancel_btn, alignment=Qt.AlignmentFlag.AlignRight,
        )

    def update(self, percent: int, message: str):
        self.progress.update_progress(percent, message)
        self.info_label.setText(message)


# ── Section header ───────────────────────────────────────
class SectionHeader(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #e0e0e0; "
            "padding: 8px 0 4px 0; border: none;"
        )
