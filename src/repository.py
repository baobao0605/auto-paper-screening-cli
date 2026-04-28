"""Repository helpers for database persistence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from src.constants import (
    COMPLETED_STATUSES,
    FAILED_STATUSES,
    PaperStatus,
)
from src.utils import utc_now


@dataclass(slots=True)
class PaperRecord:
    """In-memory representation of a paper row."""

    paper_id: int
    source_path: str
    source_type: str
    file_name: str
    file_ext: str
    file_hash: str | None
    content_hash: str | None
    fallback_fingerprint: str | None
    canonical_paper_id: int | None
    title: str | None
    doi: str | None
    status: str
    decision: str | None
    exclude_reason: str
    construct: str | None
    note: str | None
    prompt_version: str | None
    reviewed_at: str | None
    discovered_at: str
    updated_at: str
    last_error: str | None


def _paper_from_row(row: sqlite3.Row) -> PaperRecord:
    return PaperRecord(**dict(row))


class PaperRepository:
    """Persistence operations for papers and screening audit rows."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get_by_source_path(self, source_path: Path | str) -> PaperRecord | None:
        """Return a paper by source path if it exists."""

        row = self.connection.execute(
            "SELECT * FROM papers WHERE source_path = ?",
            (str(source_path),),
        ).fetchone()
        return _paper_from_row(row) if row else None

    def get_by_id(self, paper_id: int) -> PaperRecord | None:
        """Return a paper by its primary key."""

        row = self.connection.execute(
            "SELECT * FROM papers WHERE paper_id = ?",
            (paper_id,),
        ).fetchone()
        return _paper_from_row(row) if row else None

    def get_rescreen_target_by_doi(self, doi: str) -> PaperRecord | None:
        """Return the canonical paper matching a DOI for targeted rescreening."""

        row = self.connection.execute(
            """
            SELECT *
            FROM papers
            WHERE LOWER(COALESCE(doi, '')) = LOWER(?)
              AND canonical_paper_id IS NULL
            ORDER BY paper_id
            LIMIT 1
            """,
            (doi,),
        ).fetchone()
        if row:
            return _paper_from_row(row)

        duplicate_row = self.connection.execute(
            """
            SELECT canonical_paper_id
            FROM papers
            WHERE LOWER(COALESCE(doi, '')) = LOWER(?)
              AND canonical_paper_id IS NOT NULL
            ORDER BY paper_id
            LIMIT 1
            """,
            (doi,),
        ).fetchone()
        if not duplicate_row or duplicate_row["canonical_paper_id"] is None:
            return None
        return self.get_by_id(int(duplicate_row["canonical_paper_id"]))

    def register_discovered_paper(
        self,
        *,
        source_path: Path,
        source_type: str,
        file_name: str,
        file_ext: str,
        file_hash: str,
        fallback_fingerprint: str,
        title: str | None,
        doi: str | None,
    ) -> PaperRecord:
        """Insert a new paper or refresh metadata for an existing source path."""

        existing = self.get_by_source_path(source_path)
        now = utc_now()

        if existing is None:
            cursor = self.connection.execute(
                """
                INSERT INTO papers (
                    source_path, source_type, file_name, file_ext, file_hash,
                    content_hash, fallback_fingerprint, canonical_paper_id,
                    title, doi, status, decision, exclude_reason, construct,
                    note, prompt_version, reviewed_at, discovered_at,
                    updated_at, last_error
                )
                VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, ?, ?, ?, NULL, '', NULL,
                        NULL, NULL, NULL, ?, ?, NULL)
                """,
                (
                    str(source_path),
                    source_type,
                    file_name,
                    file_ext,
                    file_hash,
                    fallback_fingerprint,
                    title,
                    doi,
                    PaperStatus.NEW.value,
                    now,
                    now,
                ),
            )
            self.connection.commit()
            return self.get_by_id(int(cursor.lastrowid))  # type: ignore[return-value]

        self.connection.execute(
            """
            UPDATE papers
            SET source_type = ?,
                file_name = ?,
                file_ext = ?,
                file_hash = ?,
                fallback_fingerprint = ?,
                title = COALESCE(NULLIF(?, ''), title),
                doi = COALESCE(NULLIF(?, ''), doi),
                updated_at = ?
            WHERE paper_id = ?
            """,
            (
                source_type,
                file_name,
                file_ext,
                file_hash,
                fallback_fingerprint,
                title or "",
                doi or "",
                now,
                existing.paper_id,
            ),
        )
        self.connection.commit()
        return self.get_by_id(existing.paper_id)  # type: ignore[return-value]

    def update_extracted_text_metadata(
        self,
        paper_id: int,
        *,
        content_hash: str,
        title: str | None,
        doi: str | None,
    ) -> None:
        """Persist metadata gathered from full-text extraction."""

        now = utc_now()
        self.connection.execute(
            """
            UPDATE papers
            SET content_hash = ?,
                title = COALESCE(NULLIF(?, ''), title),
                doi = COALESCE(NULLIF(?, ''), doi),
                status = ?,
                last_error = NULL,
                updated_at = ?
            WHERE paper_id = ?
            """,
            (
                content_hash,
                title or "",
                doi or "",
                PaperStatus.TEXT_EXTRACTED.value,
                now,
                paper_id,
            ),
        )
        self.connection.commit()

    def set_status(self, paper_id: int, status: PaperStatus, last_error: str | None = None) -> None:
        """Update the current status and optional error message."""

        self.connection.execute(
            """
            UPDATE papers
            SET status = ?, last_error = ?, updated_at = ?
            WHERE paper_id = ?
            """,
            (status.value, last_error, utc_now(), paper_id),
        )
        self.connection.commit()

    def mark_duplicate(self, paper_id: int, canonical_paper_id: int) -> None:
        """Mark a paper as a duplicate of another canonical paper."""

        self.connection.execute(
            """
            UPDATE papers
            SET status = ?,
                canonical_paper_id = ?,
                decision = NULL,
                exclude_reason = '',
                construct = NULL,
                note = NULL,
                prompt_version = NULL,
                reviewed_at = NULL,
                last_error = NULL,
                updated_at = ?
            WHERE paper_id = ?
            """,
            (
                PaperStatus.SKIPPED_DUPLICATE.value,
                canonical_paper_id,
                utc_now(),
                paper_id,
            ),
        )
        self.connection.commit()

    def mark_done(
        self,
        paper_id: int,
        *,
        title: str,
        doi: str,
        decision: str,
        exclude_reason: str,
        construct: str,
        note: str,
        prompt_version: str,
    ) -> None:
        """Persist a validated screening result."""

        reviewed_at = utc_now()
        self.connection.execute(
            """
            UPDATE papers
            SET title = ?,
                doi = ?,
                decision = ?,
                exclude_reason = ?,
                construct = ?,
                note = ?,
                prompt_version = ?,
                reviewed_at = ?,
                status = ?,
                canonical_paper_id = NULL,
                last_error = NULL,
                updated_at = ?
            WHERE paper_id = ?
            """,
            (
                title,
                doi,
                decision,
                exclude_reason,
                construct,
                note,
                prompt_version,
                reviewed_at,
                PaperStatus.DONE.value,
                reviewed_at,
                paper_id,
            ),
        )
        self.connection.commit()

    def create_screening_run(
        self,
        *,
        paper_id: int,
        model_name: str,
        prompt_version: str,
        raw_response: str | None,
        parsed_ok: bool,
    ) -> None:
        """Insert an audit row for a model attempt."""

        self.connection.execute(
            """
            INSERT INTO screening_runs (
                paper_id, model_name, prompt_version, raw_response, parsed_ok, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (paper_id, model_name, prompt_version, raw_response, int(parsed_ok), utc_now()),
        )
        self.connection.commit()

    def get_queue(self, statuses: tuple[PaperStatus, ...], limit: int | None = None) -> list[PaperRecord]:
        """Return papers eligible for processing."""

        placeholders = ", ".join("?" for _ in statuses)
        sql = f"""
            SELECT *
            FROM papers
            WHERE status IN ({placeholders})
            ORDER BY paper_id
        """
        params: list[object] = [status.value for status in statuses]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self.connection.execute(sql, params).fetchall()
        return [_paper_from_row(row) for row in rows]

    def find_canonical_match(
        self,
        *,
        current_paper_id: int,
        doi: str | None,
        content_hash: str | None,
        file_hash: str | None,
        fallback_fingerprint: str | None,
    ) -> PaperRecord | None:
        """Find a canonical paper using DOI, then content hash, then file/fallback hashes."""

        def query(field_name: str, value: str | None, case_insensitive: bool = False) -> PaperRecord | None:
            if not value:
                return None
            if case_insensitive:
                sql = f"""
                    SELECT *
                    FROM papers
                    WHERE LOWER(COALESCE({field_name}, '')) = LOWER(?)
                      AND paper_id != ?
                      AND status != ?
                    ORDER BY paper_id
                    LIMIT 1
                """
            else:
                sql = f"""
                    SELECT *
                    FROM papers
                    WHERE {field_name} = ?
                      AND paper_id != ?
                      AND status != ?
                    ORDER BY paper_id
                    LIMIT 1
                """
            row = self.connection.execute(
                sql,
                (value, current_paper_id, PaperStatus.SKIPPED_DUPLICATE.value),
            ).fetchone()
            return _paper_from_row(row) if row else None

        doi_match = query("doi", doi, case_insensitive=True)
        if doi_match:
            return doi_match

        content_match = query("content_hash", content_hash)
        if content_match:
            return content_match

        file_match = query("file_hash", file_hash)
        if file_match:
            return file_match

        return query("fallback_fingerprint", fallback_fingerprint)

    def get_status_summary(self) -> dict[str, int]:
        """Return CLI-friendly status and decision counts."""

        total_discovered = self.connection.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        done = self.connection.execute(
            "SELECT COUNT(*) FROM papers WHERE status IN (?, ?)",
            tuple(status.value for status in COMPLETED_STATUSES),
        ).fetchone()[0]
        new = self.connection.execute(
            "SELECT COUNT(*) FROM papers WHERE status = ?",
            (PaperStatus.NEW.value,),
        ).fetchone()[0]
        failed = self.connection.execute(
            "SELECT COUNT(*) FROM papers WHERE status IN (?, ?)",
            tuple(status.value for status in FAILED_STATUSES),
        ).fetchone()[0]
        maybe = self.connection.execute(
            "SELECT COUNT(*) FROM papers WHERE decision = ?",
            ("MAYBE",),
        ).fetchone()[0]
        include = self.connection.execute(
            "SELECT COUNT(*) FROM papers WHERE decision = ?",
            ("INCLUDE",),
        ).fetchone()[0]
        exclude = self.connection.execute(
            "SELECT COUNT(*) FROM papers WHERE decision = ?",
            ("EXCLUDE",),
        ).fetchone()[0]

        return {
            "total_discovered": total_discovered,
            "done": done,
            "new": new,
            "failed": failed,
            "maybe": maybe,
            "include": include,
            "exclude": exclude,
        }

    def get_export_rows(self) -> list[dict[str, str]]:
        """Return canonical completed records in export order."""

        rows = self.connection.execute(
            """
            SELECT
                title AS "Title",
                COALESCE(doi, '') AS "DOI",
                decision AS "Decision",
                exclude_reason AS "Exclude reason",
                construct AS "Construct",
                note AS "Note"
            FROM papers
            WHERE status IN (?, ?)
              AND canonical_paper_id IS NULL
            ORDER BY COALESCE(reviewed_at, updated_at), paper_id
            """,
            tuple(status.value for status in COMPLETED_STATUSES),
        ).fetchall()
        return [dict(row) for row in rows]

    def recover_stale_statuses(self) -> int:
        """Move stale in-progress rows back into retryable states."""

        now = utc_now()
        cursor = self.connection.execute(
            """
            UPDATE papers
            SET status = CASE
                    WHEN status = ? THEN ?
                    WHEN status = ? THEN ?
                    ELSE status
                END,
                last_error = CASE
                    WHEN status IN (?, ?) THEN 'Recovered from interrupted prior run.'
                    ELSE last_error
                END,
                updated_at = ?
            WHERE status IN (?, ?)
            """,
            (
                PaperStatus.TEXT_EXTRACTED.value,
                PaperStatus.TEXT_FAILED_RETRY.value,
                PaperStatus.SCREENING.value,
                PaperStatus.SCREEN_FAILED_RETRY.value,
                PaperStatus.TEXT_EXTRACTED.value,
                PaperStatus.SCREENING.value,
                now,
                PaperStatus.TEXT_EXTRACTED.value,
                PaperStatus.SCREENING.value,
            ),
        )
        self.connection.commit()
        return int(cursor.rowcount)
