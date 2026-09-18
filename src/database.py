from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from .models import NormalizedCompany

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY,
    ticker TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    sector TEXT,
    industry TEXT,
    source TEXT NOT NULL CHECK(source IN ('screener', 'file_upload')),
    source_file TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS financials (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    fiscal_year INTEGER NOT NULL,
    statement_type TEXT NOT NULL CHECK(statement_type IN ('balance_sheet', 'pnl', 'cashflow')),
    line_item TEXT NOT NULL,
    value REAL NOT NULL,
    UNIQUE(company_id, fiscal_year, statement_type, line_item)
);

CREATE TABLE IF NOT EXISTS ratios (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    fiscal_year INTEGER NOT NULL,
    ratio_name TEXT NOT NULL,
    value REAL,
    UNIQUE(company_id, fiscal_year, ratio_name)
);

CREATE TABLE IF NOT EXISTS forensic_scores (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    fiscal_year INTEGER NOT NULL,
    altman_z REAL,
    beneish_m REAL,
    piotroski_f INTEGER,
    benford_chi2 REAL,
    fraud_probability REAL
);

CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS shareholding (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    quarter TEXT NOT NULL,
    promoter_pct REAL,
    fii_pct REAL,
    dii_pct REAL,
    public_pct REAL
);

CREATE TABLE IF NOT EXISTS uploaded_files (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_hash TEXT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    parse_status TEXT NOT NULL CHECK(parse_status IN ('pending', 'success', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_financials_company_year ON financials(company_id, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_prices_company_date ON prices(company_id, date);
CREATE INDEX IF NOT EXISTS idx_shareholding_company_quarter ON shareholding(company_id, quarter);
CREATE INDEX IF NOT EXISTS idx_uploaded_files_company ON uploaded_files(company_id);
"""


class DatabaseError(Exception):
    """Raised for SQLite initialization or persistence failures."""


def get_connection(db_path: Path | str) -> sqlite3.Connection:
    """Create a SQLite connection with foreign keys enabled."""
    try:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except sqlite3.Error as exc:
        raise DatabaseError(f"Could not open database at {db_path}") from exc


def init_db(conn: sqlite3.Connection) -> None:
    """Create schema if missing."""
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    except sqlite3.Error as exc:
        raise DatabaseError("Failed to initialize database schema") from exc


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Atomic transaction context."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _upsert_company(
    conn: sqlite3.Connection,
    ticker: str,
    name: str,
    sector: Optional[str],
    industry: Optional[str],
    source: str,
    source_file: Optional[str],
) -> int:
    if source not in {"screener", "file_upload"}:
        raise DatabaseError(f"Invalid source: {source}")

    conn.execute(
        """
        INSERT INTO companies (ticker, name, sector, industry, source, source_file)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
            name = excluded.name,
            sector = excluded.sector,
            industry = excluded.industry,
            source = excluded.source,
            source_file = excluded.source_file
        """,
        (ticker, name, sector, industry, source, source_file),
    )

    row = conn.execute(
        "SELECT id FROM companies WHERE ticker = ?",
        (ticker,),
    ).fetchone()

    if row is None:
        raise DatabaseError(f"Failed to upsert company: {ticker}")

    return int(row["id"])


def store_normalized(
    conn: sqlite3.Connection,
    data: NormalizedCompany,
    source: str,
    source_file: Optional[str] = None,
) -> int:
    """Persist normalized company data, replacing existing company datasets."""
    try:
        with transaction(conn):
            company_id = _upsert_company(
                conn,
                ticker=data.company.ticker,
                name=data.company.name,
                sector=data.company.sector,
                industry=data.company.industry,
                source=source,
                source_file=source_file,
            )

            conn.execute("DELETE FROM financials WHERE company_id = ?", (company_id,))
            conn.execute("DELETE FROM prices WHERE company_id = ?", (company_id,))
            conn.execute("DELETE FROM shareholding WHERE company_id = ?", (company_id,))

            conn.executemany(
                """
                INSERT OR REPLACE INTO financials
                    (company_id, fiscal_year, statement_type, line_item, value)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        company_id,
                        line.fiscal_year,
                        line.statement_type,
                        line.line_item,
                        line.value,
                    )
                    for line in data.financials
                ],
            )

            conn.executemany(
                """
                INSERT INTO prices
                    (company_id, date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        company_id,
                        point.date.isoformat(),
                        point.open,
                        point.high,
                        point.low,
                        point.close,
                        point.volume,
                    )
                    for point in data.prices
                ],
            )

            conn.executemany(
                """
                INSERT INTO shareholding
                    (company_id, quarter, promoter_pct, fii_pct, dii_pct, public_pct)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        company_id,
                        row.quarter,
                        row.promoter_pct,
                        row.fii_pct,
                        row.dii_pct,
                        row.public_pct,
                    )
                    for row in data.shareholding
                ],
            )

            conn.execute(
                "DELETE FROM ratios WHERE company_id = ? AND ratio_name LIKE 'src:%'",
                (company_id,),
            )

            source_ratios = getattr(data, "source_ratios", {}) or {}
            ratio_rows = [
                (company_id, int(year), f"src:{name}", float(value))
                for name, by_year in source_ratios.items()
                for year, value in by_year.items()
            ]

            if ratio_rows:
                conn.executemany(
                    "INSERT OR REPLACE INTO ratios (company_id, fiscal_year, ratio_name, value) VALUES (?, ?, ?, ?)",
                    ratio_rows,
                )

            return company_id
    except sqlite3.Error as exc:
        raise DatabaseError("Failed to store normalized company data") from exc


def record_uploaded_file(
    conn: sqlite3.Connection,
    company_id: int,
    filename: str,
    file_type: str,
    file_hash: Optional[str],
    parse_status: str = "success",
) -> int:
    """Track uploaded file metadata."""
    if parse_status not in {"pending", "success", "failed"}:
        raise DatabaseError(f"Invalid parse_status: {parse_status}")

    try:
        with transaction(conn):
            cursor = conn.execute(
                """
                INSERT INTO uploaded_files
                    (company_id, filename, file_type, file_hash, parse_status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (company_id, filename, file_type, file_hash, parse_status),
            )
            return int(cursor.lastrowid or 0)
    except sqlite3.Error as exc:
        raise DatabaseError("Failed to record uploaded file") from exc
