"""Project workspace isolation helpers for GUI runs."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import shutil


SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]+")


@dataclass(slots=True)
class ProjectWorkspace:
    input_dir: Path
    project_id: str
    root_dir: Path
    database_path: Path
    excel_path: Path
    csv_path: Path
    run_log_path: Path
    error_log_path: Path
    prompt_snapshot_path: Path
    settings_snapshot_path: Path


def normalize_input_dir(input_dir: str | Path) -> Path:
    return Path(input_dir).expanduser().resolve()


def make_project_id(input_dir: str | Path) -> str:
    resolved = normalize_input_dir(input_dir)
    base_name = SAFE_NAME_RE.sub("_", resolved.name.strip()) or "project"
    digest = hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:6]
    return f"{base_name}_{digest}"


def get_project_workspace(input_dir: str | Path, *, output_root: str | Path = "output") -> ProjectWorkspace:
    resolved = normalize_input_dir(input_dir)
    project_id = make_project_id(resolved)
    root_dir = Path(output_root).resolve() / "projects" / project_id
    return ProjectWorkspace(
        input_dir=resolved,
        project_id=project_id,
        root_dir=root_dir,
        database_path=root_dir / "screening.sqlite",
        excel_path=root_dir / "screening_log.xlsx",
        csv_path=root_dir / "screening_log.csv",
        run_log_path=root_dir / "run.log",
        error_log_path=root_dir / "error.log",
        prompt_snapshot_path=root_dir / "criteria_prompt_snapshot.txt",
        settings_snapshot_path=root_dir / "settings_snapshot.json",
    )


def ensure_project_workspace(input_dir: str | Path, *, output_root: str | Path = "output") -> ProjectWorkspace:
    workspace = get_project_workspace(input_dir, output_root=output_root)
    workspace.root_dir.mkdir(parents=True, exist_ok=True)
    return workspace


def clear_project_workspace(input_dir: str | Path, *, output_root: str | Path = "output") -> None:
    workspace = get_project_workspace(input_dir, output_root=output_root)
    if workspace.root_dir.exists():
        shutil.rmtree(workspace.root_dir)


def get_project_output_dir(input_dir: str | Path, *, output_root: str | Path = "output") -> Path:
    return get_project_workspace(input_dir, output_root=output_root).root_dir

