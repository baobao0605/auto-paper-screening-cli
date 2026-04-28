from __future__ import annotations

import json
from urllib import error

import pytest

from src.providers.anthropic_provider import AnthropicProvider, AnthropicProviderError


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def _provider() -> AnthropicProvider:
    return AnthropicProvider(
        api_key="k",
        model_name="claude-test",
        base_url="https://api.anthropic.com",
        timeout_seconds=3.0,
        max_tokens=128,
        request_max_retries=2,
        request_retry_delay_seconds=0.0,
    )


def test_anthropic_provider_extracts_text(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout):  # noqa: ANN001
        assert timeout == 3.0
        return _FakeResponse({"content": [{"type": "text", "text": "hello"}]})

    monkeypatch.setattr("src.providers.anthropic_provider.request.urlopen", fake_urlopen)
    assert _provider().screen("prompt") == "hello"


def test_anthropic_provider_joins_multiple_text_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout):  # noqa: ANN001
        return _FakeResponse(
            {"content": [{"type": "text", "text": "line1"}, {"type": "text", "text": "line2"}]}
        )

    monkeypatch.setattr("src.providers.anthropic_provider.request.urlopen", fake_urlopen)
    assert _provider().screen("prompt") == "line1\nline2"


def test_anthropic_provider_rejects_invalid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout):  # noqa: ANN001
        return _FakeResponse({"content": []})

    monkeypatch.setattr("src.providers.anthropic_provider.request.urlopen", fake_urlopen)
    with pytest.raises(AnthropicProviderError, match="no text content"):
        _provider().screen("prompt")


def test_anthropic_provider_retries_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_urlopen(req, timeout):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] == 1:
            raise error.HTTPError(req.full_url, 429, "rate", {}, None)
        return _FakeResponse({"content": [{"type": "text", "text": "ok"}]})

    monkeypatch.setattr("src.providers.anthropic_provider.request.urlopen", fake_urlopen)
    assert _provider().screen("prompt") == "ok"
    assert calls["n"] == 2

