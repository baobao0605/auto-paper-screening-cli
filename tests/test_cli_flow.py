from __future__ import annotations

from pathlib import Path

from src.cli import build_pipeline


def test_build_pipeline_resolves_base_dir_from_custom_config_path(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "input" / "local_papers").mkdir(parents=True, exist_ok=True)
    (tmp_path / "output").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "criteria_prompt.txt").write_text("criteria", encoding="utf-8")
    config_path = tmp_path / "config" / "settings.yaml"
    config_path.write_text(
        "\n".join(
            [
                "app:",
                "  name: aiscreening",
                "  prompt_version: \"v1\"",
                "  log_level: \"INFO\"",
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

    pipeline = build_pipeline(config_path)

    assert pipeline.settings.base_dir == tmp_path.resolve()
    assert pipeline.settings.input_dir == (tmp_path / "input" / "local_papers").resolve()
