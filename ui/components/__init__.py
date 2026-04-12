"""
Reusable UI components for Anz-Creator.
"""

from __future__ import annotations

import os
from typing import Optional

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPixmap
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
        self.bar.setValue(percent)
        if message:
            self.label.setText(message)

    def reset(self):
        self.bar.setValue(0)
        self.label.setText("Ready")


# ── Video Preview Widget ────────────────────────────────
class VideoPreview(QLabel):
    """Display a video frame or thumbnail with aspect ratio preservation."""

    def __init__(self, parent=None, min_h: int = 240):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(min_h)
        self.setStyleSheet(
            "background: #1a1a2e; border: 2px dashed #444; border-radius: 8px;"
        )
        self.setText("No video loaded")
        self._pixmap: Optional[QPixmap] = None

    def set_frame(self, frame: np.ndarray):
        """Display an OpenCV BGR frame."""
        if frame is None or frame.size == 0:
            return
        h, w = frame.shape[:2]
        ch = frame.shape[2] if frame.ndim == 3 else 1
        # Ensure contiguous RGB copy (must stay alive while QImage exists)
        rgb = np.ascontiguousarray(frame[..., ::-1]) if ch == 3 else frame.copy()
        self._rgb_ref = rgb  # prevent garbage collection
        bytes_per_line = w * ch
        fmt = QImage.Format.Format_RGB888 if ch == 3 else QImage.Format.Format_Grayscale8
        qimg = QImage(rgb.data, w, h, bytes_per_line, fmt)
        self._pixmap = QPixmap.fromImage(qimg.copy())  # deep copy to decouple from numpy
        self._fit()

    def set_pixmap_file(self, path: str):
        self._pixmap = QPixmap(path)
        self._fit()

    def _fit(self):
        if self._pixmap:
            scaled = self._pixmap.scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setPixmap(scaled)

    def resizeEvent(self, event):
        self._fit()
        super().resizeEvent(event)


# ── Clickable Frame for SAM2 manual mode ─────────────────
class ClickableFrame(VideoPreview):
    """Video preview that captures user click coordinates."""
    point_added = pyqtSignal(int, int)  # x, y in original image coords

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points: list[tuple[int, int]] = []
        self._original_size = (0, 0)  # (w, h)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setStyleSheet(
            "background: #1a1a2e; border: 2px solid #00bfa5; border-radius: 8px;"
        )

    def set_frame(self, frame: np.ndarray):
        h, w = frame.shape[:2]
        self._original_size = (w, h)
        self._points.clear()
        super().set_frame(frame)

    def mousePressEvent(self, event: QMouseEvent):
        if self._pixmap and event.button() == Qt.MouseButton.LeftButton:
            # Map widget coords → original image coords
            pm = self.pixmap()
            if pm is None:
                return
            # Offset from centering
            x_off = (self.width() - pm.width()) // 2
            y_off = (self.height() - pm.height()) // 2
            cx = event.pos().x() - x_off
            cy = event.pos().y() - y_off
            if 0 <= cx < pm.width() and 0 <= cy < pm.height():
                ox = int(cx / pm.width() * self._original_size[0])
                oy = int(cy / pm.height() * self._original_size[1])
                self._points.append((ox, oy))
                self.point_added.emit(ox, oy)
                self._draw_points()

    def _draw_points(self):
        if not self._pixmap:
            return
        pm = self._pixmap.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter = QPainter(pm)
        painter.setPen(Qt.PenStyle.NoPen)
        for ox, oy in self._points:
            sx = int(ox / self._original_size[0] * pm.width())
            sy = int(oy / self._original_size[1] * pm.height())
            painter.setBrush(QColor(0, 191, 165, 200))
            painter.drawEllipse(sx - 6, sy - 6, 12, 12)
            painter.setBrush(QColor(255, 255, 255))
            painter.drawEllipse(sx - 3, sy - 3, 6, 6)
        painter.end()
        self.setPixmap(pm)

    def clear_points(self):
        self._points.clear()
        self._fit()

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
