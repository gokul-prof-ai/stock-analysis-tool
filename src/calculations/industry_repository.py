from __future__ import annotations

import sqlite3


class IndustryRepository:
    """Repository helpers for industry analysis."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def all_tickers(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT ticker FROM companies ORDER BY ticker"
        ).fetchall()

        return [row["ticker"] for row in rows]
