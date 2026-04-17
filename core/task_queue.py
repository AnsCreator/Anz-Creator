"""
Background task execution using PyQt6 QThreadPool.
All heavy processing runs here so the UI never freezes.
"""

from __future__ import annotations

import threading
import traceback
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot

from utils.logger import log


# ── Signals bridge ───────────────────────────────────────
class WorkerSignals(QObject):
    """Signals emitted by a background worker."""
    started = pyqtSignal()
    progress = pyqtSignal(int, str)        # percent, message
    finished = pyqtSignal(object)          # result
    error = pyqtSignal(str)                # error message
    cancelled = pyqtSignal()


# ── Worker ───────────────────────────────────────────────
class Worker(QRunnable):
    """Generic background worker wrapping any callable."""

    def __init__(
        self,
        fn: Callable,
        *args,
        progress_callback: Optional[Callable] = None,
        **kwargs,
    ):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self._cancelled = False
        self.setAutoDelete(False)  # Prevent premature GC

        if progress_callback is None:
            self.kwargs["progress_callback"] = self.signals.progress.emit
        else:
            self.kwargs["progress_callback"] = progress_callback

    def cancel(self):
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    @pyqtSlot()
    def run(self):
        self.signals.started.emit()
        try:
            self.kwargs["cancel_flag"] = lambda: self._cancelled
            result = self.fn(*self.args, **self.kwargs)
            if self._cancelled:
                self.signals.cancelled.emit()
            else:
                self.signals.finished.emit(result)
        except Exception as exc:
            tb = traceback.format_exc()
            log.error("Worker error: %s\n%s", exc, tb)
            try:
                self.signals.error.emit(str(exc))
            except Exception:
                pass


# ── Task Queue Manager ───────────────────────────────────
class TaskQueue:
    """Singleton task queue backed by QThreadPool."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._pool = QThreadPool.globalInstance()
                    inst._pool.setMaxThreadCount(4)
                    inst._active: list[Worker] = []
                    inst._active_lock = threading.Lock()
                    log.info(
                        "TaskQueue ready — max threads: %d",
                        inst._pool.maxThreadCount(),
                    )
                    cls._instance = inst
        return cls._instance

    def submit(self, worker: Worker) -> Worker:
        """Submit a Worker to the thread pool."""
        with self._active_lock:
            self._active.append(worker)

        # Use a small closure to remove on completion. We keep a reference
        # on the worker itself so it isn't collected before the slot fires.
        def _on_done(*_args):
            self._cleanup(worker)

        worker._cleanup_cb = _on_done  # keep alive reference
        worker.signals.finished.connect(_on_done)
        worker.signals.error.connect(_on_done)
        worker.signals.cancelled.connect(_on_done)
        self._pool.start(worker)

        fn_name = getattr(worker.fn, "__name__", repr(worker.fn))
        log.debug("Task submitted: %s", fn_name)
        return worker

    def cancel_all(self):
        with self._active_lock:
            workers = list(self._active)
        for w in workers:
            try:
                w.cancel()
            except Exception:
                pass
        log.info("All tasks cancelled.")

    def _cleanup(self, worker: Worker):
        with self._active_lock:
            try:
                self._active.remove(worker)
            except ValueError:
                pass  # Already removed

    @property
    def active_count(self) -> int:
        with self._active_lock:
            return len(self._active)
