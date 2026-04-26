"""Export SQLite data to a complete Excel log."""

from __future__ import annotations

from pathlib import Path

from src.constants import OUTPUT_COLUMNS
from src.repository import PaperRepository
from src.utils import ensure_parent_dir


class Exporter:
    """Regenerate full screening exports from SQLite."""

    def __init__(
        self,
        repository: PaperRepository,
        *,
        excel_path: Path,
        csv_path: Path | None,
        sheet_name: str,
    ) -> None:
        self.repository = repository
        self.excel_path = excel_path
        self.csv_path = csv_path
        self.sheet_name = sheet_name

    def export(self) -> int:
        """Write the full export and return the row count."""

        try:
            import pandas as pd
        except ImportError as exc:  # pragma: no cover - depends on local environment.
            raise RuntimeError(
                "Excel export requires pandas and openpyxl. Install project dependencies with "
                "'python -m pip install -r requirements.txt'."
            ) from exc

        rows = self.repository.get_export_rows()
        frame = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)

        ensure_parent_dir(self.excel_path)
        try:
            with pd.ExcelWriter(self.excel_path, engine="openpyxl") as writer:
                frame.to_excel(writer, sheet_name=self.sheet_name, index=False)
        except PermissionError as exc:
            raise RuntimeError(
                f"Could not write Excel export because the file is in use: {self.excel_path}. "
                "Close the file in Excel/WPS and run the command again."
            ) from exc

        if self.csv_path is not None:
            ensure_parent_dir(self.csv_path)
            try:
                frame.to_csv(self.csv_path, index=False)
            except PermissionError as exc:
                raise RuntimeError(
                    f"Could not write CSV export because the file is in use: {self.csv_path}. "
                    "Close the file in Excel/WPS/another editor and run the command again."
                ) from exc

        return len(frame.index)
