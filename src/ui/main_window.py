from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .analysis_bundle import AnalysisWorker
from .ingestion_widget import IngestionWidget
from .pages.analysis_pages import ChartPage, ForensicPage, RatiosPage, ScenarioPage, ValuationPage
from .pages.decision_page import DecisionPage
from .pages.summary_page import SummaryPage
from .workers import IngestionWorker

NAV_ITEMS = [
    ("SUMMARY", 1),
    ("CHART", 2),
    ("RATIOS", 3),
    ("FORENSIC", 4),
    ("VALUATION", 5),
    ("SCENARIO", 6),
    ("DECISION", 7),
]


class MainWindow(QMainWindow):
    """TradingView-style workspace: toolbar, nav rail, stacked pages, key-stats panel."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Stock Analysis Tool v2.0")
        self.resize(1440, 860)
        self.setMinimumSize(1100, 700)

        self._bundle = None
        self._analysis_worker: AnalysisWorker | None = None
        self._ingestion_worker: IngestionWorker | None = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        toolbar = QWidget()
        toolbar.setObjectName("Toolbar")
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 8, 10, 6)
        toolbar_layout.setSpacing(6)

        top_row = QHBoxLayout()
        logo = QLabel("◧ SAT v2.0")
        logo.setObjectName("LogoLabel")
        top_row.addWidget(logo)

        top_row.addSpacing(24)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search company or ticker...")
        self.search_input.setFixedWidth(340)
        self.search_input.returnPressed.connect(self._toolbar_fetch)
        top_row.addWidget(self.search_input)

        self.toolbar_fetch_btn = QPushButton("Fetch")
        self.toolbar_fetch_btn.setObjectName("FetchButton")
        self.toolbar_fetch_btn.clicked.connect(self._toolbar_fetch)
        top_row.addWidget(self.toolbar_fetch_btn)

        self.toolbar_upload_btn = QPushButton("Upload")
        self.toolbar_upload_btn.setObjectName("SecondaryButton")
        self.toolbar_upload_btn.clicked.connect(self._toolbar_upload)
        top_row.addWidget(self.toolbar_upload_btn)

        top_row.addStretch(1)

        self.export_btn = QPushButton("Export PDF / DOCX")
        self.export_btn.setObjectName("PrimaryButton")
        self.export_btn.clicked.connect(self._export_report)
        self.export_btn.setEnabled(False)
        top_row.addWidget(self.export_btn)

        toolbar_layout.addLayout(top_row)

        nav_row = QHBoxLayout()
        nav_row.setSpacing(2)

        self._nav_buttons: list[QPushButton] = []
        for label, _ in NAV_ITEMS:
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setEnabled(False)
            button.clicked.connect(lambda _=False, text=label: self._show_page(text))
            nav_row.addWidget(button)
            self._nav_buttons.append(button)

        nav_row.addStretch(1)

        self.status_label = QLabel("Ready. Search a company or upload a report.")
        self.status_label.setObjectName("StatusLabel")
        nav_row.addWidget(self.status_label)

        toolbar_layout.addLayout(nav_row)
        root.addWidget(toolbar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.stack = QStackedWidget()

        self.ingestion_page = IngestionWidget()
        self.summary_page = SummaryPage()
        self.chart_page = ChartPage()
        self.ratios_page = RatiosPage()
        self.forensic_page = ForensicPage()
        self.valuation_page = ValuationPage()
        self.scenario_page = ScenarioPage()
        self.decision_page = DecisionPage()

        self.stack.addWidget(self.ingestion_page)
        self.stack.addWidget(self.summary_page)
        self.stack.addWidget(self.chart_page)
        self.stack.addWidget(self.ratios_page)
        self.stack.addWidget(self.forensic_page)
        self.stack.addWidget(self.valuation_page)
        self.stack.addWidget(self.scenario_page)
        self.stack.addWidget(self.decision_page)

        body.addWidget(self.stack, stretch=1)

        right_panel = QWidget()
        right_panel.setObjectName("RightPanel")
        right_panel.setFixedWidth(250)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(10)

        panel_title = QLabel("KEY STATS")
        panel_title.setObjectName("PanelTitle")
        right_layout.addWidget(panel_title)

        self._stat_labels: dict[str, QLabel] = {}
        for key in ["Price", "P/E", "P/B", "ROE", "D/E", "Fraud %", "Upside %", "Decision"]:
            label_widget = QLabel(key)
            label_widget.setObjectName("StatLabel")
            right_layout.addWidget(label_widget)

            value_widget = QLabel("--")
            value_widget.setObjectName("StatValue")
            right_layout.addWidget(value_widget)
            self._stat_labels[key] = value_widget

        right_layout.addStretch(1)
        body.addWidget(right_panel)

        root.addLayout(body, stretch=1)

        self.ingestion_page.analysis_requested.connect(self._load_company)

    def _toolbar_fetch(self) -> None:
        text = self.search_input.text().strip()

        if not text:
            QMessageBox.warning(self, "Input Required", "Enter a company name or ticker.")
            return

        self._start_ingestion(ticker=text, file_path=None)

    def _toolbar_upload(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Financial Report",
            "",
            "Supported Files (*.pdf *.xlsx *.xls *.csv *.json)",
        )
        if path:
            self._start_ingestion(ticker=None, file_path=path)

    def _start_ingestion(self, ticker: str | None, file_path: str | None) -> None:
        self.status_label.setText("Ingesting data...")
        self._ingestion_worker = IngestionWorker(ticker, file_path)
        self._ingestion_worker.finished.connect(self._load_company)
        self._ingestion_worker.error.connect(self._ingestion_error)
        self._ingestion_worker.start()

    def _ingestion_error(self, message: str) -> None:
        self.status_label.setText(f"Ingestion failed: {message}")
        error_text = "Failed to process data:\n\n" + message
        QMessageBox.critical(self, "Ingestion Error", error_text)

    def _load_company(self, ticker: str) -> None:
        self.status_label.setText(f"Computing analysis for {ticker}...")
        self._analysis_worker = AnalysisWorker(ticker)
        self._analysis_worker.done.connect(self._on_bundle)
        self._analysis_worker.error.connect(self._analysis_error)
        self._analysis_worker.start()

    def _analysis_error(self, message: str) -> None:
        self.status_label.setText(f"Analysis failed: {message}")
        QMessageBox.critical(self, "Analysis Error", message)

    def _on_bundle(self, bundle) -> None:
        self._bundle = bundle

        for page in [
            self.summary_page,
            self.chart_page,
            self.ratios_page,
            self.forensic_page,
            self.valuation_page,
            self.scenario_page,
            self.decision_page,
        ]:
            page.set_bundle(bundle)

        self._populate_right_panel(bundle)

        for button in self._nav_buttons:
            button.setEnabled(True)

        self.export_btn.setEnabled(True)
        self._show_page("SUMMARY")
        self.status_label.setText(f"Analysis ready: {bundle.company.company.ticker}")

    def _populate_right_panel(self, bundle) -> None:
        valuation = bundle.valuation
        ratios = bundle.ratios
        forensic = bundle.forensic
        scenario = bundle.scenario

        def ratio_value(name: str):
            if ratios is None:
                return None
            item = ratios.get(name)
            return item.value if item is not None else None

        upside = None
        if scenario is not None:
            base = next((s for s in scenario.scenarios if s.name == "base"), None)
            upside = base.upside_pct if base is not None else None

        values = {
            "Price": valuation.price if valuation is not None else None,
            "P/E": valuation.multiples.pe if valuation is not None else None,
            "P/B": valuation.multiples.pb if valuation is not None else None,
            "ROE": (ratio_value("roe") * 100.0) if ratio_value("roe") is not None else None,
            "D/E": ratio_value("debt_to_equity"),
            "Fraud %": forensic.fraud_probability if forensic is not None else None,
            "Upside %": upside,
        }

        for key, value in values.items():
            label = self._stat_labels[key]
            label.setText("N/A" if value is None else f"{value:,.2f}")

        decision_label = self._stat_labels["Decision"]
        if bundle.decision is not None:
            decision_label.setText(bundle.decision.recommendation.upper())
            decision_label.setObjectName(
                "PosValue" if bundle.decision.recommendation == "buy"
                else ("NegValue" if bundle.decision.recommendation == "avoid" else "StatValue")
            )
        else:
            decision_label.setText("N/A")
        decision_label.style().unpolish(decision_label)
        decision_label.style().polish(decision_label)

    def _show_page(self, label: str) -> None:
        index = dict(NAV_ITEMS)[label]

        for button, (text, _) in zip(self._nav_buttons, NAV_ITEMS):
            button.setChecked(text == label)

        self.stack.setCurrentIndex(index)

    def _export_report(self) -> None:
        if self._bundle is None:
            return

        ticker = self._bundle.company.company.ticker

        try:
            from src.reports.docx_generator import generate_docx
            from src.reports.pdf_generator import generate_pdf
            from src.reports.report_builder import ReportBuilder

            output_dir = Path("data/reports") / ticker
            builder = ReportBuilder(chart_dir=output_dir / "charts")
            report = builder.build(self._bundle.company, [])

            pdf_path = generate_pdf(report, output_dir / f"{ticker}_analysis_report.pdf")
            docx_path = generate_docx(report, output_dir / f"{ticker}_analysis_report.docx")

            self.status_label.setText(f"Report exported for {ticker}")
            QMessageBox.information(
                self,
                "Export Successful",
                "PDF: " + str(pdf_path.resolve()) + "\nDOCX: " + str(docx_path.resolve()),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))


def launch_app() -> int:
    """Initialize and run the PySide6 application with the TradingView theme."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Stock Analysis Tool")
    app.setOrganizationName("FinTool")
    app.setFont(QFont("Trebuchet MS", 10))

    theme_path = Path(__file__).parent / "styles" / "tradingview.qss"
    if theme_path.exists():
        app.setStyleSheet(theme_path.read_text(encoding="utf-8"))

    window = MainWindow()
    window.show()
    return app.exec()
