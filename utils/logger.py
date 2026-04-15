"""
Anz-Creator Logging Module
Centralized logging with file + console output.
"""

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logger(name: str = "AnzCreator", log_dir: str = None) -> logging.Logger:
    """Configure and return the application logger."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(name)s.%(funcName)s:%(lineno)d — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # File handler with rotation (max 10MB per file, keep 5 backups)
    if log_dir is None:
        log_dir = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")),
            "Anz-Creator", "logs",
        )
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_file = os.path.join(log_dir, f"anz_{datetime.now():%Y%m%d}.log")

    try:
        file_handler = RotatingFileHandler(
            log_file, encoding="utf-8",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except (OSError, PermissionError) as exc:
        # If file logging fails (e.g. read-only), continue with console only
        logger.warning("Cannot create log file %s: %s", log_file, exc)

    logger.info("Logger initialized — %s", log_file)
    return logger


log = setup_logger()
