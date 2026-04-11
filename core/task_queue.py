"""
Background task execution using PyQt6 QThreadPool.
All heavy processing runs here so the UI never freezes.
"""

from __future__ import annotations

import traceback
from typing import Any, Callable, Optional

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
            self.signals.error.emit(str(exc))


# ── Task Queue Manager ───────────────────────────────────
class TaskQueue:
    """Singleton task queue backed by QThreadPool."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._pool = QThreadPool.globalInstance()
            cls._instance._pool.setMaxThreadCount(4)
            cls._instance._active: list[Worker] = []
            log.info(
                "TaskQueue ready — max threads: %d",
                cls._instance._pool.maxThreadCount(),
            )
        return cls._instance

    def submit(self, worker: Worker) -> Worker:
        """Submit a Worker to the thread pool."""
        self._active.append(worker)
        worker.signals.finished.connect(lambda _: self._cleanup(worker))
        worker.signals.error.connect(lambda _: self._cleanup(worker))
        worker.signals.cancelled.connect(lambda: self._cleanup(worker))
        self._pool.start(worker)
        log.debug("Task submitted: %s", worker.fn.__name__)
        return worker

    def cancel_all(self):
        for w in self._active:
            w.cancel()
        log.info("All tasks cancelled.")

    def _cleanup(self, worker: Worker):
        if worker in self._active:
            self._active.remove(worker)

    @property
    def active_count(self) -> int:
        return len(self._active)
