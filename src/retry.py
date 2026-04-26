"""Retry-related helpers."""

from __future__ import annotations

from src.constants import PaperStatus, QUEUEABLE_STATUSES, RETRY_ONLY_STATUSES


def get_queue_statuses(retry_only: bool = False) -> tuple[PaperStatus, ...]:
    """Return statuses that should be queued for a given command."""

    return RETRY_ONLY_STATUSES if retry_only else QUEUEABLE_STATUSES
