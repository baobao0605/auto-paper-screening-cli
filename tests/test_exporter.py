from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from src.config import AppSettings, ExportSettings, FileSettings, GeminiSettings, PathsSettings, ScreeningSettings, Settings
from src.constants import PaperStatus
from src.db import get_connection, initialize_database
from src.exporter import Exporter
from src.repository import PaperRepository


def test_exporter_writes_exact_column_order(tmp_path: Path) -> None:
    settings = Settings(
        base_dir=tmp_path,
        gemini_api_key=None,
        app=AppSettings(),
        paths=PathsSettings(
            input_dir="input/local_papers",
            output_dir="output",
            database_path="data/app.db",
            full_excel_path="output/screening_log.xlsx",
            full_csv_path=None,
            criteria_prompt_path="config/criteria_prompt.txt",
        ),
        screening=ScreeningSettings(),
        gemini=GeminiSettings(),
        files=FileSettings(),
        export=ExportSettings(sheet_name="screening_log"),
    )
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "criteria_prompt.txt").write_text("criteria", encoding="utf-8")

    connection = get_connection(settings.database_path)
    initialize_database(connection)
    repository = PaperRepository(connection)
    logger = logging.getLogger("export-test")
    logger.handlers.clear()

    record = repository.register_discovered_paper(
        source_path=tmp_path / "paper.txt",
        source_type="local",
        file_name="paper.txt",
        file_ext=".txt",
        file_hash="hash",
        fallback_fingerprint="fallback",
        title="Paper title",
        doi="10.1000/demo",
    )
    repository.mark_done(
        record.paper_id,
        title="Paper title",
        doi="10.1000/demo",
        decision="MAYBE",
        exclude_reason="",
        construct="unclear",
        note="The full text is unclear on the measure details.",
        prompt_version="v1",
    )

    exporter = Exporter(
        repository,
        excel_path=settings.excel_path,
        csv_path=settings.csv_path,
        sheet_name=settings.export.sheet_name,
    )
    exporter.export()

    frame = pd.read_excel(settings.excel_path)
    assert list(frame.columns) == [
        "Title",
        "DOI",
        "Decision",
        "Exclude reason",
        "Construct",
        "Note",
    ]
    assert frame.iloc[0]["Decision"] == "MAYBE"


def test_exporter_regenerates_full_workbook_from_database(tmp_path: Path) -> None:
    settings = Settings(
        base_dir=tmp_path,
        gemini_api_key=None,
        app=AppSettings(),
        paths=PathsSettings(
            input_dir="input/local_papers",
            output_dir="output",
            database_path="data/app.db",
            full_excel_path="output/screening_log.xlsx",
            full_csv_path=None,
            criteria_prompt_path="config/criteria_prompt.txt",
        ),
        screening=ScreeningSettings(),
        gemini=GeminiSettings(),
        files=FileSettings(),
        export=ExportSettings(sheet_name="screening_log"),
    )
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "criteria_prompt.txt").write_text("criteria", encoding="utf-8")

    connection = get_connection(settings.database_path)
    initialize_database(connection)
    repository = PaperRepository(connection)

    first = repository.register_discovered_paper(
        source_path=tmp_path / "paper1.txt",
        source_type="local",
        file_name="paper1.txt",
        file_ext=".txt",
        file_hash="hash1",
        fallback_fingerprint="fallback1",
        title="Paper one",
        doi="10.1000/one",
    )
    second = repository.register_discovered_paper(
        source_path=tmp_path / "paper2.txt",
        source_type="local",
        file_name="paper2.txt",
        file_ext=".txt",
        file_hash="hash2",
        fallback_fingerprint="fallback2",
        title="Paper two",
        doi="10.1000/two",
    )
    repository.mark_done(
        first.paper_id,
        title="Paper one",
        doi="10.1000/one",
        decision="INCLUDE",
        exclude_reason="",
        construct="target construct",
        note="First row.",
        prompt_version="v1",
    )
    repository.mark_done(
        second.paper_id,
        title="Paper two",
        doi="10.1000/two",
        decision="EXCLUDE",
        exclude_reason="Wrong topic",
        construct="unclear",
        note="Second row.",
        prompt_version="v1",
    )

    exporter = Exporter(
        repository,
        excel_path=settings.excel_path,
        csv_path=settings.csv_path,
        sheet_name=settings.export.sheet_name,
    )
    exporter.export()
    repository.set_status(second.paper_id, PaperStatus.NEW)
    exporter.export()

    frame = pd.read_excel(settings.excel_path)
    assert len(frame.index) == 1
    assert frame.iloc[0]["Title"] == "Paper one"
