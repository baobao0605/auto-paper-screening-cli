"""Prompt file read/write helpers shared by CLI and GUI."""

from __future__ import annotations

from pathlib import Path


class PromptManagerError(ValueError):
    """Raised when prompt operations fail validation."""


class PromptManager:
    """Manage screening criteria prompt content on disk."""

    def __init__(self, default_prompt_path: Path) -> None:
        self.default_prompt_path = default_prompt_path

    def load_prompt(self, prompt_path: Path | None = None) -> str:
        path = prompt_path or self.default_prompt_path
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def save_prompt(self, prompt: str, prompt_path: Path | None = None) -> Path:
        self.validate_prompt(prompt)
        path = prompt_path or self.default_prompt_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(prompt, encoding="utf-8")
        return path

    @staticmethod
    def validate_prompt(prompt: str) -> None:
        if not isinstance(prompt, str):
            raise PromptManagerError("Prompt must be a string.")
        if not prompt.strip():
            raise PromptManagerError("Prompt must not be empty.")

