"""General utility helpers used across the project."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re


WHITESPACE_RE = re.compile(r"\s+")


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp without microseconds."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dir(path: Path) -> None:
    """Create a directory if it does not exist."""

    path.mkdir(parents=True, exist_ok=True)


def ensure_parent_dir(path: Path) -> None:
    """Create the parent directory for a file path."""

    ensure_dir(path.parent)


def normalize_whitespace(value: str) -> str:
    """Collapse repeated whitespace into single spaces."""

    return WHITESPACE_RE.sub(" ", value).strip()


def non_empty(value: str | None) -> str | None:
    """Return a stripped string or None if it becomes empty."""

    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
