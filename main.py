"""
Anz-Creator — AI-powered Video Processing Toolkit
Entry point: initializes Qt app, applies dark material theme, launches main window.
"""

import os
import sys

# Absolute path support for PyInstaller (when running as .exe)
if getattr(sys, "frozen", False):
    _PROJECT_ROOT = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    _PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

if _PROJECT_ROOT and _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    os.chdir(_PROJECT_ROOT)
except OSError:
    pass

from PyQt6.QtCore import QThread  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from utils.logger import log  # noqa: E402

# Global refs to keep crash file open for faulthandler
_crash_file = None
_handling_exception = False  # Lock to prevent infinite error loop


def main() -> int:
    log.info("=" * 50)
    log.info("Anz-Creator starting…")
    log.info("=" * 50)

    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

    app = QApplication(sys.argv)
    app.setApplicationName("Anz-Creator")
    app.setOrganizationName("AnzCreator")

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
        palette.setColor(
            QPalette.ColorRole.HighlightedText, QColor(255, 255, 255),
        )
        app.setPalette(palette)

    app.setStyleSheet(app.styleSheet() + """
        QMainWindow { background: #161b22; }
        QToolTip { background: #1e2a3a; color: #e0e0e0; border: 1px solid #30363d; padding: 4px 8px; font-size: 12px; }
        QScrollBar:vertical { width: 8px; background: transparent; }
        QScrollBar::handle:vertical { background: #30363d; border-radius: 4px; min-height: 30px; }
        QScrollBar::handle:vertical:hover { background: #484f58; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QTabWidget::pane { border: 1px solid #30363d; border-radius: 6px; background: #0d1117; }
        QTabBar::tab { padding: 8px 16px; border-radius: 6px 6px 0 0; font-size: 12px; }
        QTabBar::tab:selected { background: #0d1117; color: #80cbc4; }
        QTabBar::tab:!selected { background: #161b22; color: #8b949e; }
        QGroupBox { border: 1px solid #30363d; border-radius: 8px; margin-top: 12px; padding-top: 20px; font-size: 13px; font-weight: bold; color: #b0bec5; }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
        QComboBox { min-height: 32px; padding: 4px 8px; }
        QLineEdit { padding: 6px 10px; border-radius: 6px; }
        QPushButton { min-height: 32px; padding: 4px 16px; border-radius: 6px; }
        QProgressBar { border-radius: 4px; text-align: center; }
        QProgressBar::chunk { border-radius: 4px; }
    """)

    from ui.main_window import MainWindow
    window = MainWindow()
    window.show()

    log.info("Application ready.")
    exit_code = app.exec()

    # Cleanup
    try:
        if hasattr(window, "debug_panel") and hasattr(
            window.debug_panel, "remove_handler",
        ):
            window.debug_panel.remove_handler()
    except Exception:
        pass

    try:
        window.close()
    except Exception:
        pass

    app.processEvents()
    return exit_code


def _global_exception_handler(exc_type, exc_value, exc_tb):
    global _handling_exception
    # Prevent infinite loop if QMessageBox itself raises
    if _handling_exception:
        return
    _handling_exception = True

    try:
        if issubclass(exc_type, (SystemExit, KeyboardInterrupt)):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        import traceback
        tb_str = "".join(
            traceback.format_exception(exc_type, exc_value, exc_tb),
        )
        log.critical("Unhandled exception:\n%s", tb_str)

        from PyQt6.QtWidgets import QApplication, QMessageBox
        app_inst = QApplication.instance()

        if (
            app_inst is not None
            and QThread.currentThread() == app_inst.thread()
        ):
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("Anz-Creator — Error")
            msg.setText("An unexpected error occurred.")
            msg.setDetailedText(tb_str)
            msg.exec()
    except Exception:
        pass
    finally:
        _handling_exception = False


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()

    import atexit
    import faulthandler

    _crash_log = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        "Anz-Creator", "logs", "crash_dump.log",
    )
    try:
        os.makedirs(os.path.dirname(_crash_log), exist_ok=True)
        _crash_file = open(_crash_log, "a", encoding="utf-8")
        _crash_file.write("\n\n=== Session started ===\n")
        _crash_file.flush()
        faulthandler.enable(file=_crash_file, all_threads=True)
    except (OSError, PermissionError) as exc:
        # If we can't create the crash log, fall back to stderr
        _crash_file = None
        try:
            faulthandler.enable()
        except Exception:
            pass
        print(f"Warning: cannot create crash log: {exc}", file=sys.stderr)

    _cf = _crash_file

    def _close_crash_file():
        if _cf and not _cf.closed:
            try:
                _cf.close()
            except Exception:
                pass

    atexit.register(_close_crash_file)
    sys.excepthook = _global_exception_handler

    exit_code = main()
    sys.exit(exit_code)
