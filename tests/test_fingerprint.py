from __future__ import annotations

from pathlib import Path

from src.db import get_connection, initialize_database
from src.fingerprint import (
    compute_content_hash,
    compute_fallback_fingerprint,
    compute_file_hash,
)
from src.repository import PaperRepository


def test_content_hash_normalizes_equivalent_text() -> None:
    first = "Target   Construct\nIn SAMPLE DATA"
    second = "target construct in sample data"
    assert compute_content_hash(first) == compute_content_hash(second)


def test_file_and_fallback_fingerprints_are_stable(tmp_path: Path) -> None:
    paper = tmp_path / "sample.txt"
    paper.write_text("same content", encoding="utf-8")

    assert compute_file_hash(paper) == compute_file_hash(paper)
    assert compute_fallback_fingerprint(paper) == compute_fallback_fingerprint(paper)


def test_doi_match_wins_for_canonical_lookup(tmp_path: Path) -> None:
    connection = get_connection(tmp_path / "app.db")
    initialize_database(connection)
    repository = PaperRepository(connection)

    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")

    first_record = repository.register_discovered_paper(
        source_path=first,
        source_type="local",
        file_name=first.name,
        file_ext=first.suffix,
        file_hash=compute_file_hash(first),
        fallback_fingerprint=compute_fallback_fingerprint(first),
        title="First paper",
        doi="10.1000/shared",
    )
    second_record = repository.register_discovered_paper(
        source_path=second,
        source_type="local",
        file_name=second.name,
        file_ext=second.suffix,
        file_hash=compute_file_hash(second),
        fallback_fingerprint=compute_fallback_fingerprint(second),
        title="Second paper",
        doi="10.1000/shared",
    )

    canonical = repository.find_canonical_match(
        current_paper_id=second_record.paper_id,
        doi=second_record.doi,
        content_hash=None,
        file_hash=second_record.file_hash,
        fallback_fingerprint=second_record.fallback_fingerprint,
    )
    assert canonical is not None
    assert canonical.paper_id == first_record.paper_id


def test_content_hash_match_beats_file_hash_fallback_when_doi_missing(tmp_path: Path) -> None:
    connection = get_connection(tmp_path / "app.db")
    initialize_database(connection)
    repository = PaperRepository(connection)

    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("Target construct in sample dataset", encoding="utf-8")
    second.write_text("Completely different bytes", encoding="utf-8")

    first_record = repository.register_discovered_paper(
        source_path=first,
        source_type="local",
        file_name=first.name,
        file_ext=first.suffix,
        file_hash=compute_file_hash(first),
        fallback_fingerprint=compute_fallback_fingerprint(first),
        title="First paper",
        doi=None,
    )
    second_record = repository.register_discovered_paper(
        source_path=second,
        source_type="local",
        file_name=second.name,
        file_ext=second.suffix,
        file_hash=compute_file_hash(second),
        fallback_fingerprint=compute_fallback_fingerprint(second),
        title="Second paper",
        doi=None,
    )

    content_hash = compute_content_hash("Target construct in sample dataset")
    repository.update_extracted_text_metadata(
        first_record.paper_id,
        content_hash=content_hash,
        title="First paper",
        doi=None,
    )

    canonical = repository.find_canonical_match(
        current_paper_id=second_record.paper_id,
        doi=None,
        content_hash=content_hash,
        file_hash=second_record.file_hash,
        fallback_fingerprint=second_record.fallback_fingerprint,
    )
    assert canonical is not None
    assert canonical.paper_id == first_record.paper_id
