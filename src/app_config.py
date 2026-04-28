"""User-level app configuration for future desktop UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Any


APP_DIR_NAME = "ai_fulltext_screening"
APP_CONFIG_FILE = "app_config.json"
KEYRING_SERVICE = "ai_fulltext_screening"

PROVIDER_KEY_ALIASES = {
    "gemini": "gemini",
    "google": "gemini",
    "openai_compatible": "openai_compatible",
    "deepseek": "deepseek",
    "anthropic": "anthropic",
    "claude": "anthropic",
}

PROVIDER_ENV_VARS = {
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "openai_compatible": ("OPENAI_COMPATIBLE_API_KEY",),
    "deepseek": ("DEEPSEEK_API_KEY", "OPENAI_COMPATIBLE_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY",),
}


@dataclass(slots=True)
class AppConfig:
    input_dir: str
    provider: str
    model: str
    base_url: str
    output_dir: str
    prompt_path: str
    api_keys: dict[str, str] | None = None
    last_window_state: dict[str, Any] | None = None
    remember_api_key: bool = False


@dataclass(slots=True)
class APIKeyOperationResult:
    ok: bool
    source: str
    message: str = ""


def _normalize_provider(provider: str) -> str:
    return PROVIDER_KEY_ALIASES.get((provider or "").strip().casefold(), "openai_compatible")


def get_default_app_config_path() -> Path:
    appdata = os.getenv("APPDATA")
    if os.name == "nt" and appdata:
        base_dir = Path(appdata) / APP_DIR_NAME
    else:
        base_dir = Path.home() / f".{APP_DIR_NAME}"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / APP_CONFIG_FILE


def get_default_input_dir() -> str:
    return str((Path.cwd() / "input" / "local_papers").resolve())


def get_default_prompt_path() -> str:
    return str((Path.cwd() / "config" / "criteria_prompt.txt").resolve())


def _default_output_dir() -> str:
    return str((Path.cwd() / "output").resolve())


def _default_config() -> AppConfig:
    return AppConfig(
        input_dir=get_default_input_dir(),
        provider="gemini",
        model="",
        base_url="",
        output_dir=_default_output_dir(),
        prompt_path=get_default_prompt_path(),
        api_keys={},
        last_window_state=None,
        remember_api_key=False,
    )


def load_app_config(path: Path | None = None) -> AppConfig:
    target = path or get_default_app_config_path()
    if not target.exists():
        return _default_config()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_config()
    defaults = asdict(_default_config())
    defaults.update({k: v for k, v in payload.items() if k in defaults})
    if not isinstance(defaults.get("api_keys"), dict):
        defaults["api_keys"] = {}
    return AppConfig(**defaults)


def save_app_config(config: AppConfig, path: Path | None = None) -> Path:
    target = path or get_default_app_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _load_keyring_module():
    try:
        import keyring  # type: ignore
    except Exception:
        return None
    return keyring


def _keyring_account(provider: str) -> str:
    return f"provider:{_normalize_provider(provider)}"


def get_api_key(provider: str) -> tuple[str | None, str]:
    normalized = _normalize_provider(provider)
    keyring_module = _load_keyring_module()
    if keyring_module is not None:
        try:
            value = keyring_module.get_password(KEYRING_SERVICE, _keyring_account(normalized))
        except Exception:
            value = None
        if value:
            return value, "keyring"

    config = load_app_config()
    config_keys = config.api_keys or {}
    config_value = config_keys.get(normalized)
    if config_value:
        return config_value, "app_config"

    for env_name in PROVIDER_ENV_VARS.get(normalized, ()):
        value = os.getenv(env_name)
        if value:
            return value, f"env:{env_name}"
    return None, "missing"


def save_api_key(provider: str, api_key: str) -> APIKeyOperationResult:
    normalized = _normalize_provider(provider)
    keyring_module = _load_keyring_module()
    if keyring_module is not None:
        try:
            keyring_module.set_password(KEYRING_SERVICE, _keyring_account(normalized), api_key)
            return APIKeyOperationResult(ok=True, source="keyring")
        except Exception:
            pass

    config = load_app_config()
    keys = dict(config.api_keys or {})
    keys[normalized] = api_key
    config.api_keys = keys
    save_app_config(config)
    return APIKeyOperationResult(ok=True, source="app_config")


def delete_api_key(provider: str) -> APIKeyOperationResult:
    normalized = _normalize_provider(provider)
    keyring_deleted = False
    keyring_available = False
    keyring_module = _load_keyring_module()
    if keyring_module is not None:
        keyring_available = True
        try:
            keyring_module.delete_password(KEYRING_SERVICE, _keyring_account(normalized))
            keyring_deleted = True
        except Exception:
            # Missing key in keyring should not be fatal for local usability.
            keyring_deleted = False

    config_deleted = False
    try:
        config = load_app_config()
        keys = dict(config.api_keys or {})
        if normalized in keys:
            config_deleted = True
            keys.pop(normalized, None)
            config.api_keys = keys
            save_app_config(config)
    except OSError as exc:
        return APIKeyOperationResult(ok=False, source="app_config", message=str(exc))

    if keyring_deleted:
        return APIKeyOperationResult(ok=True, source="keyring")
    if config_deleted:
        return APIKeyOperationResult(ok=True, source="app_config")
    if keyring_available:
        return APIKeyOperationResult(ok=True, source="keyring")
    return APIKeyOperationResult(ok=True, source="app_config")
