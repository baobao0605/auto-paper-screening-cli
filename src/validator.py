"""Strict validation for Gemini screening output."""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


EXPECTED_KEYS = {
    "Title",
    "DOI",
    "Decision",
    "Exclude reason",
    "Construct",
    "Note",
}


class ModelOutputValidationError(ValueError):
    """Raised when model output is not valid screening JSON."""


FENCED_JSON_RE = re.compile(
    r"^\s*```(?:json)?\s*(?P<body>[\s\S]*?)\s*```\s*$",
    re.IGNORECASE,
)


def _normalize_json_candidate(raw_response: str) -> str:
    """Strip common model wrappers while still requiring a JSON object payload."""

    candidate = raw_response.strip()
    fenced = FENCED_JSON_RE.match(candidate)
    if fenced:
        candidate = fenced.group("body").strip()
    return candidate


class ScreeningResult(BaseModel):
    """Validated screening payload returned by the model."""

    model_config = ConfigDict(extra="forbid", populate_by_name=False, str_strip_whitespace=True)

    Title: str
    DOI: str = ""
    Decision: Literal["INCLUDE", "EXCLUDE", "MAYBE"]
    Exclude_reason: str = Field(alias="Exclude reason")
    Construct: Literal["target construct", "unclear"]
    Note: str

    @field_validator("Title", "Note")
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("Field must not be empty.")
        return value

    @field_validator("Exclude_reason")
    @classmethod
    def validate_reason_value(cls, value: str) -> str:
        allowed = {
            "",
            "Wrong topic",
            "Qualitative only",
            "Foreign language",
            "Exp is a predictor",
            "Wrong EXP timing",
            "Wrong publication type",
            "Wrong population",
            "No effect size",
        }
        if value not in allowed:
            raise ValueError("Invalid exclusion reason.")
        return value

    @model_validator(mode="after")
    def validate_cross_field_rules(self) -> "ScreeningResult":
        if self.Decision == "EXCLUDE" and not self.Exclude_reason:
            raise ValueError("Exclude reason must be present when Decision is EXCLUDE.")
        if self.Decision in {"INCLUDE", "MAYBE"} and self.Exclude_reason:
            raise ValueError("Exclude reason must be empty unless Decision is EXCLUDE.")
        return self

    def to_db_payload(self) -> dict[str, str]:
        """Return a simple payload for repository persistence/export."""

        return {
            "Title": self.Title,
            "DOI": self.DOI,
            "Decision": self.Decision,
            "Exclude reason": self.Exclude_reason,
            "Construct": self.Construct,
            "Note": self.Note,
        }


def validate_model_output(raw_response: str) -> ScreeningResult:
    """Parse and strictly validate the model's JSON response."""

    normalized = _normalize_json_candidate(raw_response)

    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise ModelOutputValidationError(f"Model response was not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ModelOutputValidationError("Model response must be a JSON object.")
    if set(parsed.keys()) != EXPECTED_KEYS or len(parsed) != len(EXPECTED_KEYS):
        raise ModelOutputValidationError("Model response must contain exactly the required 6 keys.")

    try:
        return ScreeningResult.model_validate(parsed)
    except ValidationError as exc:
        raise ModelOutputValidationError(str(exc)) from exc
