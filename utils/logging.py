from __future__ import annotations

import logging
import os
from typing import Optional

_DEFAULT_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_DEFAULT_DATEFMT = "%Y-%m-%dT%H:%M:%SZ"


def setup_logging(level: Optional[str] = None, fmt: str = _DEFAULT_FORMAT, datefmt: str = _DEFAULT_DATEFMT) -> None:
    """Configure root logger.

    Respect `LOG_LEVEL` env var when level is not supplied.
    """

    log_level = level or os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO), format=fmt, datefmt=datefmt)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return module-specific logger."""

    if logging.getLogger().handlers:
        return logging.getLogger(name)

    # Auto-setup if not configured.
    setup_logging()
    return logging.getLogger(name)
