from __future__ import annotations

from pathlib import Path

from src.db import get_connection, initialize_database


def test_initialize_database_adds_screening_model_column_for_legacy_db(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    connection = get_connection(db_path)
    connection.executescript(
        """
        DROP TABLE IF EXISTS papers;
        CREATE TABLE papers (
            paper_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT NOT NULL UNIQUE,
            source_type TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_ext TEXT NOT NULL,
            file_hash TEXT,
            content_hash TEXT,
            fallback_fingerprint TEXT,
            canonical_paper_id INTEGER,
            title TEXT,
            doi TEXT,
            status TEXT NOT NULL,
            decision TEXT,
            exclude_reason TEXT NOT NULL DEFAULT '',
            construct TEXT,
            note TEXT,
            prompt_version TEXT,
            reviewed_at TEXT,
            discovered_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_error TEXT
        );
        """
    )
    connection.commit()
    initialize_database(connection)
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(papers)").fetchall()}
    assert "screening_model" in columns

