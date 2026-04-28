"""Shared provider interfaces for LLM-backed screening."""

from __future__ import annotations

from typing import Protocol


class LLMProvider(Protocol):
    """Minimal provider contract used by the screening pipeline."""

    provider_name: str
    model_name: str

    def screen(self, prompt: str) -> str:
        """Submit a screening prompt and return raw text output."""

