from __future__ import annotations

from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.calculations.financial_extractor import FinancialExtractor
from src.ui.widgets import StatTile


def build_company_narrative(company, bundle) -> str:
    """Auto-generate the company summary narrative."""
    profile = company.company
    years = sorted({line.fiscal_year for line in company.financials})

    sentences = [
        f"{profile.name} ({profile.ticker}) is analysed in the "
        f"{profile.sector or 'unclassified'} sector"
        + (f", {profile.industry} industry" if profile.industry else "")
        + "."
    ]

    if years:
        sentences.append(
            f"The dataset covers fiscal years {years[0]}-{years[-1]} with "
            f"{len(company.financials)} statement lines, {len(company.prices)} price points "
            f"and {len(company.shareholding)} shareholding records."
        )

        extractor = FinancialExtractor(company)
        snapshot = extractor.snapshot(years[-1])

        revenue = snapshot.get("revenue")
        net_profit = snapshot.get("net_profit")
        total_assets = snapshot.get("total_assets")
        total_equity = snapshot.get("total_equity")

        if revenue is not None and net_profit is not None:
            margin = 100.0 * net_profit / revenue if revenue else 0.0
            sentences.append(
                f"In FY{years[-1]} revenue stood at {revenue:,.2f} with net profit "
                f"{net_profit:,.2f} (net margin {margin:.1f}%)."
            )

        if total_assets is not None and total_equity is not None:
            sentences.append(
                f"Total assets of {total_assets:,.2f} against equity of {total_equity:,.2f} "
                f"imply an equity multiplier of {total_assets / total_equity:.2f}x."
            )

    if getattr(bundle, "forensic", None) is not None and bundle.forensic.fraud_probability is not None:
        sentences.append(
            f"Forensic screening assigns a composite fraud probability of "
            f"{bundle.forensic.fraud_probability:.1f}% (Altman zone: {bundle.forensic.altman.zone})."
        )

    if getattr(bundle, "valuation", None) is not None and bundle.valuation.intrinsic_value is not None:
        sentences.append(
            f"Valuation indicates '{bundle.valuation.valuation_signal}' with intrinsic value "
            f"{bundle.valuation.intrinsic_value:.2f} per share."
        )

    if getattr(bundle, "decision", None) is not None:
        sentences.append(f"The investment engine recommends {bundle.decision.recommendation.upper()}.")

    return " ".join(sentences)


class SummaryPage(QWidget):
    """Company Summary section (TradingView-style overview)."""

    def __init__(self) -> None:
        super().__init__()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(12)

        placeholder = QLabel("No company loaded. Fetch online data or upload a report.")
        placeholder.setObjectName("SubtitleLabel")
        self._layout.addWidget(placeholder)
        self._layout.addStretch(1)

    def set_bundle(self, bundle) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        company = bundle.company
        profile = company.company

        header = QHBoxLayout()
        title = QLabel(profile.name)
        title.setObjectName("TitleLabel")
        header.addWidget(title)

        for chip_text in [profile.ticker, profile.sector or "no-sector", profile.industry or "no-industry"]:
            chip = QLabel(chip_text)
            chip.setObjectName("ChipLabel")
            header.addWidget(chip)

        header.addStretch(1)
        self._layout.addLayout(header)

        narrative = QLabel(build_company_narrative(company, bundle))
        narrative.setObjectName("BulletLabel")
        narrative.setWordWrap(True)
        self._layout.addWidget(narrative)

        extractor = FinancialExtractor(company)
        years = extractor.fiscal_years()

        if years:
            snapshot = extractor.snapshot(years[-1])

            tiles = [
                ("REVENUE", snapshot.get("revenue")),
                ("NET PROFIT", snapshot.get("net_profit")),
                ("TOTAL ASSETS", snapshot.get("total_assets")),
                ("TOTAL EQUITY", snapshot.get("total_equity")),
                ("CASH", snapshot.get("cash_and_equivalents")),
                ("TOTAL DEBT", snapshot.get("total_debt")),
            ]

            grid = QGridLayout()
            grid.setSpacing(8)

            for index, (label, value) in enumerate(tiles):
                text = "N/A" if value is None else f"{value:,.2f}"
                grid.addWidget(StatTile(label, text), index // 4, index % 4)

            self._layout.addLayout(grid)

            statement_rows = []
            for statement_type, statement_label in [
                ("pnl", "Profit & Loss"),
                ("balance_sheet", "Balance Sheet"),
                ("cashflow", "Cash Flow"),
            ]:
                items = {}
                for year in years:
                    year_snapshot = extractor.snapshot(year)
                    items[year] = year_snapshot

                keys = []
                for line in company.financials:
                    if line.statement_type == statement_type and line.line_item not in keys:
                        keys.append(line.line_item)

                if not keys:
                    continue

                table = QTableWidget()
                table.setColumnCount(len(years) + 1)
                table.setHorizontalHeaderLabels(["Line Item"] + [str(year) for year in years])
                table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
                table.setRowCount(min(len(keys), 12))
                table.setAlternatingRowColors(True)

                values_by_year = {
                    year: {line.line_item: line.value for line in company.financials
                           if line.fiscal_year == year and line.statement_type == statement_type}
                    for year in years
                }

                for row, key in enumerate(keys[:12]):
                    table.setItem(row, 0, QTableWidgetItem(key))
                    for col, year in enumerate(years, start=1):
                        value = values_by_year[year].get(key)
                        table.setItem(row, col, QTableWidgetItem("N/A" if value is None else f"{value:,.2f}"))

                label = QLabel(statement_label)
                label.setObjectName("SectionLabel")
                self._layout.addWidget(label)
                self._layout.addWidget(table)

        if company.shareholding:
            label = QLabel("Shareholding Pattern")
            label.setObjectName("SectionLabel")
            self._layout.addWidget(label)

            table = QTableWidget()
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(["Quarter", "Promoter %", "FII %", "DII %", "Public %"])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            table.setRowCount(len(company.shareholding))
            table.setAlternatingRowColors(True)

            for row, item in enumerate(company.shareholding):
                table.setItem(row, 0, QTableWidgetItem(item.quarter))
                for col, value in enumerate([item.promoter_pct, item.fii_pct, item.dii_pct, item.public_pct], start=1):
                    table.setItem(row, col, QTableWidgetItem("N/A" if value is None else f"{value:.2f}"))

            self._layout.addWidget(table)

        if bundle.assumptions:
            label = QLabel("Data Notes & Assumptions")
            label.setObjectName("SectionLabel")
            self._layout.addWidget(label)

            for assumption in bundle.assumptions:
                bullet = QLabel(f"• {assumption}")
                bullet.setObjectName("BulletLabel")
                bullet.setWordWrap(True)
                self._layout.addWidget(bullet)

        self._layout.addStretch(1)
