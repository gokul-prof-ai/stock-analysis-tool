from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import DataSource, IngestionError, ParsedTable, RawExtract, UnsupportedFileError


class PDFParser(DataSource):
    """PDF extractor using pdfplumber first and PyMuPDF fallback."""

    source_name = "file_upload"

    def load(self, target: str | Path) -> RawExtract:
        path = Path(target).expanduser().resolve()

        if not path.exists():
            raise IngestionError(f"PDF not found: {path}")
        if path.suffix.lower() != ".pdf":
            raise UnsupportedFileError(f"Not a PDF file: {path}")

        try:
            tables, text = self._extract_with_pdfplumber(path)
        except Exception:
            try:
                tables, text = self._extract_with_fitz(path)
            except Exception as exc:
                raise IngestionError(f"Failed to extract PDF: {path}") from exc

        if not text:
            try:
                _, fitz_text = self._extract_with_fitz(path)
                text = fitz_text
            except Exception:
                text = ""

        if not tables and text:
            tables = self._parse_text_tables(text)

        return RawExtract(
            source=self.source_name,
            source_file=path.name,
            metadata={"file_path": str(path)},
            tables=tables,
        )

    def _extract_with_pdfplumber(self, path: Path) -> tuple[list[ParsedTable], str]:
        import pdfplumber

        tables: list[ParsedTable] = []
        text_pages: list[str] = []

        with pdfplumber.open(path) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                text_pages.append(text)

                try:
                    page_tables = page.extract_tables() or []
                except Exception:
                    page_tables = []

                for table_number, raw_table in enumerate(page_tables, start=1):
                    if not raw_table:
                        continue

                    cleaned = [
                        ["" if cell is None else str(cell) for cell in row]
                        for row in raw_table
                    ]
                    if len(cleaned) < 2:
                        continue

                    header = cleaned[0]
                    body = cleaned[1:]
                    max_cols = max([len(header)] + [len(row) for row in body] + [1])
                    columns = header + [f"col_{i}" for i in range(len(header), max_cols)]
                    rows = [row + [""] * (len(columns) - len(row)) for row in body]

                    tables.append(
                        ParsedTable(
                            name=f"page{page_number}_table{table_number}",
                            columns=columns,
                            rows=rows,
                        )
                    )

        return tables, "\n".join(text_pages)

    def _extract_with_fitz(self, path: Path) -> tuple[list[ParsedTable], str]:
        import fitz

        text_pages: list[str] = []
        document = fitz.open(str(path))

        try:
            for page in document:
                text_pages.append(page.get_text())
        finally:
            document.close()

        return [], "\n".join(text_pages)

    def _parse_text_tables(self, text: str) -> list[ParsedTable]:
        rows: list[list[str]] = []

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if "," in line:
                cells = [cell.strip() for cell in line.split(",")]
            elif "\t" in line:
                cells = [cell.strip() for cell in line.split("\t")]
            else:
                cells = [cell.strip() for cell in re.split(r"\s{2,}", line)]

            cells = [cell for cell in cells if cell != ""]
            if len(cells) >= 2:
                rows.append(cells)

        if not rows:
            return []

        header = rows[0]
        body = rows[1:] if len(rows) > 1 else []
        max_cols = max([len(header)] + [len(row) for row in body] + [1])
        columns = header + [f"col_{i}" for i in range(len(header), max_cols)]
        normalized_rows = [row + [""] * (len(columns) - len(row)) for row in body]

        return [
            ParsedTable(
                name="text_table",
                columns=columns,
                rows=normalized_rows,
            )
        ]
