"""Thin wrapper around the Google Gemini SDK."""

from __future__ import annotations

import json
import time


class GeminiClientError(RuntimeError):
    """Raised when Gemini configuration or API calls fail."""

    def __init__(self, message: str, *, raw_response: str | None = None) -> None:
        super().__init__(message)
        self.raw_response = raw_response


def _safe_serialize_response(response: object) -> str:
    """Best-effort response serialization for debugging empty/non-text replies."""

    for method_name in ("model_dump_json", "to_json_dict"):
        method = getattr(response, method_name, None)
        if callable(method):
            try:
                payload = method()
                if isinstance(payload, str):
                    return payload
                return json.dumps(payload, ensure_ascii=False, default=str)
            except Exception:
                pass

    model_dump = getattr(response, "model_dump", None)
    if callable(model_dump):
        try:
            return json.dumps(model_dump(), ensure_ascii=False, default=str)
        except Exception:
            pass

    candidates = getattr(response, "candidates", None)
    prompt_feedback = getattr(response, "prompt_feedback", None)
    payload = {
        "text": getattr(response, "text", None),
        "candidates_count": len(candidates or []),
        "prompt_feedback": repr(prompt_feedback),
        "candidates": [],
    }
    for candidate in candidates or []:
        payload["candidates"].append(
            {
                "finish_reason": repr(getattr(candidate, "finish_reason", None)),
                "safety_ratings": repr(getattr(candidate, "safety_ratings", None)),
                "content": repr(getattr(candidate, "content", None)),
            }
        )
    return json.dumps(payload, ensure_ascii=False, default=str)


def _extract_finish_reasons(response: object) -> list[str]:
    """Collect candidate finish reasons for diagnostics."""

    reasons: list[str] = []
    for candidate in getattr(response, "candidates", None) or []:
        finish_reason = getattr(candidate, "finish_reason", None)
        if finish_reason is not None:
            reasons.append(str(finish_reason))
    return reasons


def _is_retryable_request_error(exc: Exception) -> bool:
    """Return True when a Gemini request failure looks transient."""

    message = str(exc).casefold()
    retryable_fragments = (
        "unexpected_eof_while_reading",
        "eof occurred in violation of protocol",
        "ssl",
        "connection reset",
        "connection aborted",
        "timed out",
        "timeout",
        "temporary failure",
        "temporarily unavailable",
        "service unavailable",
        "internal error",
        "429",
        "500",
        "502",
        "503",
        "504",
    )
    return any(fragment in message for fragment in retryable_fragments)


class GeminiClient:
    """Minimal Gemini client wrapper for screening prompts."""

    def __init__(
        self,
        *,
        api_key: str | None,
        model_name: str,
        temperature: float,
        max_output_tokens: int,
        thinking_budget: int | None,
        request_max_retries: int,
        request_retry_delay_seconds: float,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.thinking_budget = thinking_budget
        self.request_max_retries = max(1, request_max_retries)
        self.request_retry_delay_seconds = max(0.0, request_retry_delay_seconds)

    def screen(self, prompt: str) -> str:
        """Submit a screening prompt and return raw text output."""

        if not self.api_key:
            raise GeminiClientError("Missing GEMINI_API_KEY. Add it to .env before running screening.")

        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise GeminiClientError(
                "google-genai is not installed. Install requirements before running the CLI."
            ) from exc

        client = genai.Client(api_key=self.api_key)
        config_kwargs = {
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "response_mime_type": "application/json",
        }
        thinking_config_cls = getattr(types, "ThinkingConfig", None)
        if thinking_config_cls is not None and self.thinking_budget is not None:
            config_kwargs["thinking_config"] = thinking_config_cls(
                thinking_budget=self.thinking_budget
            )

        response = None
        last_error: Exception | None = None
        for attempt in range(1, self.request_max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
                last_error = None
                break
            except Exception as exc:  # pragma: no cover - network/SDK errors are environment-specific.
                last_error = exc
                if not _is_retryable_request_error(exc) or attempt >= self.request_max_retries:
                    break
                if self.request_retry_delay_seconds > 0:
                    time.sleep(self.request_retry_delay_seconds * attempt)

        if last_error is not None:
            raise GeminiClientError(
                f"Gemini request failed after {self.request_max_retries} attempt(s): {last_error}"
            ) from last_error

        text = getattr(response, "text", None)
        if text:
            return text.strip()

        candidates = getattr(response, "candidates", None) or []
        parts: list[str] = []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            if not content:
                continue
            for part in getattr(content, "parts", []) or []:
                value = getattr(part, "text", None)
                if value:
                    parts.append(value)

        if parts:
            return "\n".join(parts).strip()
        debug_payload = _safe_serialize_response(response)
        finish_reasons = _extract_finish_reasons(response)
        if "MAX_TOKENS" in finish_reasons:
            raise GeminiClientError(
                "Gemini returned no text content because generation hit MAX_TOKENS before producing a final answer.",
                raw_response=debug_payload,
            )
        raise GeminiClientError(
            "Gemini returned no text content. The response may have been blocked, empty, or structured without text parts.",
            raw_response=debug_payload,
        )
