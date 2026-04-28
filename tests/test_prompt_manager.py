from __future__ import annotations

from pathlib import Path

import pytest

from src.prompt_manager import PromptManager, PromptManagerError


def test_prompt_manager_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "criteria_prompt.txt"
    manager = PromptManager(path)
    manager.save_prompt("第一行\nSecond line", path)
    assert manager.load_prompt(path) == "第一行\nSecond line"


def test_prompt_manager_rejects_empty_prompt(tmp_path: Path) -> None:
    manager = PromptManager(tmp_path / "prompt.txt")
    with pytest.raises(PromptManagerError, match="must not be empty"):
        manager.save_prompt("   ")

