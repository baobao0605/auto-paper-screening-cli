from __future__ import annotations

import logging
from pathlib import Path

from src.config import AppSettings, ExportSettings, FileSettings, GeminiSettings, PathsSettings, ScreeningSettings, Settings
from src.constants import PaperStatus
from src.db import get_connection, initialize_database
from src.repository import PaperRepository
from src.screener import ScreeningPipeline
from src.state_manager import StateManager


VALID_RESPONSE = """
{
  "Title": "Sample quantitative study",
  "DOI": "10.1000/test",
  "Decision": "INCLUDE",
  "Exclude reason": "",
  "Construct": "target construct",
  "Note": "The paper reports quantitative analyses for the target construct."
}
""".strip()


class FakeGeminiClient:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.prompts: list[str] = []

    def screen(self, prompt: str) -> str:
        assert "BEGIN FULL TEXT" in prompt
        self.prompts.append(prompt)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return str(response)


def build_settings(base_dir: Path) -> Settings:
    (base_dir / "config").mkdir(parents=True, exist_ok=True)
    (base_dir / "input" / "local_papers").mkdir(parents=True, exist_ok=True)
    (base_dir / "output").mkdir(parents=True, exist_ok=True)
    (base_dir / "config" / "criteria_prompt.txt").write_text("Use the provided criteria.", encoding="utf-8")
    return Settings(
        base_dir=base_dir,
        gemini_api_key="test-key",
        app=AppSettings(prompt_version="v1", log_level="INFO"),
        paths=PathsSettings(
            input_dir="input/local_papers",
            output_dir="output",
            database_path="data/app.db",
            full_excel_path="output/screening_log.xlsx",
            full_csv_path="output/screening_log.csv",
            criteria_prompt_path="config/criteria_prompt.txt",
        ),
        screening=ScreeningSettings(batch_size=0, skip_done=True, retry_failed=True, save_raw_response=True),
        gemini=GeminiSettings(model="gemini-test", temperature=0.0, max_output_tokens=256),
        files=FileSettings(allowed_extensions=[".txt"]),
        export=ExportSettings(sheet_name="screening_log"),
    )


def build_pipeline(base_dir: Path, responses: list[object]) -> tuple[ScreeningPipeline, PaperRepository, FakeGeminiClient]:
    settings = build_settings(base_dir)
    connection = get_connection(settings.database_path)
    initialize_database(connection)
    repository = PaperRepository(connection)
    logger = logging.getLogger(f"test-{base_dir.name}")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.INFO)
    fake_client = FakeGeminiClient(responses)
    pipeline = ScreeningPipeline(
        settings=settings,
        repository=repository,
        logger=logger,
        gemini_client=fake_client,
    )
    return pipeline, repository, fake_client


def test_run_skips_done_manual_and_duplicate(tmp_path: Path) -> None:
    pipeline, repository, _ = build_pipeline(tmp_path, [VALID_RESPONSE, VALID_RESPONSE])
    paper_dir = tmp_path / "input" / "local_papers"

    paths = []
    for index in range(5):
        paper = paper_dir / f"paper_{index}.txt"
        paper.write_text(f"full text for paper {index}", encoding="utf-8")
        paths.append(paper)

    pipeline.scan()
    records = [repository.get_by_source_path(path) for path in paths]
    assert all(record is not None for record in records)

    repository.set_status(records[0].paper_id, PaperStatus.DONE)
    repository.set_status(records[1].paper_id, PaperStatus.MANUAL_DONE)
    repository.set_status(records[2].paper_id, PaperStatus.SKIPPED_DUPLICATE)
    repository.set_status(records[3].paper_id, PaperStatus.TEXT_FAILED_RETRY)
    repository.set_status(records[4].paper_id, PaperStatus.NEW)

    summary = pipeline.run()

    assert summary.queued == 2
    assert summary.done == 2
    assert repository.get_by_id(records[0].paper_id).status == PaperStatus.DONE.value
    assert repository.get_by_id(records[1].paper_id).status == PaperStatus.MANUAL_DONE.value
    assert repository.get_by_id(records[2].paper_id).status == PaperStatus.SKIPPED_DUPLICATE.value


def test_recover_stale_records_moves_rows_into_retryable_statuses(tmp_path: Path) -> None:
    pipeline, repository, _ = build_pipeline(tmp_path, [])
    paper_dir = tmp_path / "input" / "local_papers"

    first = paper_dir / "first.txt"
    second = paper_dir / "second.txt"
    first.write_text("first text", encoding="utf-8")
    second.write_text("second text", encoding="utf-8")

    first_record = repository.register_discovered_paper(
        source_path=first,
        source_type="local",
        file_name=first.name,
        file_ext=first.suffix,
        file_hash="a",
        fallback_fingerprint="fa",
        title="first",
        doi=None,
    )
    second_record = repository.register_discovered_paper(
        source_path=second,
        source_type="local",
        file_name=second.name,
        file_ext=second.suffix,
        file_hash="b",
        fallback_fingerprint="fb",
        title="second",
        doi=None,
    )
    repository.set_status(first_record.paper_id, PaperStatus.TEXT_EXTRACTED)
    repository.set_status(second_record.paper_id, PaperStatus.SCREENING)

    recovered = StateManager(repository).recover_stale_records()

    assert recovered == 2
    assert repository.get_by_id(first_record.paper_id).status == PaperStatus.TEXT_FAILED_RETRY.value
    assert repository.get_by_id(second_record.paper_id).status == PaperStatus.SCREEN_FAILED_RETRY.value
    assert pipeline.status()["failed"] == 2


def test_completed_result_persists_when_later_item_fails(tmp_path: Path) -> None:
    pipeline, repository, _ = build_pipeline(tmp_path, [VALID_RESPONSE, "not json"])
    paper_dir = tmp_path / "input" / "local_papers"

    first = paper_dir / "first.txt"
    second = paper_dir / "second.txt"
    first.write_text("quantitative study of target construct", encoding="utf-8")
    second.write_text("another quantitative study of target construct", encoding="utf-8")

    summary = pipeline.run()

    assert summary.queued == 2
    statuses = {record.file_name: record.status for record in repository.get_queue((PaperStatus.DONE, PaperStatus.SCREEN_FAILED_RETRY), None)}
    assert statuses["first.txt"] == PaperStatus.DONE.value
    assert statuses["second.txt"] == PaperStatus.SCREEN_FAILED_RETRY.value
    assert repository.get_export_rows()[0]["Decision"] == "INCLUDE"
    assert summary.exported_rows == 1


def test_second_run_does_not_rescreen_done_items(tmp_path: Path) -> None:
    pipeline, repository, fake_client = build_pipeline(tmp_path, [VALID_RESPONSE])
    paper_dir = tmp_path / "input" / "local_papers"

    paper = paper_dir / "done_once.txt"
    paper.write_text("quantitative study of target construct", encoding="utf-8")

    first_summary = pipeline.run()
    second_summary = pipeline.run()

    record = repository.get_by_source_path(paper)
    assert record is not None
    assert first_summary.queued == 1
    assert second_summary.queued == 0
    assert second_summary.done == 0
    assert record.status == PaperStatus.DONE.value
    assert len(fake_client.prompts) == 1


def test_pipeline_uses_criteria_prompt_file_in_screening_prompt(tmp_path: Path) -> None:
    pipeline, _, fake_client = build_pipeline(tmp_path, [VALID_RESPONSE])
    criteria_path = tmp_path / "config" / "criteria_prompt.txt"
    expected_line = "CUSTOM CRITERIA LINE FOR TESTING"
    criteria_path.write_text(expected_line, encoding="utf-8")
    pipeline.criteria_prompt = criteria_path.read_text(encoding="utf-8")

    paper = tmp_path / "input" / "local_papers" / "prompt_check.txt"
    paper.write_text("quantitative study of target construct", encoding="utf-8")

    pipeline.run()

    assert fake_client.prompts
    assert expected_line in fake_client.prompts[0]


def test_rescreen_by_doi_overwrites_existing_conclusion(tmp_path: Path) -> None:
    pipeline, repository, _ = build_pipeline(tmp_path, [VALID_RESPONSE])
    paper = tmp_path / "input" / "local_papers" / "rescreen_target.txt"
    paper.write_text("quantitative study of target construct", encoding="utf-8")

    first_summary = pipeline.run()
    assert first_summary.done == 1

    record = repository.get_by_source_path(paper)
    assert record is not None
    repository.mark_done(
        record.paper_id,
        title="Old title",
        doi="10.1000/test",
        decision="EXCLUDE",
        exclude_reason="Wrong topic",
        construct="unclear",
        note="Old note.",
        prompt_version="v-old",
    )

    summary = pipeline.rescreen_by_dois(["10.1000/test"])
    updated = repository.get_by_id(record.paper_id)

    assert summary.requested == 1
    assert summary.found == 1
    assert summary.done == 1
    assert summary.failed == 0
    assert updated is not None
    assert updated.decision == "INCLUDE"
    assert updated.exclude_reason == ""
    assert updated.prompt_version == "v1"
