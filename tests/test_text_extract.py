from __future__ import annotations

from pathlib import Path

import pytest

from src.text_extract import TextExtractionError, _suppress_pdf_library_noise, extract_text


def test_extract_text_raises_clean_error_for_corrupt_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "broken.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nthis is not a valid pdf and has no eof marker")

    with pytest.raises(TextExtractionError, match="PDF parsing failed"):
        extract_text(pdf_path)


def test_extract_text_uses_pdfminer_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "broken.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nbroken")

    monkeypatch.setattr("src.text_extract._extract_pdf_with_pdfminer", lambda path: "fallback text")

    class BrokenReader:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("primary parser failed")

    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, globals=None, locals=None, fromlist=(), level: int = 0):
        if name == "pypdf":
            class FakeModule:
                PdfReader = BrokenReader
            return FakeModule()
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert extract_text(pdf_path) == "fallback text"


def test_extract_text_detects_html_masquerading_as_pdf(tmp_path: Path) -> None:
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_text(
        "<!DOCTYPE html><html><head><title>Example</title></head><body>Springer Nature Link access no</body></html>",
        encoding="utf-8",
    )

    with pytest.raises(TextExtractionError, match="Source file is not a PDF"):
        extract_text(fake_pdf)


def test_suppress_pdf_library_noise_hides_stdout_and_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    with _suppress_pdf_library_noise():
        print("Ignoring wrong pointing object 6 0 (offset 0)")
        import sys

        print("EOF marker not found", file=sys.stderr)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
