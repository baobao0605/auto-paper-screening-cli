"""SQLite connection and schema helpers."""

from __future__ import annotations

from pathlib import Path
import sqlite3

from src.utils import ensure_parent_dir


def get_connection(database_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with sensible defaults for the pipeline."""

    ensure_parent_dir(database_path)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    connection.execute("PRAGMA journal_mode = WAL;")
    connection.execute("PRAGMA synchronous = NORMAL;")
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    """Create database tables and indexes if they do not already exist."""

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS papers (
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
            screening_model TEXT,
            prompt_version TEXT,
            reviewed_at TEXT,
            discovered_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_error TEXT,
            FOREIGN KEY (canonical_paper_id) REFERENCES papers(paper_id)
        );

        CREATE TABLE IF NOT EXISTS screening_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id INTEGER NOT NULL,
            model_name TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            raw_response TEXT,
            parsed_ok INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
        );

        CREATE INDEX IF NOT EXISTS idx_papers_status ON papers(status);
        CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
        CREATE INDEX IF NOT EXISTS idx_papers_content_hash ON papers(content_hash);
        CREATE INDEX IF NOT EXISTS idx_papers_file_hash ON papers(file_hash);
        CREATE INDEX IF NOT EXISTS idx_papers_fallback ON papers(fallback_fingerprint);
        CREATE INDEX IF NOT EXISTS idx_papers_canonical ON papers(canonical_paper_id);
        CREATE INDEX IF NOT EXISTS idx_screening_runs_paper ON screening_runs(paper_id);
        """
    )
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(papers)").fetchall()
    }
    if "screening_model" not in columns:
        connection.execute("ALTER TABLE papers ADD COLUMN screening_model TEXT")
    connection.commit()
