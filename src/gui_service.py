"""GUI-facing service layer with per-input project workspace isolation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Callable

from src.config import Settings, load_settings
from src.constants import PaperStatus
from src.db import get_connection, initialize_database
from src.logger import configure_logging
from src.project_workspace import (
    ProjectWorkspace,
    clear_project_workspace,
    ensure_project_workspace,
    get_project_workspace,
)
from src.prompt_manager import PromptManager
from src.providers.factory import create_provider
from src.repository import PaperRepository
from src.screener import RunSummary, ScreeningPipeline


@dataclass(slots=True)
class RuntimeOverrides:
    input_dir: str
    provider_name: str
    api_key: str
    model: str
    base_url: str
    prompt_text: str
    prompt_path: str
    run_mode: str = "start"


class CancelToken:
    """Cooperative cancellation token for GUI runs."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


class GuiScreeningService:
    """Runtime facade around ScreeningPipeline for the desktop app."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path.resolve() if config_path else None
        self.base_dir = self._resolve_base_dir(self.config_path)
        self.base_settings = load_settings(self.base_dir, config_path=self.config_path)

    def _resolve_base_dir(self, config_path: Path | None) -> Path:
        if config_path is None:
            return Path.cwd()
        if config_path.parent.name.casefold() == "config":
            return config_path.parent.parent
        return config_path.parent

    def _workspace(self, input_dir: str) -> ProjectWorkspace:
        return ensure_project_workspace(input_dir, output_root=self.base_settings.output_dir)

    def _build_runtime_settings(self, overrides: RuntimeOverrides) -> tuple[Settings, ProjectWorkspace]:
        settings = self.base_settings.model_copy(deep=True)
        workspace = self._workspace(overrides.input_dir)
        settings.paths.input_dir = str(workspace.input_dir)
        settings.paths.output_dir = str(workspace.root_dir)
        settings.paths.database_path = str(workspace.database_path)
        settings.paths.full_excel_path = str(workspace.excel_path)
        settings.paths.full_csv_path = str(workspace.csv_path)
        settings.paths.criteria_prompt_path = overrides.prompt_path
        return settings, workspace

    def _persist_prompt(self, prompt_text: str, prompt_path: str) -> Path:
        manager = PromptManager(default_prompt_path=Path(prompt_path))
        return manager.save_prompt(prompt_text, prompt_path=Path(prompt_path))

    def _write_snapshots(self, workspace: ProjectWorkspace, overrides: RuntimeOverrides) -> None:
        workspace.prompt_snapshot_path.write_text(overrides.prompt_text, encoding="utf-8")
        snapshot = {
            "input_dir": str(workspace.input_dir),
            "project_id": workspace.project_id,
            "provider": overrides.provider_name,
            "model": overrides.model,
            "base_url": overrides.base_url,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "mode": overrides.run_mode,
        }
        workspace.settings_snapshot_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _build_pipeline(self, settings: Settings, overrides: RuntimeOverrides) -> ScreeningPipeline:
        logger = configure_logging(settings.output_dir, settings.app.log_level)
        connection = get_connection(settings.database_path)
        initialize_database(connection)
        repository = PaperRepository(connection)
        provider = create_provider(
            settings=settings,
            provider_name=overrides.provider_name,
            api_key=overrides.api_key or None,
            model=overrides.model or None,
            base_url=overrides.base_url or None,
        )
        pipeline = ScreeningPipeline(
            settings=settings,
            repository=repository,
            logger=logger,
            llm_provider=provider,
        )
        pipeline.criteria_prompt = overrides.prompt_text
        return pipeline

    def _run_mode(
        self,
        pipeline: ScreeningPipeline,
        mode: str,
        cancel_token: CancelToken | None,
        on_log: Callable[[str], None] | None,
        on_started: Callable[[dict[str, int]], None] | None,
        on_paper_started: Callable[[dict[str, str]], None] | None,
        on_paper_finished: Callable[[dict[str, str]], None] | None,
        on_paper_error: Callable[[dict[str, str]], None] | None,
        on_finished: Callable[[RunSummary], None] | None,
        on_cancelled: Callable[[RunSummary], None] | None,
    ) -> RunSummary:
        should_cancel = cancel_token.is_cancelled if cancel_token is not None else None
        if mode == "retry_failed":
            return pipeline.run(
                retry_only=True,
                should_cancel=should_cancel,
                on_log=on_log,
                on_started=on_started,
                on_paper_started=on_paper_started,
                on_paper_finished=on_paper_finished,
                on_paper_error=on_paper_error,
                on_finished=on_finished,
                on_cancelled=on_cancelled,
            )
        if mode == "new_only":
            return pipeline.run(
                statuses_override=(PaperStatus.NEW,),
                should_cancel=should_cancel,
                on_log=on_log,
                on_started=on_started,
                on_paper_started=on_paper_started,
                on_paper_finished=on_paper_finished,
                on_paper_error=on_paper_error,
                on_finished=on_finished,
                on_cancelled=on_cancelled,
            )
        return pipeline.run(
            retry_only=False,
            should_cancel=should_cancel,
            on_log=on_log,
            on_started=on_started,
            on_paper_started=on_paper_started,
            on_paper_finished=on_paper_finished,
            on_paper_error=on_paper_error,
            on_finished=on_finished,
            on_cancelled=on_cancelled,
        )

    def run_screening(
        self,
        *,
        overrides: RuntimeOverrides,
        cancel_token: CancelToken | None = None,
        on_log: Callable[[str], None] | None = None,
        on_started: Callable[[dict[str, int]], None] | None = None,
        on_paper_started: Callable[[dict[str, str]], None] | None = None,
        on_paper_finished: Callable[[dict[str, str]], None] | None = None,
        on_paper_error: Callable[[dict[str, str]], None] | None = None,
        on_finished: Callable[[RunSummary], None] | None = None,
        on_cancelled: Callable[[RunSummary], None] | None = None,
    ) -> RunSummary:
        settings, workspace = self._build_runtime_settings(overrides)
        self._persist_prompt(overrides.prompt_text, overrides.prompt_path)
        self._write_snapshots(workspace, overrides)
        pipeline = self._build_pipeline(settings, overrides)
        if on_log is not None:
            on_log(
                f"Project={workspace.project_id} provider={overrides.provider_name} model={overrides.model} mode={overrides.run_mode}"
            )
        mode = overrides.run_mode
        if mode == "auto_start":
            if on_log is not None:
                on_log("Auto Start phase 1/2: retry failed papers...")
            phase1 = self._run_mode(
                pipeline,
                "retry_failed",
                cancel_token,
                on_log,
                on_started,
                on_paper_started,
                on_paper_finished,
                on_paper_error,
                None,
                None,
            )
            if cancel_token is not None and cancel_token.is_cancelled():
                if on_cancelled is not None:
                    on_cancelled(phase1)
                return phase1
            if on_log is not None:
                on_log("Auto Start phase 2/2: screen new papers...")
            phase2 = self._run_mode(
                pipeline,
                "new_only",
                cancel_token,
                on_log,
                on_started,
                on_paper_started,
                on_paper_finished,
                on_paper_error,
                on_finished,
                on_cancelled,
            )
            if on_log is not None:
                on_log("Auto Start finished.")
            return RunSummary(
                queued=phase1.queued + phase2.queued,
                done=phase1.done + phase2.done,
                failed=phase1.failed + phase2.failed,
                duplicates=phase1.duplicates + phase2.duplicates,
                exported_rows=phase2.exported_rows,
            )

        return self._run_mode(
            pipeline,
            mode,
            cancel_token,
            on_log,
            on_started,
            on_paper_started,
            on_paper_finished,
            on_paper_error,
            on_finished,
            on_cancelled,
        )

    def export(self, *, input_dir: str) -> int:
        overrides = RuntimeOverrides(
            input_dir=input_dir,
            provider_name=self.base_settings.provider.name,
            api_key="",
            model=self.base_settings.gemini.model,
            base_url="",
            prompt_text=PromptManager(self.base_settings.criteria_prompt_path).load_prompt(),
            prompt_path=str(self.base_settings.criteria_prompt_path),
        )
        settings, _ = self._build_runtime_settings(overrides)
        pipeline = self._build_pipeline(settings, overrides)
        return pipeline.export()

    def status(self, *, input_dir: str) -> dict[str, int]:
        overrides = RuntimeOverrides(
            input_dir=input_dir,
            provider_name=self.base_settings.provider.name,
            api_key="",
            model=self.base_settings.gemini.model,
            base_url="",
            prompt_text=PromptManager(self.base_settings.criteria_prompt_path).load_prompt(),
            prompt_path=str(self.base_settings.criteria_prompt_path),
        )
        settings, _ = self._build_runtime_settings(overrides)
        pipeline = self._build_pipeline(settings, overrides)
        return pipeline.status()

    def list_table_rows(self, *, input_dir: str, limit: int = 500) -> list[dict[str, str]]:
        overrides = RuntimeOverrides(
            input_dir=input_dir,
            provider_name=self.base_settings.provider.name,
            api_key="",
            model=self.base_settings.gemini.model,
            base_url="",
            prompt_text=PromptManager(self.base_settings.criteria_prompt_path).load_prompt(),
            prompt_path=str(self.base_settings.criteria_prompt_path),
        )
        settings, _ = self._build_runtime_settings(overrides)
        pipeline = self._build_pipeline(settings, overrides)
        return pipeline.repository.get_paper_table_rows(limit=limit)

    def project_workspace(self, *, input_dir: str) -> ProjectWorkspace:
        return get_project_workspace(input_dir, output_root=self.base_settings.output_dir)

    def clear_project_history(self, *, input_dir: str) -> None:
        clear_project_workspace(input_dir, output_root=self.base_settings.output_dir)
