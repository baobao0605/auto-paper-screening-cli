"""Factory for creating configured LLM providers."""

from __future__ import annotations

import os

from src.config import Settings
from src.gemini_client import GeminiClient
from src.providers.anthropic_provider import AnthropicProvider
from src.providers.base import LLMProvider
from src.providers.gemini_provider import GeminiProvider
from src.providers.openai_compatible_provider import OpenAICompatibleProvider


def create_provider(
    *,
    settings: Settings,
    provider_name: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> LLMProvider:
    """Build a provider instance with optional overrides."""

    chosen = (provider_name or settings.provider.name or "gemini").strip().casefold()
    if chosen in {"gemini", "google", "google_gemini"}:
        client = GeminiClient(
            api_key=api_key if api_key is not None else settings.gemini_api_key,
            model_name=model or settings.gemini.model,
            temperature=settings.gemini.temperature,
            max_output_tokens=settings.gemini.max_output_tokens,
            thinking_budget=settings.gemini.thinking_budget,
            request_max_retries=settings.gemini.request_max_retries,
            request_retry_delay_seconds=settings.gemini.request_retry_delay_seconds,
        )
        return GeminiProvider(client)

    if chosen == "openai_compatible":
        resolved_model = model or settings.openai_compatible.model
        resolved_base_url = base_url or settings.openai_compatible.base_url
        return OpenAICompatibleProvider(
            api_key=api_key if api_key is not None else settings.openai_compatible_api_key,
            base_url=resolved_base_url,
            model_name=resolved_model,
            timeout_seconds=settings.openai_compatible.timeout_seconds,
            request_max_retries=settings.openai_compatible.request_max_retries,
            request_retry_delay_seconds=settings.openai_compatible.request_retry_delay_seconds,
        )

    if chosen == "deepseek":
        resolved_model = model or settings.deepseek.model
        resolved_base_url = base_url or settings.deepseek.base_url
        resolved_key = api_key
        if resolved_key is None:
            resolved_key = settings.deepseek_api_key or os.getenv("DEEPSEEK_API_KEY")
        if resolved_key is None:
            resolved_key = settings.openai_compatible_api_key or os.getenv("OPENAI_COMPATIBLE_API_KEY")
        return OpenAICompatibleProvider(
            api_key=resolved_key,
            base_url=resolved_base_url,
            model_name=resolved_model,
            timeout_seconds=settings.deepseek.timeout_seconds,
            request_max_retries=settings.deepseek.request_max_retries,
            request_retry_delay_seconds=settings.deepseek.request_retry_delay_seconds,
        )

    if chosen in {"anthropic", "claude"}:
        resolved_key = api_key
        if resolved_key is None:
            resolved_key = settings.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        return AnthropicProvider(
            api_key=resolved_key,
            model_name=model or settings.anthropic.model,
            base_url=base_url or settings.anthropic.base_url,
            timeout_seconds=settings.anthropic.timeout_seconds,
            max_tokens=settings.anthropic.max_tokens,
            request_max_retries=settings.anthropic.request_max_retries,
            request_retry_delay_seconds=settings.anthropic.request_retry_delay_seconds,
        )

    supported = "gemini, google, google_gemini, openai_compatible, deepseek, anthropic, claude"
    raise ValueError(f"Unsupported provider '{provider_name}'. Supported providers: {supported}.")
