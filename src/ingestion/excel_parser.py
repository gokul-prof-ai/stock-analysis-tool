from __future__ import annotations

from pathlib import Path

import pandas as pd

from .base import DataSource, IngestionError, ParsedTable, RawExtract, UnsupportedFileError


class ExcelParser(DataSource):
    """Excel and CSV extractor."""

    source_name = "file_upload"

    def load(self, target: str | Path) -> RawExtract:
        path = Path(target).expanduser().resolve()

        if not path.exists():
            raise IngestionError(f"File not found: {path}")

        suffix = path.suffix.lower()
        if suffix not in {".csv", ".xlsx", ".xls"}:
            raise UnsupportedFileError(f"Unsupported spreadsheet type: {path}")

        try:
            if suffix == ".csv":
                frames = {"sheet1": pd.read_csv(path)}
            else:
                frames = pd.read_excel(path, sheet_name=None)
        except Exception as exc:
            raise IngestionError(f"Failed to parse spreadsheet: {path}") from exc

        tables: list[ParsedTable] = []

        for sheet_name, frame in frames.items():
            frame = frame.dropna(how="all")
            if frame.empty:
                continue

            columns = [str(column) for column in frame.columns]
            rows = frame.astype(object).where(pd.notnull(frame), None).values.tolist()

            tables.append(
                ParsedTable(
                    name=str(sheet_name),
                    columns=columns,
                    rows=rows,
                )
            )

        return RawExtract(
            source=self.source_name,
            source_file=path.name,
            metadata={"file_path": str(path)},
            tables=tables,
        )
