from __future__ import annotations

from pathlib import Path

from src.project_workspace import get_project_workspace, make_project_id


def test_same_input_dir_has_stable_project_id(tmp_path: Path) -> None:
    input_dir = tmp_path / "Review A" / "papers"
    input_dir.mkdir(parents=True, exist_ok=True)
    first = make_project_id(input_dir)
    second = make_project_id(str(input_dir))
    assert first == second


def test_different_input_dirs_have_different_project_ids(tmp_path: Path) -> None:
    a = tmp_path / "A papers"
    b = tmp_path / "B papers"
    a.mkdir(parents=True, exist_ok=True)
    b.mkdir(parents=True, exist_ok=True)
    assert make_project_id(a) != make_project_id(b)


def test_workspace_path_uses_output_projects_folder(tmp_path: Path) -> None:
    input_dir = tmp_path / "含空格 路径" / "papers"
    input_dir.mkdir(parents=True, exist_ok=True)
    workspace = get_project_workspace(input_dir, output_root=tmp_path / "output")
    assert "output" in str(workspace.root_dir)
    assert "projects" in str(workspace.root_dir)
    assert workspace.database_path.name == "screening.sqlite"

