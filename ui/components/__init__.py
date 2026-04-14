"""
Reusable UI components for Anz-Creator.
"""

from __future__ import annotations

import os
from typing import Optional

import cv2
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
        self._rgb_ref = None  # prevent numpy GC

    def set_frame(self, frame: np.ndarray):
        """Display an OpenCV BGR/BGRA/grayscale frame safely."""
        try:
            if frame is None or frame.size == 0:
                return
            h, w = frame.shape[:2]
            ch = frame.shape[2] if frame.ndim == 3 else 1

            if ch == 4:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
            elif ch == 3:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            elif ch == 1 or frame.ndim == 2:
                rgb = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
            else:
                return

            rgb = np.ascontiguousarray(rgb)
            self._rgb_ref = rgb
            qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
            # Deep copy pixmap so it has NO reference to numpy memory
            self._pixmap = QPixmap.fromImage(qimg.copy())
            self._rgb_ref = None  # safe to release now, pixmap owns pixel data
            self._fit()
        except Exception:
            pass

    def set_pixmap_direct(self, pixmap: QPixmap):
        """Set pixmap directly (already constructed, thread-safe)."""
        self._pixmap = pixmap
        self._fit()

    def set_pixmap_file(self, path: str):
        self._pixmap = QPixmap(path)
        self._fit()

    def _fit(self):
        try:
            if self._pixmap and not self._pixmap.isNull():
                w = self.width()
                h = self.height()
                if w > 0 and h > 0:
                    from PyQt6.QtCore import QSize

                    scaled = self._pixmap.scaled(
                        QSize(w, h),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    if not scaled.isNull():
                        self.setPixmap(scaled)
        except Exception:
            pass

    def resizeEvent(self, event):
        try:
            self._fit()
        except Exception:
            pass
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
        try:
            if frame is None or frame.size == 0:
                return
            h, w = frame.shape[:2]
            self._original_size = (w, h)
            self._points.clear()
            super().set_frame(frame)
        except Exception:
            pass

    def mousePressEvent(self, event: QMouseEvent):
        try:
            if self._pixmap and not self._pixmap.isNull() and event.button() == Qt.MouseButton.LeftButton:
                pm = self.pixmap()
                if pm is None or pm.isNull():
                    return
                x_off = (self.width() - pm.width()) // 2
                y_off = (self.height() - pm.height()) // 2
                cx = event.pos().x() - x_off
                cy = event.pos().y() - y_off
                if 0 <= cx < pm.width() and 0 <= cy < pm.height():
                    ow = self._original_size[0]
                    oh = self._original_size[1]
                    if ow > 0 and oh > 0:
                        ox = int(cx / pm.width() * ow)
                        oy = int(cy / pm.height() * oh)
                        self._points.append((ox, oy))
                        self.point_added.emit(ox, oy)
                        self._draw_points()
        except Exception:
            pass

    def _draw_points(self):
        try:
            if not self._pixmap or self._pixmap.isNull():
                return
            if self._original_size[0] <= 0 or self._original_size[1] <= 0:
                return
            w = self.width()
            h = self.height()
            if w <= 0 or h <= 0:
                return

            from PyQt6.QtCore import QSize

            pm = self._pixmap.scaled(
                QSize(w, h),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if pm.isNull():
                return

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
        except Exception:
            pass

    def clear_points(self):
        self._points.clear()
        try:
            self._fit()
        except Exception:
            pass

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
