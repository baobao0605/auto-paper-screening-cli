"""State recovery helpers for interrupted runs."""

from __future__ import annotations

from src.repository import PaperRepository


class StateManager:
    """Recover stale in-progress rows at startup."""

    def __init__(self, repository: PaperRepository) -> None:
        self.repository = repository

    def recover_stale_records(self) -> int:
        """Move stale TEXT_EXTRACTED/SCREENING rows back into retry buckets."""

        return self.repository.recover_stale_statuses()
