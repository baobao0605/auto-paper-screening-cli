"""Utilities for safely converting summary/result objects for GUI signals."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


def summary_to_dict(summary: Any) -> dict[str, Any]:
    """Best-effort conversion of summary objects to dictionaries."""

    if summary is None:
        return {}
    if isinstance(summary, dict):
        return dict(summary)
    if is_dataclass(summary):
        return asdict(summary)
    asdict_method = getattr(summary, "_asdict", None)
    if callable(asdict_method):
        try:
            return dict(asdict_method())
        except Exception:
            pass
    try:
        return dict(vars(summary))
    except TypeError:
        return {"summary": str(summary)}

