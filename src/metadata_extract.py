"""Metadata extraction helpers for titles and DOIs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from src.utils import non_empty, normalize_whitespace


DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)


@dataclass(slots=True)
class PaperMetadata:
    """Detected title and DOI metadata."""

    title: str | None
    doi: str | None


def _clean_filename_title(stem: str) -> str:
    title = DOI_RE.sub("", stem)
    title = title.replace("+", " ").replace("_", " ")
    title = title.replace("{", "").replace("}", "")
    title = re.sub(r"\s+", " ", title)
    title = title.strip(" -_.")
    return normalize_whitespace(title)


def extract_doi(value: str) -> str | None:
    """Extract the first DOI from a string if present."""

    match = DOI_RE.search(value)
    return match.group(0) if match else None


def extract_metadata_from_filename(path: Path) -> PaperMetadata:
    """Extract a best-effort title and DOI from a filename."""

    title = _clean_filename_title(path.stem)
    doi = extract_doi(path.name)
    return PaperMetadata(title=non_empty(title), doi=non_empty(doi))


def extract_metadata_from_text(text: str) -> PaperMetadata:
    """Extract a DOI and rough title candidate from full text."""

    doi = extract_doi(text[:4000])
    title = None
    for line in text.splitlines():
        cleaned = normalize_whitespace(line.replace("\x00", ""))
        if len(cleaned) < 15:
            continue
        if cleaned.casefold().startswith("abstract"):
            continue
        if DOI_RE.search(cleaned):
            continue
        title = cleaned[:300]
        break
    return PaperMetadata(title=non_empty(title), doi=non_empty(doi))
