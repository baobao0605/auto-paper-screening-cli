from __future__ import annotations

from pathlib import Path

import pytest

from src import app_config
from src.app_config import AppConfig


def test_save_and_load_app_config_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "app_config.json"
    cfg = AppConfig(
        input_dir="C:/input",
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        output_dir="C:/output",
        prompt_path="C:/prompt.txt",
        api_keys={"deepseek": "k"},
        last_window_state={"w": 100},
        remember_api_key=True,
    )
    app_config.save_app_config(cfg, path=path)
    loaded = app_config.load_app_config(path=path)
    assert loaded.provider == "deepseek"
    assert loaded.remember_api_key is True
    assert loaded.api_keys == {"deepseek": "k"}


def test_default_paths_and_defaults_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = app_config.load_app_config(path=tmp_path / "missing.json")
    assert cfg.provider == "gemini"
    assert "input" in cfg.input_dir
    assert cfg.prompt_path.endswith("criteria_prompt.txt")


def test_keyring_save_and_get(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeKeyring:
        store: dict[tuple[str, str], str] = {}

        @classmethod
        def set_password(cls, service, account, value):  # noqa: ANN001
            cls.store[(service, account)] = value

        @classmethod
        def get_password(cls, service, account):  # noqa: ANN001
            return cls.store.get((service, account))

        @classmethod
        def delete_password(cls, service, account):  # noqa: ANN001
            cls.store.pop((service, account), None)

    monkeypatch.setattr(app_config, "_load_keyring_module", lambda: FakeKeyring)
    save_result = app_config.save_api_key("claude", "abc")
    assert save_result.ok is True
    value, source = app_config.get_api_key("anthropic")
    assert value == "abc"
    assert source == "keyring"
    delete_result = app_config.delete_api_key("anthropic")
    assert delete_result.ok is True


def test_keyring_unavailable_does_not_crash(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(app_config, "_load_keyring_module", lambda: None)
    temp_path = tmp_path / "app_config.json"
    monkeypatch.setattr(app_config, "get_default_app_config_path", lambda: temp_path)
    result = app_config.save_api_key("gemini", "abc")
    assert result.ok is True
    value, source = app_config.get_api_key("gemini")
    assert value == "abc"
    assert source == "app_config"


def test_env_fallback_for_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_config, "_load_keyring_module", lambda: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deep-key")
    value, source = app_config.get_api_key("deepseek")
    assert value == "deep-key"
    assert source == "env:DEEPSEEK_API_KEY"
