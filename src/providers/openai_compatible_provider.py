"""OpenAI-compatible chat/completions provider."""

from __future__ import annotations

import json
import time
from urllib import error, request


class OpenAICompatibleProviderError(RuntimeError):
    """Raised when OpenAI-compatible provider requests fail."""


def _is_retryable_http_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code <= 599


class OpenAICompatibleProvider:
    """Provider using OpenAI-compatible /chat/completions APIs."""

    provider_name = "openai_compatible"

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        model_name: str,
        timeout_seconds: float,
        request_max_retries: int,
        request_retry_delay_seconds: float,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.request_max_retries = max(1, request_max_retries)
        self.request_retry_delay_seconds = max(0.0, request_retry_delay_seconds)

    def screen(self, prompt: str) -> str:
        if not self.api_key:
            raise OpenAICompatibleProviderError(
                "Missing OPENAI_COMPATIBLE_API_KEY. Add it to .env before running screening."
            )
        if not self.base_url:
            raise OpenAICompatibleProviderError(
                "Missing openai_compatible.base_url in settings."
            )
        if not self.model_name:
            raise OpenAICompatibleProviderError(
                "Missing openai_compatible.model in settings."
            )

        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
        }
        body = json.dumps(payload).encode("utf-8")
        endpoint = f"{self.base_url}/chat/completions"
        req = request.Request(
            endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        parsed: dict[str, object] | None = None
        last_error: Exception | None = None
        for attempt in range(1, self.request_max_retries + 1):
            try:
                with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    parsed = json.loads(resp.read().decode("utf-8"))
                last_error = None
                break
            except error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="ignore")
                last_error = OpenAICompatibleProviderError(
                    f"OpenAI-compatible request failed with HTTP {exc.code}: {detail}"
                )
                if not _is_retryable_http_status(exc.code) or attempt >= self.request_max_retries:
                    break
                if self.request_retry_delay_seconds > 0:
                    time.sleep(self.request_retry_delay_seconds * attempt)
            except error.URLError as exc:
                last_error = OpenAICompatibleProviderError(
                    f"OpenAI-compatible request failed: {exc}"
                )
                if attempt >= self.request_max_retries:
                    break
                if self.request_retry_delay_seconds > 0:
                    time.sleep(self.request_retry_delay_seconds * attempt)

        if last_error is not None:
            raise last_error
        assert parsed is not None

        choices = parsed.get("choices") if isinstance(parsed, dict) else None
        if not choices:
            raise OpenAICompatibleProviderError("OpenAI-compatible response missing choices.")

        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        content = message.get("content")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    value = item.get("text")
                    if isinstance(value, str) and value.strip():
                        parts.append(value)
            content = "\n".join(parts)
        if isinstance(content, str) and content.strip():
            return content.strip()
        raise OpenAICompatibleProviderError("OpenAI-compatible response had empty message content.")
