"""Configuration loading for the local CLI application."""

from __future__ import annotations

from pathlib import Path
import os
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

try:
    from dotenv import load_dotenv as _load_dotenv
except ImportError:  # pragma: no cover - exercised only when python-dotenv is unavailable.
    _load_dotenv = None

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only when PyYAML is unavailable.
    yaml = None


class AppSettings(BaseModel):
    """Application-level settings."""

    model_config = ConfigDict(extra="ignore")

    name: str = "aiscreening"
    prompt_version: str = "v1"
    log_level: str = "INFO"


class PathsSettings(BaseModel):
    """Configured filesystem paths."""

    model_config = ConfigDict(extra="ignore")

    input_dir: str = "input/local_papers"
    output_dir: str = "output"
    database_path: str = "data/app.db"
    full_excel_path: str = "output/screening_log.xlsx"
    full_csv_path: str | None = "output/screening_log.csv"
    criteria_prompt_path: str = "config/criteria_prompt.txt"


class ScreeningSettings(BaseModel):
    """Screening runtime settings."""

    model_config = ConfigDict(extra="ignore")

    batch_size: int = 0
    skip_done: bool = True
    retry_failed: bool = True
    save_raw_response: bool = True


class GeminiSettings(BaseModel):
    """Gemini model options."""

    model_config = ConfigDict(extra="ignore")

    model: str = "gemini-2.5-pro"
    temperature: float = 0.0
    max_output_tokens: int = 2048
    thinking_budget: int | None = 128
    request_max_retries: int = 3
    request_retry_delay_seconds: float = 2.0


class FileSettings(BaseModel):
    """Allowed local source types."""

    model_config = ConfigDict(extra="ignore")

    allowed_extensions: list[str] = Field(default_factory=lambda: [".pdf", ".docx", ".txt"])


class ExportSettings(BaseModel):
    """Export options."""

    model_config = ConfigDict(extra="ignore")

    sheet_name: str = "screening_log"


class Settings(BaseModel):
    """Resolved application settings."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    base_dir: Path
    gemini_api_key: str | None = None
    app: AppSettings = Field(default_factory=AppSettings)
    paths: PathsSettings = Field(default_factory=PathsSettings)
    screening: ScreeningSettings = Field(default_factory=ScreeningSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    files: FileSettings = Field(default_factory=FileSettings)
    export: ExportSettings = Field(default_factory=ExportSettings)

    def resolve_path(self, value: str | Path) -> Path:
        """Resolve a path relative to the repository root."""

        path = Path(value)
        if path.is_absolute():
            return path
        return (self.base_dir / path).resolve()

    @property
    def input_dir(self) -> Path:
        return self.resolve_path(self.paths.input_dir)

    @property
    def output_dir(self) -> Path:
        return self.resolve_path(self.paths.output_dir)

    @property
    def database_path(self) -> Path:
        return self.resolve_path(self.paths.database_path)

    @property
    def excel_path(self) -> Path:
        return self.resolve_path(self.paths.full_excel_path)

    @property
    def csv_path(self) -> Path | None:
        if self.paths.full_csv_path is None:
            return None
        return self.resolve_path(self.paths.full_csv_path)

    @property
    def criteria_prompt_path(self) -> Path:
        return self.resolve_path(self.paths.criteria_prompt_path)


def _load_env_file(path: Path) -> None:
    """Load environment variables from .env with a stdlib fallback."""

    if not path.exists():
        return

    if _load_dotenv is not None:
        _load_dotenv(path)
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        os.environ.setdefault(key, value)


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        return value[1:-1]
    lowered = value.casefold()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def _next_meaningful_line(lines: list[str], start_index: int) -> tuple[int, str] | None:
    for index in range(start_index, len(lines)):
        candidate = lines[index]
        stripped = candidate.strip()
        if stripped and not stripped.startswith("#"):
            return index, candidate
    return None


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the small YAML subset used by this project's settings files."""

    lines = text.splitlines()
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any] | list[Any]]] = [(-1, root)]

    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        container = stack[-1][1]

        if stripped.startswith("- "):
            if not isinstance(container, list):
                raise ValueError("Invalid YAML structure: list item outside of a list context.")
            container.append(_parse_scalar(stripped[2:]))
            continue

        key, separator, value = stripped.partition(":")
        if separator != ":":
            raise ValueError(f"Invalid YAML line: {raw_line}")
        if not isinstance(container, dict):
            raise ValueError("Invalid YAML structure: mapping entry inside list context.")

        key = key.strip()
        value = value.strip()
        if value:
            container[key] = _parse_scalar(value)
            continue

        next_line = _next_meaningful_line(lines, index + 1)
        next_container: dict[str, Any] | list[Any]
        if next_line is not None:
            _, next_raw = next_line
            next_indent = len(next_raw) - len(next_raw.lstrip(" "))
            next_stripped = next_raw.strip()
            if next_indent > indent and next_stripped.startswith("- "):
                next_container = []
            else:
                next_container = {}
        else:
            next_container = {}

        container[key] = next_container
        stack.append((indent, next_container))

    return root


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if yaml is not None:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    else:
        data = _parse_simple_yaml(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping in settings file: {path}")
    return data


def load_settings(base_dir: Path, config_path: Path | None = None) -> Settings:
    """Load YAML settings and .env values into a typed configuration object."""

    dotenv_path = base_dir / ".env"
    _load_env_file(dotenv_path)

    resolved_config = config_path
    if resolved_config is None:
        preferred = base_dir / "config" / "settings.yaml"
        fallback = base_dir / "config" / "settings.yaml.example"
        resolved_config = preferred if preferred.exists() else fallback

    yaml_payload = _load_yaml(resolved_config)
    gemini_payload = dict(yaml_payload.get("gemini", {}))

    env_model = os.getenv("GEMINI_MODEL")
    if env_model:
        gemini_payload["model"] = env_model

    payload = {
        **yaml_payload,
        "base_dir": base_dir.resolve(),
        "gemini_api_key": os.getenv("GEMINI_API_KEY"),
        "gemini": gemini_payload,
    }
    return Settings.model_validate(payload)
