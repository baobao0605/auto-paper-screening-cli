"""Command-line interface for the screening pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
from typing import Sequence

from src.config import load_settings
from src.db import get_connection, initialize_database
from src.logger import configure_logging
from src.repository import PaperRepository
from src.screener import ScreeningPipeline


COMMON_DOI_DELIMITERS = ("|", ";", ",", "，", "\n")


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""

    parser = argparse.ArgumentParser(description="AI-assisted full-text screening CLI")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional path to settings.yaml; defaults to config/settings.yaml or the example file.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("scan", help="Discover files and register papers in SQLite.")
    subparsers.add_parser("run", help="Scan, screen eligible papers, and export the full Excel log.")
    subparsers.add_parser("export", help="Regenerate the full Excel log from SQLite.")
    subparsers.add_parser("retry-failed", help="Retry only failed papers and export the full Excel log.")
    subparsers.add_parser("status", help="Show summary counts for discovered papers.")
    rescreen_parser = subparsers.add_parser(
        "rescreen-doi",
        help="Rescreen specific papers by exact DOI and overwrite prior conclusions.",
    )
    rescreen_parser.add_argument(
        "--dois",
        required=True,
        help="One or more DOIs joined by a delimiter, matching the DOI column exactly.",
    )
    rescreen_parser.add_argument(
        "--delimiter",
        default="|",
        help="Delimiter used inside --dois. Default: |",
    )
    return parser


def parse_doi_input(raw_value: str, delimiter: str | None) -> list[str]:
    """Split a DOI string into exact DOI values."""

    if delimiter:
        parts = [segment.strip() for segment in raw_value.split(delimiter)]
    else:
        pattern = "|".join(re.escape(item) for item in COMMON_DOI_DELIMITERS)
        parts = [segment.strip() for segment in re.split(pattern, raw_value)]
    return [part for part in parts if part]


def build_pipeline(config_path: Path | None = None) -> ScreeningPipeline:
    """Create a pipeline instance from on-disk settings."""

    resolved_config = config_path.resolve() if config_path is not None else None
    if resolved_config is None:
        base_dir = Path.cwd()
    elif resolved_config.parent.name.casefold() == "config":
        base_dir = resolved_config.parent.parent
    else:
        base_dir = resolved_config.parent

    settings = load_settings(base_dir, config_path=resolved_config)
    logger = configure_logging(settings.output_dir, settings.app.log_level)
    connection = get_connection(settings.database_path)
    initialize_database(connection)
    repository = PaperRepository(connection)
    return ScreeningPipeline(settings=settings, repository=repository, logger=logger)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint used by python -m src.main."""

    parser = build_parser()
    args = parser.parse_args(argv)
    pipeline = build_pipeline(args.config)

    if args.command == "scan":
        summary = pipeline.scan()
        print(f"Discovered: {summary.discovered}")
        print(f"Registered: {summary.registered}")
        print(f"Duplicates marked: {summary.duplicates}")
        return 0

    if args.command == "run":
        summary = pipeline.run(retry_only=False)
        print(f"Queued: {summary.queued}")
        print(f"Done: {summary.done}")
        print(f"Failed: {summary.failed}")
        print(f"Duplicates: {summary.duplicates}")
        print(f"Exported rows: {summary.exported_rows}")
        return 0

    if args.command == "retry-failed":
        summary = pipeline.run(retry_only=True)
        print(f"Queued: {summary.queued}")
        print(f"Done: {summary.done}")
        print(f"Failed: {summary.failed}")
        print(f"Duplicates: {summary.duplicates}")
        print(f"Exported rows: {summary.exported_rows}")
        return 0

    if args.command == "export":
        count = pipeline.export()
        print(f"Exported rows: {count}")
        return 0

    if args.command == "status":
        summary = pipeline.status()
        print(f"total discovered: {summary['total_discovered']}")
        print(f"done: {summary['done']}")
        print(f"new: {summary['new']}")
        print(f"failed: {summary['failed']}")
        print(f"maybe: {summary['maybe']}")
        print(f"include: {summary['include']}")
        print(f"exclude: {summary['exclude']}")
        return 0

    if args.command == "rescreen-doi":
        doi_values = parse_doi_input(args.dois, args.delimiter)
        summary = pipeline.rescreen_by_dois(doi_values)
        print(f"Requested: {summary.requested}")
        print(f"Found: {summary.found}")
        print(f"Done: {summary.done}")
        print(f"Failed: {summary.failed}")
        print(f"Exported rows: {summary.exported_rows}")
        if summary.missing:
            print("Missing DOI(s):")
            for doi in summary.missing:
                print(doi)
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 1
