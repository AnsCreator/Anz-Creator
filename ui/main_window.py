"""
Main Window — shell with sidebar navigation + content area.
"""

from __future__ import annotations

import logging
import os

from PyQt6.QtCore import QObject, Qt, pyqtSignal
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
    def __init__(self, text: str, icon_char: str = "", parent=None):
        display = f"  {icon_char}  {text}" if icon_char else f"  {text}"
        super().__init__(display, parent)
        self.setCheckable(True)
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton { text-align: left; padding-left: 12px; border: none; border-radius: 8px; font-size: 13px; color: #b0bec5; background: transparent; }
            QPushButton:hover { background: rgba(255,255,255,0.06); color: #e0e0e0; }
            QPushButton:checked { background: rgba(0,191,165,0.15); color: #80cbc4; font-weight: bold; border-left: 3px solid #00bfa5; }
        """)


class Sidebar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(220)
        self.setStyleSheet("QFrame { background: #0d1117; border-right: 1px solid #1e2a3a; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 16, 10, 16)
        layout.setSpacing(4)

        title = QLabel("⚡ Anz-Creator")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #80cbc4; padding: 8px 4px 16px 4px; border: none;")
        layout.addWidget(title)

        self.version_label = QLabel("v1.0.0")
        self.version_label.setStyleSheet("font-size: 10px; color: #546e7a; padding: 0 4px 12px 4px; border: none;")
        layout.addWidget(self.version_label)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #1e2a3a; border: none;")
        layout.addWidget(sep)
        layout.addSpacing(8)

        nav_label = QLabel("FEATURES")
        nav_label.setStyleSheet("font-size: 10px; color: #546e7a; padding: 4px 4px; letter-spacing: 2px; border: none;")
        layout.addWidget(nav_label)

        self.buttons: list[SidebarButton] = []

        self.btn_watermark = SidebarButton("Watermark Removal", "🧹")
        self.btn_watermark.setChecked(True)
        self.buttons.append(self.btn_watermark)
        layout.addWidget(self.btn_watermark)

        self.btn_placeholder1 = SidebarButton("Background Remove", "🖼️")
        self.btn_placeholder1.setEnabled(False)
        self.btn_placeholder1.setStyleSheet(self.btn_placeholder1.styleSheet() + "QPushButton:disabled { color: #37474f; }")
        layout.addWidget(self.btn_placeholder1)

        self.btn_placeholder2 = SidebarButton("Video Enhance", "✨")
        self.btn_placeholder2.setEnabled(False)
        self.btn_placeholder2.setStyleSheet(self.btn_placeholder2.styleSheet() + "QPushButton:disabled { color: #37474f; }")
        layout.addWidget(self.btn_placeholder2)

        layout.addStretch()

        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background: #1e2a3a; border: none;")
        layout.addWidget(sep2)
        layout.addSpacing(4)

        self.btn_settings = SidebarButton("Settings", "⚙️")
        self.buttons.append(self.btn_settings)
        layout.addWidget(self.btn_settings)

        self.btn_debug = SidebarButton("Debug Log", "🐛")
        self.buttons.append(self.btn_debug)
        layout.addWidget(self.btn_debug)

        self.btn_about = SidebarButton("About", "ℹ️")
        self.buttons.append(self.btn_about)
        layout.addWidget(self.btn_about)

        for btn in self.buttons:
            btn.clicked.connect(lambda checked, b=btn: self._on_click(b))

    def _on_click(self, clicked: SidebarButton):
        for btn in self.buttons:
            if btn is not clicked:
                btn.setChecked(False)
        clicked.setChecked(True)


class AboutPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("⚡ Anz-Creator")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #80cbc4;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        try:
            from core.updater import get_current_version
            ver = get_current_version()
        except Exception:
            ver = "1.0.0"

        self.ver_label = QLabel(f"Version: {ver}")
        self.ver_label.setStyleSheet("font-size: 14px; color: #b0bec5;")
        self.ver_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.ver_label)

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

        layout.addSpacing(30)

        self.update_status = QLabel("")
        self.update_status.setStyleSheet("font-size: 12px; color: #8b949e;")
        self.update_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_status.setWordWrap(True)
        layout.addWidget(self.update_status)

        try:
            from ui.components import ProgressPanel
            self.update_progress = ProgressPanel()
            self.update_progress.hide()
            layout.addWidget(self.update_progress)
        except ImportError:
            self.update_progress = QLabel("Progress panel UI missing")
            layout.addWidget(self.update_progress)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.check_btn = QPushButton("🔄  Check for Updates")
        self.check_btn.setFixedWidth(200)
        self.check_btn.setMinimumHeight(36)
        self.check_btn.clicked.connect(self._check_update)
        btn_row.addWidget(self.check_btn)

        self.install_btn = QPushButton("⬇  Install Update")
        self.install_btn.setFixedWidth(200)
        self.install_btn.setMinimumHeight(36)
        self.install_btn.hide()
        self.install_btn.clicked.connect(self._install_update)
        btn_row.addWidget(self.install_btn)

        layout.addLayout(btn_row)
        layout.addStretch()

        self._update_info = None

    def _check_update(self):
        self.check_btn.setEnabled(False)
        self.update_status.setText("Checking for updates…")
        try:
            from core.task_queue import TaskQueue, Worker
            from core.updater import check_for_update

            def _check(progress_callback=None, cancel_flag=None):
                return check_for_update()

            worker = Worker(_check)
            worker.signals.finished.connect(self._on_check_done)
            worker.signals.error.connect(lambda e: self._on_check_error(e))
            TaskQueue().submit(worker)
        except Exception as e:
            self._on_check_error(str(e))

    def _on_check_done(self, result):
        self.check_btn.setEnabled(True)
        if result is None:
            self.update_status.setText("<span style='color:#66bb6a'>✓ You're running the latest version.</span>")
            self.install_btn.hide()
        else:
            self._update_info = result
            size_mb = result.get("size", 0) / 1048576
            self.update_status.setText(f"<span style='color:#ffa726'>⬆ Update available: <b>{result.get('tag','')}</b> ({size_mb:.0f} MB)</span>")
            self.install_btn.show()

    def _on_check_error(self, err):
        self.check_btn.setEnabled(True)
        self.update_status.setText(f"<span style='color:#ef5350'>Update check failed: {err}</span>")

    def _install_update(self):
        if not self._update_info:
            return

        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Install Update",
            f"Download and install {self._update_info.get('tag','')}?\n\nThe application will restart after updating.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.install_btn.setEnabled(False)
        if hasattr(self.update_progress, 'show'):
            self.update_progress.show()

        try:
            from core.task_queue import TaskQueue, Worker
            from core.updater import apply_update, download_update

            url = self._update_info["url"]

            def _download_and_apply(progress_callback=None, cancel_flag=None):
                zip_path = download_update(url, progress_callback=progress_callback, cancel_flag=cancel_flag)
                if not zip_path:
                    return None
                return apply_update(zip_path)

            worker = Worker(_download_and_apply)
            if hasattr(self.update_progress, 'update_progress'):
                worker.signals.progress.connect(self.update_progress.update_progress)
            worker.signals.finished.connect(self._on_update_ready)
            worker.signals.error.connect(lambda e: self._on_update_error(e))
            TaskQueue().submit(worker)
        except Exception as e:
            self._on_update_error(str(e))

    def _on_update_ready(self, batch_path):
        if not batch_path:
            self.update_status.setText("Update cancelled.")
            self.install_btn.setEnabled(True)
            return

        self.update_status.setText("<span style='color:#66bb6a'>✓ Update downloaded! Restarting…</span>")
        import subprocess
        if os.name == "nt":
            subprocess.Popen(["cmd", "/c", batch_path], creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            subprocess.Popen(["bash", batch_path])

        from PyQt6.QtWidgets import QApplication
        QApplication.quit()

    def _on_update_error(self, err):
        self.install_btn.setEnabled(True)
        if hasattr(self.update_progress, 'hide'):
            self.update_progress.hide()
        self.update_status.setText(f"<span style='color:#ef5350'>Update failed: {err}</span>")


class LogEmitter(QObject):
    log_signal = pyqtSignal(str)


class _QtLogHandler(logging.Handler):
    """Logging handler that writes to a QPlainTextEdit widget in a Thread-Safe way."""
    def __init__(self, widget):
        super().__init__()
        self._widget = widget
        self._closed = False
        self.emitter = LogEmitter()
        self.emitter.log_signal.connect(self._widget.appendHtml)

    def close_handler(self):
        self._closed = True

    def emit(self, record):
        if self._closed:
            return
        try:
            msg = self.format(record)
            msg = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if record.levelno >= logging.ERROR:
                color = "#f85149"
            elif record.levelno >= logging.WARNING:
                color = "#d29922"
            elif record.levelno >= logging.INFO:
                color = "#8b949e"
            else:
                color = "#6e7681"

            # Emit signal alih-alih merender ke GUI secara langsung
            self.emitter.log_signal.emit(f"<span style='color:{color}'>{msg}</span>")
        except Exception:
            pass


class DebugPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_handler = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        title = QLabel("🐛  Debug Log")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #e0e0e0;")
        header_row.addWidget(title)
        header_row.addStretch()

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setFixedWidth(70)
        self.clear_btn.clicked.connect(self._clear)
        header_row.addWidget(self.clear_btn)

        self.copy_btn = QPushButton("Copy All")
        self.copy_btn.setFixedWidth(80)
        self.copy_btn.clicked.connect(self._copy_all)
        header_row.addWidget(self.copy_btn)

        layout.addLayout(header_row)

        from PyQt6.QtWidgets import QPlainTextEdit
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(2000)
        self.log_text.setStyleSheet(
            "QPlainTextEdit { background: #0d1117; color: #8b949e; font-family: 'Consolas', 'Courier New', monospace; font-size: 11px; border: 1px solid #30363d; border-radius: 6px; padding: 8px; }"
        )
        layout.addWidget(self.log_text)

        log_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Anz-Creator", "logs")
        path_label = QLabel(f"Log files: <code>{log_dir}</code>")
        path_label.setStyleSheet("font-size: 11px; color: #546e7a;")
        path_label.setWordWrap(True)
        layout.addWidget(path_label)

        self._install_handler()

    def _install_handler(self):
        handler = _QtLogHandler(self.log_text)
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter("[%asctime)s] %(levelname)-8s %(funcName)s — %(message)s", datefmt="%H:%M:%S")
        handler.setFormatter(formatter)

        logger = logging.getLogger("AnzCreator")
        logger.addHandler(handler)
        self._log_handler = handler

    def remove_handler(self):
        if self._log_handler is not None:
            self._log_handler.close_handler()
            logger = logging.getLogger("AnzCreator")
            logger.removeHandler(self._log_handler)
            self._log_handler = None

    def _clear(self):
        self.log_text.clear()

    def _copy_all(self):
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self.log_text.toPlainText())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Anz-Creator")
        self.setMinimumSize(1100, 720)
        self.resize(1280, 800)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = Sidebar()
        main_layout.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("QStackedWidget { background: #161b22; }")

        self.watermark_panel = WatermarkRemovalPanel()
        self.settings_panel = SettingsPanel()
        self.about_panel = AboutPanel()
        self.debug_panel = DebugPanel()

        self.stack.addWidget(self.watermark_panel)
        self.stack.addWidget(self.settings_panel)
        self.stack.addWidget(self.about_panel)
        self.stack.addWidget(self.debug_panel)

        main_layout.addWidget(self.stack, 1)

        self.sidebar.btn_watermark.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.sidebar.btn_settings.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        self.sidebar.btn_about.clicked.connect(lambda: self.stack.setCurrentIndex(2))
        self.sidebar.btn_debug.clicked.connect(lambda: self.stack.setCurrentIndex(3))

        try:
            from core.updater import get_current_version
            self.sidebar.version_label.setText(get_current_version())
        except Exception:
            pass

        self.statusBar().showMessage("Ready")
        self.statusBar().setStyleSheet("QStatusBar { background: #0d1117; color: #546e7a; border-top: 1px solid #1e2a3a; font-size: 11px; }")

        log.info("MainWindow initialized.")
        self._startup_update_check()

    def _startup_update_check(self):
        try:
            from core.task_queue import TaskQueue, Worker
            from core.updater import check_for_update

            def _check(progress_callback=None, cancel_flag=None):
                return check_for_update()

            def _on_result(result):
                if result:
                    self.statusBar().showMessage(f"Update available: {result.get('tag','')}  —  Go to About to install.", 15000)
                    self.about_panel._update_info = result
                    size_mb = result.get("size", 0) / 1048576
                    self.about_panel.update_status.setText(f"<span style='color:#ffa726'>⬆ Update available: <b>{result.get('tag','')}</b> ({size_mb:.0f} MB)</span>")
                    self.about_panel.install_btn.show()

            worker = Worker(_check)
            worker.signals.finished.connect(_on_result)
            TaskQueue().submit(worker)
        except Exception as e:
            log.warning(f"Startup update check failed: {e}")

    def closeEvent(self, event):
        self.debug_panel.remove_handler()
        try:
            from core.task_queue import TaskQueue
            TaskQueue().cancel_all()
        except Exception:
            pass
        log.info("Application closing.")
        event.accept()
