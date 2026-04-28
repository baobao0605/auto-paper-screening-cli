"""Gemini provider wrapper."""

from __future__ import annotations

from src.gemini_client import GeminiClient


class GeminiProvider:
    """Provider adapter backed by the existing Gemini client."""

    provider_name = "gemini"

    def __init__(self, client: GeminiClient) -> None:
        self._client = client
        self.model_name = client.model_name

    def screen(self, prompt: str) -> str:
        return self._client.screen(prompt)

