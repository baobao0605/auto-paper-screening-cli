from __future__ import annotations

from src.providers.gemini_provider import GeminiProvider


class DummyGeminiClient:
    def __init__(self) -> None:
        self.model_name = "gemini-test"
        self.calls: list[str] = []

    def screen(self, prompt: str) -> str:
        self.calls.append(prompt)
        return '{"Title":"T","DOI":"","Decision":"MAYBE","Exclude reason":"","Construct":"unclear","Note":"n"}'


def test_gemini_provider_delegates_to_client() -> None:
    client = DummyGeminiClient()
    provider = GeminiProvider(client)
    prompt = "hello"

    result = provider.screen(prompt)

    assert client.calls == [prompt]
    assert result.startswith('{"Title"')
    assert provider.model_name == "gemini-test"

