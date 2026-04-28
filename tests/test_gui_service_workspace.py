from __future__ import annotations

from pathlib import Path

from src.gui_service import CancelToken, GuiScreeningService, RuntimeOverrides
from src.screener import RunSummary


def _write_settings(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "criteria_prompt.txt").write_text("criteria", encoding="utf-8")
    (tmp_path / "config" / "settings.yaml").write_text(
        "\n".join(
            [
                "app:",
                "  name: aiscreening",
                "paths:",
                "  input_dir: \"input/local_papers\"",
                "  output_dir: \"output\"",
                "  database_path: \"data/app.db\"",
                "  full_excel_path: \"output/screening_log.xlsx\"",
                "  full_csv_path: \"output/screening_log.csv\"",
                "  criteria_prompt_path: \"config/criteria_prompt.txt\"",
            ]
        ),
        encoding="utf-8",
    )
    return tmp_path / "config" / "settings.yaml"


def _overrides(input_dir: Path, mode: str = "start") -> RuntimeOverrides:
    return RuntimeOverrides(
        input_dir=str(input_dir),
        provider_name="gemini",
        api_key="dummy",
        model="gemini-2.5-flash",
        base_url="",
        prompt_text="criteria",
        prompt_path=str(input_dir.parent.parent / "config" / "criteria_prompt.txt"),
        run_mode=mode,
    )


def test_workspace_paths_differ_by_input_dir(tmp_path: Path) -> None:
    settings_path = _write_settings(tmp_path)
    service = GuiScreeningService(settings_path)
    a = tmp_path / "input" / "A"
    b = tmp_path / "input" / "B"
    a.mkdir(parents=True, exist_ok=True)
    b.mkdir(parents=True, exist_ok=True)
    ws_a = service.project_workspace(input_dir=str(a))
    ws_b = service.project_workspace(input_dir=str(b))
    assert ws_a.database_path != ws_b.database_path
    assert ws_a.excel_path != ws_b.excel_path


def test_auto_start_runs_retry_then_new_only(monkeypatch, tmp_path: Path) -> None:
    settings_path = _write_settings(tmp_path)
    service = GuiScreeningService(settings_path)
    input_dir = tmp_path / "input" / "A"
    input_dir.mkdir(parents=True, exist_ok=True)

    calls: list[str] = []

    def fake_run_mode(*args, **kwargs):  # noqa: ANN001
        mode = args[1]
        calls.append(mode)
        return RunSummary(queued=1, done=1, failed=0, duplicates=0, exported_rows=1)

    monkeypatch.setattr(service, "_build_pipeline", lambda settings, overrides: object())
    monkeypatch.setattr(service, "_run_mode", fake_run_mode)
    monkeypatch.setattr(service, "_persist_prompt", lambda prompt_text, prompt_path: Path(prompt_path))
    monkeypatch.setattr(service, "_write_snapshots", lambda workspace, overrides: None)
    service.run_screening(overrides=_overrides(input_dir, "auto_start"))
    assert calls == ["retry_failed", "new_only"]


def test_auto_start_stops_after_phase1_cancel(monkeypatch, tmp_path: Path) -> None:
    settings_path = _write_settings(tmp_path)
    service = GuiScreeningService(settings_path)
    input_dir = tmp_path / "input" / "A"
    input_dir.mkdir(parents=True, exist_ok=True)
    token = CancelToken()
    calls: list[str] = []

    def fake_run_mode(*args, **kwargs):  # noqa: ANN001
        mode = args[1]
        calls.append(mode)
        token.cancel()
        return RunSummary(queued=1, done=0, failed=1, duplicates=0, exported_rows=0)

    monkeypatch.setattr(service, "_build_pipeline", lambda settings, overrides: object())
    monkeypatch.setattr(service, "_run_mode", fake_run_mode)
    monkeypatch.setattr(service, "_persist_prompt", lambda prompt_text, prompt_path: Path(prompt_path))
    monkeypatch.setattr(service, "_write_snapshots", lambda workspace, overrides: None)
    service.run_screening(overrides=_overrides(input_dir, "auto_start"), cancel_token=token)
    assert calls == ["retry_failed"]


def test_retry_failed_mode_uses_retry_phase(monkeypatch, tmp_path: Path) -> None:
    settings_path = _write_settings(tmp_path)
    service = GuiScreeningService(settings_path)
    input_dir = tmp_path / "input" / "A"
    input_dir.mkdir(parents=True, exist_ok=True)
    calls: list[str] = []

    def fake_run_mode(*args, **kwargs):  # noqa: ANN001
        mode = args[1]
        calls.append(mode)
        return RunSummary(queued=0, done=0, failed=0, duplicates=0, exported_rows=0)

    monkeypatch.setattr(service, "_build_pipeline", lambda settings, overrides: object())
    monkeypatch.setattr(service, "_run_mode", fake_run_mode)
    monkeypatch.setattr(service, "_persist_prompt", lambda prompt_text, prompt_path: Path(prompt_path))
    monkeypatch.setattr(service, "_write_snapshots", lambda workspace, overrides: None)
    service.run_screening(overrides=_overrides(input_dir, "retry_failed"))
    assert calls == ["retry_failed"]
