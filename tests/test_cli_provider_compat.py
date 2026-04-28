from __future__ import annotations

from pathlib import Path

import pytest

from src.cli import build_pipeline, main
import src.cli
import src.main
from src.providers.gemini_provider import GeminiProvider


def test_cli_help_still_runs() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_cli_modules_importable() -> None:
    assert src.main is not None
    assert src.cli is not None


def test_build_pipeline_defaults_to_gemini_provider(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "input" / "local_papers").mkdir(parents=True, exist_ok=True)
    (tmp_path / "output").mkdir(parents=True, exist_ok=True)
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

    pipeline = build_pipeline(tmp_path / "config" / "settings.yaml")
    assert isinstance(pipeline.llm_provider, GeminiProvider)
