"""
Anz-Creator — AI-powered Video Processing Toolkit
Entry point: initializes Qt app, applies dark material theme, launches main window.
"""

import os
import sys

# Ensure project root is on path and set as working directory
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _PROJECT_ROOT)
os.chdir(_PROJECT_ROOT)

from PyQt6.QtWidgets import QApplication

from utils.logger import log


def main():
    log.info("=" * 50)
    log.info("Anz-Creator starting…")
    log.info("=" * 50)

    # High-DPI support
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

    app = QApplication(sys.argv)
    app.setApplicationName("Anz-Creator")
    app.setOrganizationName("AnzCreator")

    # Apply qt-material dark theme
    try:
        from qt_material import apply_stylesheet
        extra = {
            "density_scale": "0",
            "font_family": "Segoe UI, Roboto, sans-serif",
            "font_size": "13px",
        }
        apply_stylesheet(app, theme="dark_teal.xml", extra=extra)
        log.info("qt-material theme applied: dark_teal.xml")
    except ImportError:
        log.warning("qt-material not installed — using default Qt style.")
        app.setStyle("Fusion")
        # Apply a basic dark palette as fallback
        from PyQt6.QtGui import QColor, QPalette
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(22, 27, 34))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(201, 209, 217))
        palette.setColor(QPalette.ColorRole.Base, QColor(13, 17, 23))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(22, 27, 34))
        palette.setColor(QPalette.ColorRole.Text, QColor(201, 209, 217))
        palette.setColor(QPalette.ColorRole.Button, QColor(33, 38, 45))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(201, 209, 217))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 150, 136))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        app.setPalette(palette)

    # Custom global stylesheet overrides
    app.setStyleSheet(app.styleSheet() + """
        QMainWindow {
            background: #161b22;
        }
        QToolTip {
            background: #1e2a3a;
            color: #e0e0e0;
            border: 1px solid #30363d;
            padding: 4px 8px;
            font-size: 12px;
        }
        QScrollBar:vertical {
            width: 8px;
            background: transparent;
        }
        QScrollBar::handle:vertical {
            background: #30363d;
            border-radius: 4px;
            min-height: 30px;
        }
        QScrollBar::handle:vertical:hover {
            background: #484f58;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
        }
        QTabWidget::pane {
            border: 1px solid #30363d;
            border-radius: 6px;
            background: #0d1117;
        }
        QTabBar::tab {
            padding: 8px 16px;
            border-radius: 6px 6px 0 0;
            font-size: 12px;
        }
        QTabBar::tab:selected {
            background: #0d1117;
            color: #80cbc4;
        }
        QTabBar::tab:!selected {
            background: #161b22;
            color: #8b949e;
        }
        QGroupBox {
            border: 1px solid #30363d;
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 20px;
            font-size: 13px;
            font-weight: bold;
            color: #b0bec5;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
        }
        QComboBox {
            min-height: 32px;
            padding: 4px 8px;
        }
        QLineEdit {
            padding: 6px 10px;
            border-radius: 6px;
        }
        QPushButton {
            min-height: 32px;
            padding: 4px 16px;
            border-radius: 6px;
        }
        QProgressBar {
            border-radius: 4px;
            text-align: center;
        }
        QProgressBar::chunk {
            border-radius: 4px;
        }
    """)

    # Launch main window
    from ui.main_window import MainWindow
    window = MainWindow()
    window.show()

    log.info("Application ready.")
    sys.exit(app.exec())


def _global_exception_handler(exc_type, exc_value, exc_tb):
    """Catch unhandled exceptions, log them, and show a dialog."""
    import traceback
    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    log.critical("Unhandled exception:\n%s", tb_str)

    # Try to show a message box
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance()
        if app:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("Anz-Creator — Error")
            msg.setText("An unexpected error occurred.")
            msg.setDetailedText(tb_str)
            msg.exec()
    except Exception:
        pass


if __name__ == "__main__":
    # Required for PyInstaller on Windows to prevent duplicate processes
    import multiprocessing
    multiprocessing.freeze_support()

    sys.excepthook = _global_exception_handler
    main()
