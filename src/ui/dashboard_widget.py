from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.calculations.forensic import ForensicAnalyzer
from src.calculations.ratios import RatioCalculator
from src.calculations.repository import RatioRepository
from src.calculations.scenario import ScenarioAnalyzer
from src.calculations.technical import TechnicalAnalyzer
from src.calculations.valuation import ValuationEngine
from src.config import load_config
from src.database import get_connection, init_db
from src.reports.pdf_generator import generate_pdf
from src.reports.report_builder import ReportBuilder


class DashboardWidget(QWidget):
    """Central dashboard displaying analysis tabs for the loaded company."""

    back_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.current_ticker: str | None = None
        self._company = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header_layout = QHBoxLayout()

        self.back_btn = QPushButton("← Analyze Another")
        self.back_btn.setObjectName("SecondaryButton")
        self.back_btn.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(self.back_btn)

        self.title_label = QLabel("Company Dashboard")
        self.title_label.setObjectName("MainTitle")
        self.title_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(self.title_label, stretch=1)

        self.export_btn = QPushButton("Export PDF Report")
        self.export_btn.setObjectName("PrimaryButton")
        self.export_btn.clicked.connect(self._export_report)
        header_layout.addWidget(self.export_btn)

        layout.addLayout(header_layout)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("DashboardTabs")
        layout.addWidget(self.tabs)

    def load_company(self, ticker: str) -> None:
        self.current_ticker = ticker
        self.title_label.setText(f"Analysis Dashboard: {ticker}")
        self.tabs.clear()

        try:
            config = load_config()
            conn = get_connection(config.database.path)
            init_db(conn)

            repo = RatioRepository(conn)
            self._company = repo.load_normalized_company(ticker)

            self._add_ratios_tab()
            self._add_forensic_tab()
            
            if self._company.prices:
                self._add_technical_tab()
                
            self._add_valuation_tab()
            self._add_scenario_tab()

        except Exception as exc:
            error_text = "Error loading data:\n" + traceback.format_exc()
            error_label = QLabel(error_text)
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: red; padding: 20px;")
            self.tabs.addTab(error_label, "Error")

    def _add_ratios_tab(self) -> None:
        ratio_set = RatioCalculator().calculate_all(self._company)
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Category", "Ratio", "Value", "Status"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setRowCount(len(ratio_set.ratios))

        for row, ratio in enumerate(ratio_set.ratios):
            table.setItem(row, 0, QTableWidgetItem(ratio.category.replace("_", " ").title()))
            table.setItem(row, 1, QTableWidgetItem(ratio.name.replace("_", " ").title()))
            val = f"{ratio.value:.4f}" if ratio.value is not None else "N/A"
            table.setItem(row, 2, QTableWidgetItem(val))
            table.setItem(row, 3, QTableWidgetItem(ratio.status.replace("_", " ").title()))

        self.tabs.addTab(table, "Financial Ratios")

    def _add_forensic_tab(self) -> None:
        forensic = ForensicAnalyzer().analyze(self._company)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        layout.addWidget(self._kpi_label(f"Fraud Probability: {forensic.fraud_probability or 0:.1f}%"))
        layout.addWidget(self._kpi_label(f"Altman Z-Score: {forensic.altman.z_score or 'N/A'} ({forensic.altman.zone.title()})"))
        layout.addWidget(self._kpi_label(f"Beneish M-Score: {forensic.beneish.m_score or 'N/A'}"))
        layout.addWidget(self._kpi_label(f"Piotroski F-Score: {forensic.piotroski.score or 'N/A'}/9"))

        if forensic.red_flags:
            layout.addSpacing(20)
            layout.addWidget(QLabel("Red Flags:"))
            for flag in forensic.red_flags:
                layout.addWidget(QLabel(f"• [{flag.severity.upper()}] {flag.code}: {flag.message}"))

        layout.addStretch()
        self.tabs.addTab(widget, "Forensic Analysis")

    def _add_technical_tab(self) -> None:
        tech = TechnicalAnalyzer().analyze_prices(self._company.prices, self.current_ticker)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        layout.addWidget(self._kpi_label(f"Latest Close: {tech.latest_close:.2f}"))
        layout.addWidget(self._kpi_label(f"Trend: {tech.trend.replace('_', ' ').title()}"))
        layout.addWidget(self._kpi_label(f"RSI (14): {tech.latest_rsi or 'N/A'}"))
        layout.addWidget(self._kpi_label(f"Support Levels: {[round(s, 2) for s in tech.support_levels]}"))
        layout.addWidget(self._kpi_label(f"Resistance Levels: {[round(r, 2) for r in tech.resistance_levels]}"))

        if tech.patterns:
            layout.addSpacing(20)
            layout.addWidget(QLabel("Detected Patterns:"))
            for pattern in tech.patterns[-5:]:
                layout.addWidget(QLabel(f"• {pattern.date}: {pattern.name.replace('_', ' ').title()} ({pattern.direction})"))

        layout.addStretch()
        self.tabs.addTab(widget, "Technical Analysis")

    def _add_valuation_tab(self) -> None:
        valuation = ValuationEngine().analyze(self._company, [])
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        layout.addWidget(self._kpi_label(f"Current Price: {valuation.price or 'N/A'}"))
        layout.addWidget(self._kpi_label(f"Intrinsic Value: {valuation.intrinsic_value or 'N/A'}"))
        layout.addWidget(self._kpi_label(f"Margin of Safety: {valuation.margin_of_safety or 'N/A'}%"))
        layout.addWidget(self._kpi_label(f"Valuation Signal: {valuation.valuation_signal.upper()}"))

        layout.addStretch()
        self.tabs.addTab(widget, "Valuation")

    def _add_scenario_tab(self) -> None:
        scenario = ScenarioAnalyzer().analyze(self._company)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        layout.addWidget(self._kpi_label(f"Base Target Price: {scenario.base_target_price or 'N/A'}"))
        layout.addWidget(self._kpi_label(f"Target Range: {scenario.target_price_lower or 'N/A'} to {scenario.target_price_upper or 'N/A'}"))
        
        layout.addSpacing(20)
        layout.addWidget(QLabel("Scenario Forecasts:"))
        for s in scenario.scenarios:
            final_rev = s.revenue[-1].value if s.revenue else None
            layout.addWidget(QLabel(f"• {s.name.title()}: Target {s.target_price or 'N/A'} | Upside {s.upside_pct or 'N/A'}% | Final Rev {final_rev or 'N/A'}"))

        layout.addStretch()
        self.tabs.addTab(widget, "Scenarios")

    def _export_report(self) -> None:
        if not self.current_ticker or not self._company:
            return

        try:
            output_dir = Path("data/reports") / self.current_ticker
            builder = ReportBuilder(chart_dir=output_dir / "charts")
            report = builder.build(self._company, [])
            pdf_path = generate_pdf(report, output_dir / f"{self.current_ticker}_report.pdf")
            msg_text = "Report saved to:\n" + str(pdf_path.resolve())
            QMessageBox.information(self, "Export Successful", msg_text)
        except Exception as exc:
            err_text = "Failed to generate PDF:\n" + str(exc)
            QMessageBox.critical(self, "Export Failed", err_text)

    def _kpi_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-size: 16px; font-weight: 500;")
        return label
