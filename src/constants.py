"""Shared constants and enums for the screening pipeline."""

from __future__ import annotations

from enum import StrEnum


class PaperStatus(StrEnum):
    """Persistent processing states for a paper."""

    NEW = "NEW"
    TEXT_EXTRACTED = "TEXT_EXTRACTED"
    SCREENING = "SCREENING"
    DONE = "DONE"
    TEXT_FAILED_RETRY = "TEXT_FAILED_RETRY"
    SCREEN_FAILED_RETRY = "SCREEN_FAILED_RETRY"
    SKIPPED_DUPLICATE = "SKIPPED_DUPLICATE"
    MANUAL_DONE = "MANUAL_DONE"


class Decision(StrEnum):
    """Allowed screening decisions."""

    INCLUDE = "INCLUDE"
    EXCLUDE = "EXCLUDE"
    MAYBE = "MAYBE"


class ExcludeReason(StrEnum):
    """Standardized exclusion reasons."""

    WRONG_TOPIC = "Wrong topic"
    QUALITATIVE_ONLY = "Qualitative only"
    FOREIGN_LANGUAGE = "Foreign language"
    EXP_IS_PREDICTOR = "Exp is a predictor"
    WRONG_EXP_TIMING = "Wrong EXP timing"
    WRONG_PUBLICATION_TYPE = "Wrong publication type"
    WRONG_POPULATION = "Wrong population"
    NO_EFFECT_SIZE = "No effect size"


class Construct(StrEnum):
    """Allowed construct labels."""

    TARGET_CONSTRUCT = "target construct"
    UNCLEAR = "unclear"


OUTPUT_COLUMNS = [
    "Title",
    "DOI",
    "Decision",
    "Exclude reason",
    "Construct",
    "Note",
    "Model",
]

QUEUEABLE_STATUSES = (
    PaperStatus.NEW,
    PaperStatus.TEXT_FAILED_RETRY,
    PaperStatus.SCREEN_FAILED_RETRY,
)

RETRY_ONLY_STATUSES = (
    PaperStatus.TEXT_FAILED_RETRY,
    PaperStatus.SCREEN_FAILED_RETRY,
)

SKIP_STATUSES = (
    PaperStatus.DONE,
    PaperStatus.MANUAL_DONE,
    PaperStatus.SKIPPED_DUPLICATE,
)

FAILED_STATUSES = (
    PaperStatus.TEXT_FAILED_RETRY,
    PaperStatus.SCREEN_FAILED_RETRY,
)

COMPLETED_STATUSES = (
    PaperStatus.DONE,
    PaperStatus.MANUAL_DONE,
)
