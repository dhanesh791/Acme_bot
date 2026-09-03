from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import settings


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("acme_rag")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(settings.data_dir / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    return logger


logger = configure_logging()
