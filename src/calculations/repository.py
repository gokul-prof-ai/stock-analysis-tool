from __future__ import annotations

import sqlite3
from datetime import date
from typing import Iterable

from ..database import DatabaseError, transaction
from ..models import CompanyProfile, FinancialLine, NormalizedCompany, PricePoint, ShareholdingPoint
from ..models.ratios import RatioResult


class RatioRepository:
    """Loads normalized companies and stores ratio results."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_company_id(self, ticker: str) -> int:
        row = self._conn.execute(
            "SELECT id FROM companies WHERE ticker = ?",
            (ticker,),
        ).fetchone()

        if row is None:
            raise DatabaseError(f"Company not found: {ticker}")

        return int(row["id"])

    def load_normalized_company(self, ticker: str) -> NormalizedCompany:
        company_row = self._conn.execute(
            "SELECT id, ticker, name, sector, industry FROM companies WHERE ticker = ?",
            (ticker,),
        ).fetchone()

        if company_row is None:
            raise DatabaseError(f"Company not found: {ticker}")

        company_id = int(company_row["id"])

        financial_rows = self._conn.execute(
            """
            SELECT fiscal_year, statement_type, line_item, value
            FROM financials
            WHERE company_id = ?
            ORDER BY fiscal_year, statement_type, line_item
            """,
            (company_id,),
        ).fetchall()

        price_rows = self._conn.execute(
            """
            SELECT date, open, high, low, close, volume
            FROM prices
            WHERE company_id = ?
            ORDER BY date
            """,
            (company_id,),
        ).fetchall()

        shareholding_rows = self._conn.execute(
            """
            SELECT quarter, promoter_pct, fii_pct, dii_pct, public_pct
            FROM shareholding
            WHERE company_id = ?
            ORDER BY quarter
            """,
            (company_id,),
        ).fetchall()

        financials = [
            FinancialLine(
                fiscal_year=row["fiscal_year"],
                statement_type=row["statement_type"],
                line_item=row["line_item"],
                value=row["value"],
            )
            for row in financial_rows
        ]

        prices: list[PricePoint] = []
        for row in price_rows:
            try:
                price_date = date.fromisoformat(row["date"])
            except ValueError:
                continue

            prices.append(
                PricePoint(
                    date=price_date,
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                )
            )

        shareholding = [
            ShareholdingPoint(
                quarter=row["quarter"],
                promoter_pct=row["promoter_pct"],
                fii_pct=row["fii_pct"],
                dii_pct=row["dii_pct"],
                public_pct=row["public_pct"],
            )
            for row in shareholding_rows
        ]

        source_ratio_rows = self._conn.execute(
            "SELECT fiscal_year, ratio_name, value FROM ratios WHERE company_id = ? AND ratio_name LIKE 'src:%'",
            (company_id,),
        ).fetchall()

        source_ratios: dict[str, dict[int, float]] = {}
        for row in source_ratio_rows:
            source_ratios.setdefault(row["ratio_name"][4:], {})[row["fiscal_year"]] = row["value"]

        return NormalizedCompany(
            company=CompanyProfile(
                ticker=company_row["ticker"],
                name=company_row["name"],
                sector=company_row["sector"],
                industry=company_row["industry"],
            ),
            financials=financials,
            prices=prices,
            shareholding=shareholding,
            source_ratios=source_ratios,
        )

    def store_ratios(self, company_id: int, results: Iterable[RatioResult]) -> int:
        params = [
            (company_id, result.fiscal_year, result.name, result.value)
            for result in results
        ]

        if not params:
            return 0

        with transaction(self._conn):
            self._conn.executemany(
                """
                INSERT OR REPLACE INTO ratios
                    (company_id, fiscal_year, ratio_name, value)
                VALUES (?, ?, ?, ?)
                """,
                params,
            )

        return len(params)
