"""Fingerprint utilities for stable paper identity."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re

from src.utils import normalize_whitespace


NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def compute_file_hash(path: Path) -> str:
    """Hash a file's raw bytes."""

    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text_for_hash(text: str) -> str:
    """Normalize extracted text before hashing for content identity."""

    lowered = text.casefold()
    cleaned = NON_ALNUM_RE.sub(" ", lowered)
    return normalize_whitespace(cleaned)


def compute_content_hash(text: str) -> str:
    """Hash normalized extracted text."""

    normalized = normalize_text_for_hash(text)
    return sha256(normalized.encode("utf-8")).hexdigest()


def compute_fallback_fingerprint(path: Path) -> str:
    """Build a stable fallback fingerprint from normalized file metadata."""

    stat = path.stat()
    normalized_name = NON_ALNUM_RE.sub(" ", path.stem.casefold())
    payload = "|".join(
        [
            normalize_whitespace(normalized_name),
            path.suffix.casefold(),
            str(stat.st_size),
        ]
    )
    return sha256(payload.encode("utf-8")).hexdigest()
