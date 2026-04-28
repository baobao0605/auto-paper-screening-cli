from __future__ import annotations

from pathlib import Path

import pytest

from src.config import (
    AppSettings,
    AnthropicSettings,
    DeepSeekSettings,
    ExportSettings,
    FileSettings,
    GeminiSettings,
    OpenAICompatibleSettings,
    PathsSettings,
    ProviderSettings,
    ScreeningSettings,
    Settings,
)
from src.providers.factory import create_provider
from src.providers.gemini_provider import GeminiProvider
from src.providers.openai_compatible_provider import OpenAICompatibleProvider


def _build_settings(tmp_path: Path) -> Settings:
    return Settings(
        base_dir=tmp_path,
        gemini_api_key="gemini-key",
        openai_compatible_api_key="openai-key",
        deepseek_api_key=None,
        anthropic_api_key=None,
        app=AppSettings(),
        paths=PathsSettings(criteria_prompt_path="config/criteria_prompt.txt"),
        screening=ScreeningSettings(),
        provider=ProviderSettings(name="gemini"),
        gemini=GeminiSettings(),
        openai_compatible=OpenAICompatibleSettings(
            base_url="https://example.com/v1",
            model="demo-model",
            timeout_seconds=30.0,
            request_max_retries=2,
            request_retry_delay_seconds=0.1,
        ),
        deepseek=DeepSeekSettings(),
        anthropic=AnthropicSettings(),
        files=FileSettings(),
        export=ExportSettings(),
    )


def test_create_provider_gemini(tmp_path: Path) -> None:
    provider = create_provider(settings=_build_settings(tmp_path), provider_name="GEMINI")
    assert isinstance(provider, GeminiProvider)


def test_create_provider_google_aliases_to_gemini(tmp_path: Path) -> None:
    provider = create_provider(settings=_build_settings(tmp_path), provider_name="google_gemini")
    assert isinstance(provider, GeminiProvider)


def test_create_provider_openai_compatible(tmp_path: Path) -> None:
    provider = create_provider(settings=_build_settings(tmp_path), provider_name="openai_compatible")
    assert isinstance(provider, OpenAICompatibleProvider)


def test_create_provider_deepseek_uses_openai_compatible_provider(tmp_path: Path) -> None:
    provider = create_provider(settings=_build_settings(tmp_path), provider_name="DEEPSEEK")
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.base_url == "https://api.deepseek.com"
    assert provider.model_name == "deepseek-chat"


def test_create_provider_deepseek_explicit_base_url_has_priority(tmp_path: Path) -> None:
    provider = create_provider(
        settings=_build_settings(tmp_path),
        provider_name="deepseek",
        base_url="https://proxy.local/v1",
    )
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.base_url == "https://proxy.local/v1"


def test_create_provider_deepseek_uses_env_api_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-env")
    provider = create_provider(settings=_build_settings(tmp_path), provider_name="deepseek")
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.api_key == "from-env"


def test_create_provider_anthropic_aliases(tmp_path: Path) -> None:
    anthropic_provider = create_provider(settings=_build_settings(tmp_path), provider_name="anthropic")
    claude_provider = create_provider(settings=_build_settings(tmp_path), provider_name="claude")
    from src.providers.anthropic_provider import AnthropicProvider

    assert isinstance(anthropic_provider, AnthropicProvider)
    assert isinstance(claude_provider, AnthropicProvider)


def test_create_provider_anthropic_uses_env_api_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthro-env-key")
    from src.providers.anthropic_provider import AnthropicProvider

    provider = create_provider(settings=_build_settings(tmp_path), provider_name="anthropic")
    assert isinstance(provider, AnthropicProvider)
    assert provider.api_key == "anthro-env-key"


def test_create_provider_rejects_unknown_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported provider"):
        create_provider(settings=_build_settings(tmp_path), provider_name="unknown")
