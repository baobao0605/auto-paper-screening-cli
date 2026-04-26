"""File discovery for local screening inputs."""

from __future__ import annotations

from pathlib import Path


def discover_files(input_dir: Path, allowed_extensions: list[str]) -> list[Path]:
    """Recursively discover supported local paper files."""

    normalized = {extension.lower() for extension in allowed_extensions}
    return sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in normalized
    )
