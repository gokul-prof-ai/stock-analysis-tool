from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from src.config import load_config
from src.database import get_connection, init_db, record_uploaded_file, store_normalized
from src.ingestion.excel_parser import ExcelParser
from src.ingestion.json_parser import JSONParser
from src.ingestion.normalizer import DataNormalizer
from src.ingestion.pdf_parser import PDFParser
from src.ingestion.screener import ScreenerScraper
from src.ingestion.validator import validate_normalized


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SearchWorker(QThread):
    """Background Screener.in company search for autocomplete suggestions."""

    results_ready = Signal(list)
    search_failed = Signal(str)

    def __init__(self, query: str) -> None:
        super().__init__()
        self.query = query

    def run(self) -> None:
        try:
            results = ScreenerScraper(timeout=10).search_companies(self.query, limit=8)
            self.results_ready.emit(results)
        except Exception as exc:
            self.search_failed.emit(str(exc))


class IngestionWorker(QThread):
    """Background thread to prevent UI freezing during data ingestion."""

    finished = Signal(str)
    error = Signal(str)

    def __init__(self, ticker: str | None, file_path: str | None) -> None:
        super().__init__()
        self.ticker = ticker
        self.file_path = file_path

    def run(self) -> None:
        try:
            config = load_config()
            conn = get_connection(config.database.path)
            init_db(conn)

            if self.file_path:
                path = Path(self.file_path).expanduser().resolve()
                suffix = path.suffix.lower()

                if suffix == ".pdf":
                    parser = PDFParser()
                elif suffix in {".xlsx", ".xls", ".csv"}:
                    parser = ExcelParser()
                elif suffix == ".json":
                    parser = JSONParser()
                else:
                    raise ValueError(f"Unsupported file type: {suffix}")

                extract = parser.load(path)
                normalized = DataNormalizer().normalize(extract)
                validate_normalized(normalized)

                company_id = store_normalized(
                    conn, normalized, source="file_upload", source_file=path.name
                )
                record_uploaded_file(
                    conn,
                    company_id=company_id,
                    filename=path.name,
                    file_type=suffix.lstrip("."),
                    file_hash=_md5(path),
                    parse_status="success",
                )

                self.finished.emit(normalized.company.ticker)

            elif self.ticker:
                scraper = ScreenerScraper()
                extract = scraper.load(self.ticker)
                normalized = DataNormalizer().normalize(extract)
                validate_normalized(normalized)

                store_normalized(conn, normalized, source="screener", source_file=None)
                self.finished.emit(normalized.company.ticker)

        except Exception as exc:
            self.error.emit(str(exc))
