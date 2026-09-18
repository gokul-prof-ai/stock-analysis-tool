from __future__ import annotations

import sqlite3

from ..database import DatabaseError, transaction
from ..models.forensic import ForensicReport


class ForensicRepository:
    """Persists forensic scores into SQLite."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def store_report(self, company_id: int, report: ForensicReport) -> int:
        try:
            with transaction(self._conn):
                self._conn.execute(
                    "DELETE FROM forensic_scores WHERE company_id = ? AND fiscal_year = ?",
                    (company_id, report.fiscal_year),
                )

                cursor = self._conn.execute(
                    """
                    INSERT INTO forensic_scores
                        (
                            company_id,
                            fiscal_year,
                            altman_z,
                            beneish_m,
                            piotroski_f,
                            benford_chi2,
                            fraud_probability
                        )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        company_id,
                        report.fiscal_year,
                        report.altman.z_score,
                        report.beneish.m_score,
                        report.piotroski.score,
                        report.benford.chi_square,
                        report.fraud_probability,
                    ),
                )

                return int(cursor.lastrowid or 0)
        except sqlite3.Error as exc:
            raise DatabaseError("Failed to store forensic report") from exc
