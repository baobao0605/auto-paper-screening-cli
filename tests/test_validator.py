from __future__ import annotations

import json

import pytest

from src.validator import ModelOutputValidationError, validate_model_output


def _valid_payload() -> dict[str, str]:
    return {
        "Title": "Sample quantitative paper",
        "DOI": "10.1000/example",
        "Decision": "INCLUDE",
        "Exclude reason": "",
        "Construct": "target construct",
        "Note": "The study reports quantitative analyses for the target construct.",
    }


def test_validator_accepts_exact_contract() -> None:
    result = validate_model_output(json.dumps(_valid_payload()))
    assert result.Decision == "INCLUDE"
    assert result.Construct == "target construct"


def test_validator_rejects_extra_keys() -> None:
    payload = _valid_payload()
    payload["Extra"] = "not allowed"
    with pytest.raises(ModelOutputValidationError):
        validate_model_output(json.dumps(payload))


def test_validator_rejects_invalid_decision() -> None:
    payload = _valid_payload()
    payload["Decision"] = "YES"
    with pytest.raises(ModelOutputValidationError):
        validate_model_output(json.dumps(payload))


def test_validator_rejects_exclude_reason_for_include() -> None:
    payload = _valid_payload()
    payload["Exclude reason"] = "Wrong topic"
    with pytest.raises(ModelOutputValidationError):
        validate_model_output(json.dumps(payload))


def test_validator_rejects_missing_key() -> None:
    payload = _valid_payload()
    del payload["Note"]
    with pytest.raises(ModelOutputValidationError):
        validate_model_output(json.dumps(payload))


def test_validator_rejects_exclude_without_reason() -> None:
    payload = _valid_payload()
    payload["Decision"] = "EXCLUDE"
    payload["Exclude reason"] = ""
    with pytest.raises(ModelOutputValidationError):
        validate_model_output(json.dumps(payload))


def test_validator_rejects_invalid_construct() -> None:
    payload = _valid_payload()
    payload["Construct"] = "construct x"
    with pytest.raises(ModelOutputValidationError):
        validate_model_output(json.dumps(payload))


def test_validator_accepts_new_no_effect_size_reason() -> None:
    payload = _valid_payload()
    payload["Decision"] = "EXCLUDE"
    payload["Exclude reason"] = "No effect size"
    result = validate_model_output(json.dumps(payload))
    assert result.Exclude_reason == "No effect size"


def test_validator_accepts_json_wrapped_in_markdown_fences() -> None:
    payload = json.dumps(_valid_payload(), ensure_ascii=False, indent=2)
    wrapped = f"```json\n{payload}\n```"
    result = validate_model_output(wrapped)
    assert result.Title == "Sample quantitative paper"
