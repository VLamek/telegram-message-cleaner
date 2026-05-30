from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_DIR_NAME = "TelegramMessageCleaner_Logs"
LATEST_LOG_FILE = "latest.log"
HISTORY_LOG_FILE = "history.log"


def format_exception_message(exc: BaseException) -> str:
    text = f"{exc.__class__.__name__}: {exc}"
    return text.strip()[:500]


def setup_app_logger(app_dir: Path) -> tuple[logging.Logger, Path]:
    logger = logging.getLogger("telegram_message_cleaner")
    if logger.handlers:
        log_dir = app_dir / LOG_DIR_NAME
        return logger, log_dir

    log_dir = app_dir / LOG_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    latest_handler = RotatingFileHandler(
        log_dir / LATEST_LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=2,
        encoding="utf-8",
    )
    latest_handler.setFormatter(formatter)

    history_handler = RotatingFileHandler(
        log_dir / HISTORY_LOG_FILE,
        maxBytes=100 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    history_handler.setFormatter(formatter)

    logger.addHandler(latest_handler)
    logger.addHandler(history_handler)
    return logger, log_dir
