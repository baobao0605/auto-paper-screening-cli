from __future__ import annotations

from src.cli import parse_doi_input


def test_parse_doi_input_with_explicit_delimiter() -> None:
    values = parse_doi_input("10.1/a|10.2/b|10.3/c", "|")
    assert values == ["10.1/a", "10.2/b", "10.3/c"]


def test_parse_doi_input_trims_whitespace_and_ignores_empty_items() -> None:
    values = parse_doi_input("10.1/a ; 10.2/b ; ", ";")
    assert values == ["10.1/a", "10.2/b"]
