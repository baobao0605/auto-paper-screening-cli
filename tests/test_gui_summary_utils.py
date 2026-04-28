from __future__ import annotations

from collections import namedtuple

from src.gui.summary_utils import summary_to_dict
from src.screener import RunSummary


def test_summary_to_dict_handles_dataclass_summary() -> None:
    summary = RunSummary(queued=2, done=1, failed=1, duplicates=0, exported_rows=1)
    payload = summary_to_dict(summary)
    assert payload["queued"] == 2
    assert payload["done"] == 1


def test_summary_to_dict_handles_namedtuple() -> None:
    NT = namedtuple("NT", ["a", "b"])
    payload = summary_to_dict(NT(a=1, b=2))
    assert payload == {"a": 1, "b": 2}


def test_summary_to_dict_handles_object_without_dict() -> None:
    class SlotOnly:
        __slots__ = ("value",)

        def __init__(self, value: int) -> None:
            self.value = value

        def __str__(self) -> str:
            return f"SlotOnly({self.value})"

    payload = summary_to_dict(SlotOnly(3))
    assert payload == {"summary": "SlotOnly(3)"}

