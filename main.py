from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from src.config import load_config
from src.database import get_connection, init_db, record_uploaded_file, store_normalized
from src.ingestion.base import IngestionError, UnsupportedFileError
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


def _parser_for_file(path: Path):
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return PDFParser()
    if suffix in {".xlsx", ".xls", ".csv"}:
        return ExcelParser()
    if suffix == ".json":
        return JSONParser()

    raise UnsupportedFileError(f"Unsupported file type: {path}")


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stock-analysis-tool",
        description="Stock Analysis Tool v2.0 CLI runner",
    )
    parser.add_argument("--ticker", help="Online ticker to fetch from Screener.in")
    parser.add_argument("--file", help="Local file path to ingest")
    parser.add_argument("--config", help="Optional config.toml path")
    parser.add_argument("--gui", action="store_true", help="Launch Desktop GUI")

    args = parser.parse_args(argv)

    if args.gui or (not args.ticker and not args.file):
        from src.ui.main_window import launch_app
        return launch_app()

    try:
        config = load_config(args.config)
        conn = get_connection(config.database.path)
        init_db(conn)

        if args.file:
            path = Path(args.file).expanduser().resolve()
            source_parser = _parser_for_file(path)
            extract = source_parser.load(path)

            normalized = DataNormalizer().normalize(extract)
            validate_normalized(normalized)

            company_id = store_normalized(
                conn,
                normalized,
                source="file_upload",
                source_file=path.name,
            )

            record_uploaded_file(
                conn,
                company_id=company_id,
                filename=path.name,
                file_type=path.suffix.lstrip(".").lower(),
                file_hash=_md5(path),
                parse_status="success",
            )

            print(
                "stored "
                f"company_id={company_id} "
                f"ticker={normalized.company.ticker} "
                "source=file_upload "
                f"financial_lines={len(normalized.financials)} "
                f"prices={len(normalized.prices)} "
                f"shareholding_rows={len(normalized.shareholding)}"
            )
            return 0

        if args.ticker:
            scraper = ScreenerScraper()
            extract = scraper.load(args.ticker)

            normalized = DataNormalizer().normalize(extract)
            validate_normalized(normalized)

            company_id = store_normalized(
                conn,
                normalized,
                source="screener",
                source_file=None,
            )

            print(
                "stored "
                f"company_id={company_id} "
                f"ticker={normalized.company.ticker} "
                "source=screener "
                f"financial_lines={len(normalized.financials)} "
                f"prices={len(normalized.prices)} "
                f"shareholding_rows={len(normalized.shareholding)}"
            )
            return 0

        parser.print_help()
        return 1

    except (IngestionError, Exception) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(run_cli())
