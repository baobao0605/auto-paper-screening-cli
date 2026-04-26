from __future__ import annotations

import json

from src.gemini_client import (
    GeminiClientError,
    _is_retryable_request_error,
    _safe_serialize_response,
)


class _Part:
    def __init__(self, text: str | None = None) -> None:
        self.text = text


class _Content:
    def __init__(self, parts: list[_Part]) -> None:
        self.parts = parts


class _Candidate:
    def __init__(self, finish_reason: str, parts: list[_Part]) -> None:
        self.finish_reason = finish_reason
        self.safety_ratings = ["mock"]
        self.content = _Content(parts)


class _Response:
    def __init__(self) -> None:
        self.text = None
        self.prompt_feedback = {"block_reason": "unspecified"}
        self.candidates = [_Candidate("SAFETY", [])]


def test_safe_serialize_response_contains_debug_fields() -> None:
    payload = json.loads(_safe_serialize_response(_Response()))
    assert payload["candidates_count"] == 1
    assert payload["prompt_feedback"] is not None


def test_gemini_client_error_can_carry_raw_response() -> None:
    exc = GeminiClientError("no text", raw_response='{"debug": true}')
    assert exc.raw_response == '{"debug": true}'


def test_retryable_request_error_detects_ssl_eof() -> None:
    exc = RuntimeError("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol")
    assert _is_retryable_request_error(exc) is True


def test_retryable_request_error_rejects_invalid_argument() -> None:
    exc = RuntimeError("400 INVALID_ARGUMENT. Budget 0 is invalid.")
    assert _is_retryable_request_error(exc) is False
