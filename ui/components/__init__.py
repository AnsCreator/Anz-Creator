"""
Reusable UI components for Anz-Creator.
"""

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


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
    """Display a video thumbnail with aspect ratio preservation. Pixmap-only."""

    def __init__(self, parent=None, min_h: int = 240):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(min_h)
        self.setStyleSheet(
            "background: #1a1a2e; border: 2px dashed #444; border-radius: 8px;"
        )
        self.setText("No video loaded")
        self._pixmap: Optional[QPixmap] = None
        self._fitting = False
        self._resize_timer = None

    def set_pixmap_direct(self, pixmap: QPixmap):
        """Set pixmap directly. This is the ONLY way to set the preview."""
        try:
            if pixmap is not None and not pixmap.isNull():
                self._pixmap = QPixmap(pixmap)
                self.setText("")
                self._schedule_fit()
        except Exception:
            pass

    def set_pixmap_file(self, path: str):
        try:
            pm = QPixmap(path)
            if not pm.isNull():
                self._pixmap = QPixmap(pm)
                self.setText("")
                self._schedule_fit()
        except Exception:
            pass

    def _schedule_fit(self):
        """Debounce fit calls to prevent recursion."""
        if self._fitting:
            return
        from PyQt6.QtCore import QTimer
        if self._resize_timer is None:
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self._fit)
        self._resize_timer.start(10)

    def _fit(self):
        """Scale pixmap to fit widget while preserving aspect ratio."""
        if self._fitting:
            return
        self._fitting = True
        try:
            if self._pixmap is None or self._pixmap.isNull():
                self._fitting = False
                return

            w = self.width()
            h = self.height()
            if w <= 0 or h <= 0:
                self._fitting = False
                return

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
        """Override resize to debounce fit calls."""
        self._schedule_fit()
        super().resizeEvent(event)

    def setPixmap(self, pixmap):
        """Override to prevent external setPixmap calls from causing issues."""
        if self._fitting:
            super().setPixmap(pixmap)


# ── Clickable Frame for SAM2 manual mode ─────────────────
class ClickableFrame(VideoPreview):
    """Video preview that captures user click coordinates."""
    point_added = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points: list[tuple[int, int]] = []
        self._original_size = (0, 0)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setStyleSheet(
            "background: #1a1a2e; border: 2px solid #00bfa5; border-radius: 8px;"
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
            if (self._pixmap and not self._pixmap.isNull() and
                event.button() == Qt.MouseButton.LeftButton):

                current_pm = self.pixmap()
                if current_pm is None or current_pm.isNull():
                    return

                x_off = (self.width() - current_pm.width()) // 2
                y_off = (self.height() - current_pm.height()) // 2
                cx = event.pos().x() - x_off
                cy = event.pos().y() - y_off

                if 0 <= cx < current_pm.width() and 0 <= cy < current_pm.height():
                    ow, oh = self._original_size
                    if ow > 0 and oh > 0:
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
                self._drawing = False
                return

            ow, oh = self._original_size
            if ow <= 0 or oh <= 0:
                self._drawing = False
                return

            base_pm = QPixmap(self._pixmap)
            if base_pm.isNull():
                self._drawing = False
                return

            w = self.width()
            h = self.height()
            if w <= 0 or h <= 0:
                self._drawing = False
                return

            scaled_pm = base_pm.scaled(
                QSize(w, h),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if scaled_pm.isNull():
                self._drawing = False
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

            self._fitting = True
            super().setPixmap(scaled_pm)
            self._fitting = False

        except Exception:
            pass
        finally:
            self._drawing = False

    def clear_points(self):
        self._points.clear()
        self._schedule_fit()

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
        self._label.setStyleSheet("color: #aaa; font-size: 13px; border: none;")
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
                "QFrame { border: 2px solid #00bfa5; border-radius: 10px; "
                "background: #263238; }"
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
        layout.addWidget(self.cancel_btn, alignment=Qt.AlignmentFlag.AlignRight)

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
