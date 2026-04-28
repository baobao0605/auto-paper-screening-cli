from __future__ import annotations

import json
from urllib import error

import pytest

from src.providers.openai_compatible_provider import (
    OpenAICompatibleProvider,
    OpenAICompatibleProviderError,
)


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_openai_compatible_provider_extracts_message_content(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleProvider(
        api_key="k",
        base_url="https://example.com/v1",
        model_name="m",
        timeout_seconds=5.0,
        request_max_retries=2,
        request_retry_delay_seconds=0.0,
    )

    def fake_urlopen(req, timeout):  # noqa: ANN001
        assert timeout == 5.0
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"Title":"T","DOI":"","Decision":"INCLUDE","Exclude reason":"","Construct":"target construct","Note":"ok"}'
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("src.providers.openai_compatible_provider.request.urlopen", fake_urlopen)
    result = provider.screen("prompt")
    assert '"Decision":"INCLUDE"' in result


def test_openai_compatible_provider_requires_api_key() -> None:
    provider = OpenAICompatibleProvider(
        api_key=None,
        base_url="https://example.com/v1",
        model_name="m",
        timeout_seconds=5.0,
        request_max_retries=2,
        request_retry_delay_seconds=0.0,
    )
    with pytest.raises(OpenAICompatibleProviderError, match="OPENAI_COMPATIBLE_API_KEY"):
        provider.screen("prompt")


def test_openai_compatible_provider_retries_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleProvider(
        api_key="k",
        base_url="https://example.com/v1",
        model_name="m",
        timeout_seconds=5.0,
        request_max_retries=2,
        request_retry_delay_seconds=0.0,
    )
    calls = {"n": 0}

    def fake_urlopen(req, timeout):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] == 1:
            raise error.HTTPError(req.full_url, 429, "rate", {}, None)
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"Title":"T","DOI":"","Decision":"INCLUDE","Exclude reason":"","Construct":"target construct","Note":"ok"}'
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("src.providers.openai_compatible_provider.request.urlopen", fake_urlopen)
    result = provider.screen("prompt")
    assert '"Decision":"INCLUDE"' in result
    assert calls["n"] == 2
