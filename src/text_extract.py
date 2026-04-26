"""Local text extraction for supported file types."""

from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
import html
import logging
from pathlib import Path
import re

from src.utils import normalize_whitespace


class TextExtractionError(RuntimeError):
    """Raised when text extraction fails or yields no usable text."""


HTML_TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>[\s\S]*?</\1>", re.IGNORECASE)


def _looks_like_html_payload(raw_bytes: bytes) -> bool:
    header = raw_bytes[:512].lstrip().lower()
    return (
        header.startswith(b"<!doctype html")
        or header.startswith(b"<html")
        or b"<html" in header
        or b"<head" in header
        or b"<body" in header
    )


def _extract_html_text(raw_bytes: bytes) -> str:
    decoded = raw_bytes.decode("utf-8", errors="ignore")
    without_scripts = SCRIPT_STYLE_RE.sub(" ", decoded)
    without_tags = HTML_TAG_RE.sub(" ", without_scripts)
    return normalize_whitespace(html.unescape(without_tags))


def _classify_html_payload(text: str) -> str:
    lowered = text.casefold()
    if "recaptcha" in lowered or "challenge page" in lowered:
        return "HTML challenge/access page"
    if "springer nature link" in lowered or "access no" in lowered:
        return "HTML article landing page"
    return "HTML page"


def _extract_pdf_with_pdfminer(path: Path) -> str:
    try:
        from pdfminer.high_level import extract_text as pdfminer_extract_text
    except ImportError as exc:  # pragma: no cover - depends on local environment.
        raise TextExtractionError(
            "PDF extraction fallback requires pdfminer.six. Install project dependencies with "
            "'python -m pip install -r requirements.txt'."
        ) from exc

    try:
        with _suppress_pdf_library_noise():
            return pdfminer_extract_text(str(path))
    except Exception as exc:
        raise TextExtractionError(f"PDF fallback parsing failed: {exc}") from exc


@contextmanager
def _suppress_pdf_library_noise():
    """Silence noisy PDF library warnings that clutter the CLI."""

    pypdf_logger = logging.getLogger("pypdf")
    pdfminer_logger = logging.getLogger("pdfminer")
    previous_pypdf_level = pypdf_logger.level
    previous_pdfminer_level = pdfminer_logger.level
    sink = io.StringIO()

    pypdf_logger.setLevel(logging.ERROR)
    pdfminer_logger.setLevel(logging.ERROR)
    try:
        with redirect_stdout(sink), redirect_stderr(sink):
            yield
    finally:
        pypdf_logger.setLevel(previous_pypdf_level)
        pdfminer_logger.setLevel(previous_pdfminer_level)


def _extract_pdf(path: Path) -> str:
    raw_head = path.read_bytes()[:4096]
    if not raw_head.startswith(b"%PDF") and _looks_like_html_payload(raw_head):
        html_text = _extract_html_text(path.read_bytes()[:250000])
        html_kind = _classify_html_payload(html_text)
        raise TextExtractionError(
            f"Source file is not a PDF. Detected {html_kind} saved with a .pdf extension."
        )

    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - depends on local environment.
        raise TextExtractionError(
            "PDF extraction requires pypdf. Install project dependencies with "
            "'python -m pip install -r requirements.txt'."
        ) from exc

    try:
        with _suppress_pdf_library_noise():
            reader = PdfReader(str(path), strict=False)
            pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    except Exception as exc:
        primary_error = exc

    try:
        return _extract_pdf_with_pdfminer(path)
    except TextExtractionError as fallback_exc:
        raise TextExtractionError(
            f"PDF parsing failed: {primary_error}; fallback failed: {fallback_exc}"
        ) from primary_error


def _extract_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover - depends on local environment.
        raise TextExtractionError(
            "DOCX extraction requires python-docx. Install project dependencies with "
            "'python -m pip install -r requirements.txt'."
        ) from exc

    document = Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _extract_txt(path: Path) -> str:
    encodings = ("utf-8-sig", "utf-8", "latin-1")
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def extract_text(path: Path) -> str:
    """Extract text from PDF, DOCX, or TXT files."""

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = _extract_pdf(path)
    elif suffix == ".docx":
        text = _extract_docx(path)
    elif suffix == ".txt":
        text = _extract_txt(path)
    else:
        raise TextExtractionError(f"Unsupported file type: {path.suffix}")

    cleaned = normalize_whitespace(text)
    if not cleaned:
        raise TextExtractionError("No extractable text found.")
    return text
