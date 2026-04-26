"""Main orchestration for scanning, screening, and exporting."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from src.config import Settings
from src.constants import PaperStatus
from src.exporter import Exporter
from src.file_discovery import discover_files
from src.fingerprint import compute_content_hash, compute_fallback_fingerprint, compute_file_hash
from src.gemini_client import GeminiClient
from src.metadata_extract import extract_metadata_from_filename, extract_metadata_from_text
from src.prompt_builder import build_prompt
from src.repository import PaperRecord, PaperRepository
from src.retry import get_queue_statuses
from src.state_manager import StateManager
from src.text_extract import TextExtractionError, extract_text
from src.validator import ModelOutputValidationError, validate_model_output


@dataclass(slots=True)
class ScanSummary:
    discovered: int
    registered: int
    duplicates: int


@dataclass(slots=True)
class RunSummary:
    queued: int
    done: int
    failed: int
    duplicates: int
    exported_rows: int


@dataclass(slots=True)
class RescreenSummary:
    requested: int
    found: int
    done: int
    failed: int
    missing: list[str]
    exported_rows: int


class ScreeningPipeline:
    """End-to-end local pipeline for full-text screening."""

    def __init__(
        self,
        *,
        settings: Settings,
        repository: PaperRepository,
        logger: logging.Logger,
        gemini_client: GeminiClient | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.logger = logger
        self.state_manager = StateManager(repository)
        self.criteria_prompt = settings.criteria_prompt_path.read_text(encoding="utf-8")
        self.gemini_client = gemini_client or GeminiClient(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini.model,
            temperature=settings.gemini.temperature,
            max_output_tokens=settings.gemini.max_output_tokens,
            thinking_budget=settings.gemini.thinking_budget,
            request_max_retries=settings.gemini.request_max_retries,
            request_retry_delay_seconds=settings.gemini.request_retry_delay_seconds,
        )
        self.exporter = Exporter(
            repository,
            excel_path=settings.excel_path,
            csv_path=settings.csv_path,
            sheet_name=settings.export.sheet_name,
        )

    def scan(self) -> ScanSummary:
        """Discover supported files and register them in SQLite."""

        files = discover_files(self.settings.input_dir, self.settings.files.allowed_extensions)
        registered = 0
        duplicates = 0

        for path in files:
            metadata = extract_metadata_from_filename(path)
            record = self.repository.register_discovered_paper(
                source_path=path.resolve(),
                source_type="local",
                file_name=path.name,
                file_ext=path.suffix.lower(),
                file_hash=compute_file_hash(path),
                fallback_fingerprint=compute_fallback_fingerprint(path),
                title=metadata.title,
                doi=metadata.doi,
            )
            registered += 1

            duplicate = self.repository.find_canonical_match(
                current_paper_id=record.paper_id,
                doi=record.doi,
                content_hash=record.content_hash,
                file_hash=record.file_hash,
                fallback_fingerprint=record.fallback_fingerprint,
            )
            if duplicate and duplicate.paper_id != record.paper_id:
                self.repository.mark_duplicate(record.paper_id, duplicate.paper_id)
                duplicates += 1

        return ScanSummary(discovered=len(files), registered=registered, duplicates=duplicates)

    def run(self, retry_only: bool = False) -> RunSummary:
        """Run screening over eligible papers and export the full Excel log."""

        recovered = self.state_manager.recover_stale_records()
        if recovered:
            self.logger.info("Recovered %s stale in-progress records.", recovered)

        self.scan()
        queue_limit = self.settings.screening.batch_size
        queue = self.repository.get_queue(
            get_queue_statuses(retry_only=retry_only),
            limit=queue_limit if queue_limit > 0 else None,
        )

        done = 0
        failed = 0
        duplicates = 0
        for paper in queue:
            outcome = self._process_paper(paper)
            if outcome == PaperStatus.DONE.value:
                done += 1
            elif outcome == PaperStatus.SKIPPED_DUPLICATE.value:
                duplicates += 1
            else:
                failed += 1

        exported_rows = self.exporter.export()
        return RunSummary(
            queued=len(queue),
            done=done,
            failed=failed,
            duplicates=duplicates,
            exported_rows=exported_rows,
        )

    def export(self) -> int:
        """Regenerate the full export from SQLite."""

        return self.exporter.export()

    def rescreen_by_dois(self, dois: list[str]) -> RescreenSummary:
        """Rescreen specific papers matched by DOI and overwrite their conclusions."""

        recovered = self.state_manager.recover_stale_records()
        if recovered:
            self.logger.info("Recovered %s stale in-progress records.", recovered)

        found = 0
        done = 0
        failed = 0
        missing: list[str] = []
        seen_paper_ids: set[int] = set()

        for doi in dois:
            target = self.repository.get_rescreen_target_by_doi(doi)
            if target is None:
                missing.append(doi)
                continue

            if target.paper_id in seen_paper_ids:
                found += 1
                continue

            seen_paper_ids.add(target.paper_id)
            found += 1
            outcome = self._process_paper(target)
            if outcome == PaperStatus.DONE.value:
                done += 1
            else:
                failed += 1

        exported_rows = self.exporter.export()
        return RescreenSummary(
            requested=len(dois),
            found=found,
            done=done,
            failed=failed,
            missing=missing,
            exported_rows=exported_rows,
        )

    def status(self) -> dict[str, int]:
        """Return a summary of current repository state."""

        return self.repository.get_status_summary()

    def _process_paper(self, paper: PaperRecord) -> str:
        """Process a single paper end to end."""

        path = self.settings.resolve_path(paper.source_path)
        try:
            text = extract_text(path)
        except (OSError, TextExtractionError) as exc:
            message = f"Text extraction failed: {exc}"
            self.repository.set_status(paper.paper_id, PaperStatus.TEXT_FAILED_RETRY, message)
            self.logger.error("%s | %s", paper.file_name, message)
            return PaperStatus.TEXT_FAILED_RETRY.value

        metadata = extract_metadata_from_text(text)
        title = metadata.title or paper.title or paper.file_name
        doi = metadata.doi or paper.doi or ""
        content_hash = compute_content_hash(text)

        self.repository.update_extracted_text_metadata(
            paper.paper_id,
            content_hash=content_hash,
            title=title,
            doi=doi,
        )

        duplicate = self.repository.find_canonical_match(
            current_paper_id=paper.paper_id,
            doi=doi,
            content_hash=content_hash,
            file_hash=paper.file_hash,
            fallback_fingerprint=paper.fallback_fingerprint,
        )
        if duplicate and duplicate.paper_id != paper.paper_id:
            self.repository.mark_duplicate(paper.paper_id, duplicate.paper_id)
            self.logger.info("%s marked as duplicate of paper_id=%s", paper.file_name, duplicate.paper_id)
            return PaperStatus.SKIPPED_DUPLICATE.value

        prompt = build_prompt(
            criteria_prompt=self.criteria_prompt,
            full_text=text,
            file_name=paper.file_name,
            title_hint=title,
            doi_hint=doi,
        )

        self.repository.set_status(paper.paper_id, PaperStatus.SCREENING)
        raw_response: str | None = None
        try:
            raw_response = self.gemini_client.screen(prompt)
            validated = validate_model_output(raw_response)
            self.repository.create_screening_run(
                paper_id=paper.paper_id,
                model_name=self.settings.gemini.model,
                prompt_version=self.settings.app.prompt_version,
                raw_response=raw_response if self.settings.screening.save_raw_response else None,
                parsed_ok=True,
            )
            payload = validated.to_db_payload()
            self.repository.mark_done(
                paper.paper_id,
                title=payload["Title"] or title,
                doi=payload["DOI"] or doi,
                decision=payload["Decision"],
                exclude_reason=payload["Exclude reason"],
                construct=payload["Construct"],
                note=payload["Note"],
                prompt_version=self.settings.app.prompt_version,
            )
            self.logger.info("%s screened successfully as %s", paper.file_name, payload["Decision"])
            return PaperStatus.DONE.value
        except (ModelOutputValidationError, Exception) as exc:
            raw_response = raw_response or getattr(exc, "raw_response", None)
            self.repository.create_screening_run(
                paper_id=paper.paper_id,
                model_name=self.settings.gemini.model,
                prompt_version=self.settings.app.prompt_version,
                raw_response=raw_response if self.settings.screening.save_raw_response else None,
                parsed_ok=False,
            )
            message = f"Screening failed: {exc}"
            self.repository.set_status(paper.paper_id, PaperStatus.SCREEN_FAILED_RETRY, message)
            self.logger.error("%s | %s", paper.file_name, message)
            return PaperStatus.SCREEN_FAILED_RETRY.value
