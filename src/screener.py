"""Main orchestration for scanning, screening, and exporting."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import Callable

from src.config import Settings
from src.constants import PaperStatus
from src.exporter import Exporter
from src.file_discovery import discover_files
from src.fingerprint import compute_content_hash, compute_fallback_fingerprint, compute_file_hash
from src.metadata_extract import extract_metadata_from_filename, extract_metadata_from_text
from src.prompt_builder import build_prompt
from src.providers.base import LLMProvider
from src.providers.factory import create_provider
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
        llm_provider: LLMProvider | None = None,
        gemini_client: object | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.logger = logger
        self.state_manager = StateManager(repository)
        self.criteria_prompt = settings.criteria_prompt_path.read_text(encoding="utf-8")
        self.llm_provider = llm_provider or gemini_client or create_provider(settings=settings)
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

    def run(
        self,
        retry_only: bool = False,
        *,
        statuses_override: tuple[PaperStatus, ...] | None = None,
        should_cancel: Callable[[], bool] | None = None,
        on_log: Callable[[str], None] | None = None,
        on_started: Callable[[dict[str, int]], None] | None = None,
        on_paper_started: Callable[[dict[str, str]], None] | None = None,
        on_paper_finished: Callable[[dict[str, str]], None] | None = None,
        on_paper_error: Callable[[dict[str, str]], None] | None = None,
        on_finished: Callable[[RunSummary], None] | None = None,
        on_cancelled: Callable[[RunSummary], None] | None = None,
    ) -> RunSummary:
        """Run screening over eligible papers and export the full Excel log."""

        recovered = self.state_manager.recover_stale_records()
        if recovered:
            self.logger.info("Recovered %s stale in-progress records.", recovered)

        self.scan()
        queue_limit = self.settings.screening.batch_size
        statuses = statuses_override or get_queue_statuses(retry_only=retry_only)
        queue = self.repository.get_queue(
            statuses,
            limit=queue_limit if queue_limit > 0 else None,
        )
        if on_started is not None:
            on_started({"total_count": len(queue)})

        done = 0
        failed = 0
        duplicates = 0
        cancelled = False
        for paper in queue:
            if should_cancel is not None and should_cancel():
                cancelled = True
                if on_log is not None:
                    on_log("Cancellation requested. Stopping before next paper.")
                break
            started_at = time.perf_counter()
            if on_paper_started is not None:
                on_paper_started({"file_name": paper.file_name, "paper_id": str(paper.paper_id)})
            outcome = self._process_paper(paper)
            elapsed = time.perf_counter() - started_at
            if outcome == PaperStatus.DONE.value:
                done += 1
                if on_paper_finished is not None:
                    on_paper_finished(
                        {
                            "file_name": paper.file_name,
                            "paper_id": str(paper.paper_id),
                            "status": "Done",
                            "elapsed_seconds": f"{elapsed:.2f}",
                        }
                    )
            elif outcome == PaperStatus.SKIPPED_DUPLICATE.value:
                duplicates += 1
                if on_paper_finished is not None:
                    on_paper_finished(
                        {
                            "file_name": paper.file_name,
                            "paper_id": str(paper.paper_id),
                            "status": "Skipped",
                            "elapsed_seconds": f"{elapsed:.2f}",
                        }
                    )
            else:
                failed += 1
                if on_paper_error is not None:
                    record = self.repository.get_by_id(paper.paper_id)
                    on_paper_error(
                        {
                            "file_name": paper.file_name,
                            "paper_id": str(paper.paper_id),
                            "status": "Error",
                            "error": record.last_error if record and record.last_error else "Unknown error",
                            "elapsed_seconds": f"{elapsed:.2f}",
                        }
                    )

        exported_rows = self.exporter.export()
        summary = RunSummary(
            queued=len(queue),
            done=done,
            failed=failed,
            duplicates=duplicates,
            exported_rows=exported_rows,
        )
        if cancelled:
            if on_cancelled is not None:
                on_cancelled(summary)
        elif on_finished is not None:
            on_finished(summary)
        return summary

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
        provider_name = getattr(self.llm_provider, "provider_name", "unknown")
        model_name = getattr(self.llm_provider, "model_name", self.settings.gemini.model)
        screening_model = f"{provider_name} / {model_name}"
        try:
            raw_response = self.llm_provider.screen(prompt)
            validated = validate_model_output(raw_response)
            self.repository.create_screening_run(
                paper_id=paper.paper_id,
                model_name=model_name,
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
                screening_model=screening_model,
                prompt_version=self.settings.app.prompt_version,
            )
            self.logger.info("%s screened successfully as %s", paper.file_name, payload["Decision"])
            return PaperStatus.DONE.value
        except (ModelOutputValidationError, Exception) as exc:
            raw_response = raw_response or getattr(exc, "raw_response", None)
            self.repository.create_screening_run(
                paper_id=paper.paper_id,
                model_name=model_name,
                prompt_version=self.settings.app.prompt_version,
                raw_response=raw_response if self.settings.screening.save_raw_response else None,
                parsed_ok=False,
            )
            message = f"Screening failed: {exc}"
            self.repository.set_status(paper.paper_id, PaperStatus.SCREEN_FAILED_RETRY, message)
            self.logger.error("%s | %s", paper.file_name, message)
            return PaperStatus.SCREEN_FAILED_RETRY.value
