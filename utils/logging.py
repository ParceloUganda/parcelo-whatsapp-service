"""Logging utilities for the Parcelo WhatsApp service."""

import logging
from logging import Logger
from typing import Optional


def configure_logging(level: str = "INFO") -> Logger:
    """Configure root logger and return it.

    Args:
        level: Logging level name.
    """

    logger = logging.getLogger()
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.setLevel(level.upper())
    return logger


def get_logger(name: Optional[str] = None) -> Logger:
    """Return a module-specific logger."""

    return logging.getLogger(name)
