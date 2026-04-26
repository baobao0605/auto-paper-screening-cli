"""Logging configuration for the CLI pipeline."""

from __future__ import annotations

import logging
from pathlib import Path

from src.utils import ensure_dir


def configure_logging(output_dir: Path, level: str = "INFO") -> logging.Logger:
    """Configure file and console logging for the application."""

    ensure_dir(output_dir)
    logger = logging.getLogger("aiscreening")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    if logger.handlers:
        logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    run_handler = logging.FileHandler(output_dir / "run.log", encoding="utf-8")
    run_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    run_handler.setFormatter(formatter)

    error_handler = logging.FileHandler(output_dir / "error.log", encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    console_handler.setFormatter(formatter)

    logger.addHandler(run_handler)
    logger.addHandler(error_handler)
    logger.addHandler(console_handler)
    return logger
