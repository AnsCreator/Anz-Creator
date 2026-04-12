"""
Main Window — shell with sidebar navigation + content area.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.feature_panel import SettingsPanel, WatermarkRemovalPanel
from utils.logger import log


class SidebarButton(QPushButton):
    """Navigation button for sidebar."""

    def __init__(self, text: str, icon_char: str = "", parent=None):
        display = f"  {icon_char}  {text}" if icon_char else f"  {text}"
        super().__init__(display, parent)
        self.setCheckable(True)
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding-left: 12px;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                color: #b0bec5;
                background: transparent;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.06);
                color: #e0e0e0;
            }
            QPushButton:checked {
                background: rgba(0,191,165,0.15);
                color: #80cbc4;
                font-weight: bold;
                border-left: 3px solid #00bfa5;
            }
        """)


class Sidebar(QFrame):
    """Left sidebar with navigation buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(220)
        self.setStyleSheet("""
            QFrame {
                background: #0d1117;
                border-right: 1px solid #1e2a3a;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 16, 10, 16)
        layout.setSpacing(4)

        # Logo / Title
        title = QLabel("⚡ Anz-Creator")
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #80cbc4; "
            "padding: 8px 4px 16px 4px; border: none;"
        )
        layout.addWidget(title)

        version = QLabel("v1.0.0")
        version.setStyleSheet(
            "font-size: 10px; color: #546e7a; padding: 0 4px 12px 4px; border: none;"
        )
        layout.addWidget(version)

        # Separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #1e2a3a; border: none;")
        layout.addWidget(sep)
        layout.addSpacing(8)

        # Nav label
        nav_label = QLabel("FEATURES")
        nav_label.setStyleSheet(
            "font-size: 10px; color: #546e7a; padding: 4px 4px; "
            "letter-spacing: 2px; border: none;"
        )
        layout.addWidget(nav_label)

        # Feature buttons
        self.buttons: list[SidebarButton] = []

        self.btn_watermark = SidebarButton("Watermark Removal", "🧹")
        self.btn_watermark.setChecked(True)
        self.buttons.append(self.btn_watermark)
        layout.addWidget(self.btn_watermark)

        # Placeholder for future features
        self.btn_placeholder1 = SidebarButton("Background Remove", "🖼️")
        self.btn_placeholder1.setEnabled(False)
        self.btn_placeholder1.setStyleSheet(
            self.btn_placeholder1.styleSheet()
            + "QPushButton:disabled { color: #37474f; }"
        )
        layout.addWidget(self.btn_placeholder1)

        self.btn_placeholder2 = SidebarButton("Video Enhance", "✨")
        self.btn_placeholder2.setEnabled(False)
        self.btn_placeholder2.setStyleSheet(
            self.btn_placeholder2.styleSheet()
            + "QPushButton:disabled { color: #37474f; }"
        )
        layout.addWidget(self.btn_placeholder2)

        layout.addStretch()

        # Separator
        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background: #1e2a3a; border: none;")
        layout.addWidget(sep2)
        layout.addSpacing(4)

        # Settings
        self.btn_settings = SidebarButton("Settings", "⚙️")
        self.buttons.append(self.btn_settings)
        layout.addWidget(self.btn_settings)

        # About
        self.btn_about = SidebarButton("About", "ℹ️")
        layout.addWidget(self.btn_about)

        # Wire exclusive toggle
        for btn in self.buttons:
            btn.clicked.connect(lambda checked, b=btn: self._on_click(b))

    def _on_click(self, clicked: SidebarButton):
        for btn in self.buttons:
            if btn is not clicked:
                btn.setChecked(False)
        clicked.setChecked(True)


class AboutPanel(QWidget):
    """Simple about page."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("⚡ Anz-Creator")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #80cbc4;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        ver = QLabel("Version 1.0.0")
        ver.setStyleSheet("font-size: 14px; color: #b0bec5;")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(ver)

        layout.addSpacing(20)

        desc = QLabel(
            "AI-powered video processing toolkit.\n\n"
            "• YOLOv8 + SAM2 for watermark detection\n"
            "• ProPainter for temporal-consistent inpainting\n"
            "• yt-dlp for 1000+ platform support\n"
            "• Built with PyQt6 + qt-material"
        )
        desc.setStyleSheet("font-size: 13px; color: #78909c;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addStretch()


class MainWindow(QMainWindow):
    """Application main window — sidebar + stacked content."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Anz-Creator")
        self.setMinimumSize(1100, 720)
        self.resize(1280, 800)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar()
        main_layout.addWidget(self.sidebar)

        # Content stack
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("QStackedWidget { background: #161b22; }")

        # Pages
        self.watermark_panel = WatermarkRemovalPanel()
        self.settings_panel = SettingsPanel()
        self.about_panel = AboutPanel()

        self.stack.addWidget(self.watermark_panel)   # index 0
        self.stack.addWidget(self.settings_panel)     # index 1
        self.stack.addWidget(self.about_panel)        # index 2

        main_layout.addWidget(self.stack, 1)

        # Wire sidebar buttons
        self.sidebar.btn_watermark.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.sidebar.btn_settings.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        self.sidebar.btn_about.clicked.connect(lambda: self._show_about())

        # Status bar
        self.statusBar().showMessage("Ready")
        self.statusBar().setStyleSheet(
            "QStatusBar { background: #0d1117; color: #546e7a; "
            "border-top: 1px solid #1e2a3a; font-size: 11px; }"
        )

        log.info("MainWindow initialized.")

    def _show_about(self):
        self.stack.setCurrentIndex(2)
        for btn in self.sidebar.buttons:
            btn.setChecked(False)

    def closeEvent(self, event):
        from core.task_queue import TaskQueue
        TaskQueue().cancel_all()
        log.info("Application closing.")
        event.accept()
