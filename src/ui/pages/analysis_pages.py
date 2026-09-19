from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.ui.chart_canvas import TradingViewChartCanvas


class ContentPage(QWidget):
    """Base page with title, dynamic tables and bullets."""

    def __init__(self, title: str) -> None:
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        heading = QLabel(title)
        heading.setObjectName("TitleLabel")
        outer.addWidget(heading)

        self._layout = QVBoxLayout()
        self._layout.setSpacing(12)
        outer.addLayout(self._layout)
        outer.addStretch(1)

    def clear_content(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def add_bullets(self, bullets: list[str]) -> None:
        for bullet in bullets:
            label = QLabel(f"• {bullet}")
            label.setObjectName("BulletLabel")
            label.setWordWrap(True)
            self._layout.addWidget(label)

    def add_table(self, title: str, headers: list[str], rows: list[list]) -> None:
        label = QLabel(title)
        label.setObjectName("SectionLabel")
        self._layout.addWidget(label)

        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setRowCount(len(rows))
        table.setAlternatingRowColors(True)

        for row_index, row in enumerate(rows):
            for col_index, value in enumerate(row):
                table.setItem(row_index, col_index, QTableWidgetItem("" if value is None else str(value)))

        self._layout.addWidget(table)


class RatiosPage(ContentPage):
    def __init__(self) -> None:
        super().__init__("Financial Ratios")

    def set_bundle(self, bundle) -> None:
        self.clear_content()

        if bundle.ratios is None:
            self.add_bullets(["Ratio analysis unavailable for this dataset."])
            return

        rows = [
            [ratio.category.replace("_", " ").title(), ratio.name.replace("_", " ").title(),
             "N/A" if ratio.value is None else f"{ratio.value:.4f}", ratio.status.replace("_", " ").title()]
            for ratio in bundle.ratios.ratios
        ]
        self.add_table(f"FY{bundle.ratios.fiscal_year} Ratios", ["Category", "Ratio", "Value", "Status"], rows)


class ForensicPage(ContentPage):
    def __init__(self) -> None:
        super().__init__("Forensic Analysis")

    def set_bundle(self, bundle) -> None:
        self.clear_content()

        if bundle.forensic is None:
            self.add_bullets(["Forensic analysis unavailable for this dataset."])
            return

        report = bundle.forensic
        self.add_bullets([
            f"Composite fraud probability: {report.fraud_probability if report.fraud_probability is not None else 'N/A'}%",
            f"Altman Z-Score: {report.altman.z_score if report.altman.z_score is not None else 'N/A'} ({report.altman.zone})",
            f"Beneish M-Score: {report.beneish.m_score if report.beneish.m_score is not None else 'N/A'}",
            f"Piotroski F-Score: {report.piotroski.score if report.piotroski.score is not None else 'N/A'}/9",
            f"Benford chi-square: {report.benford.chi_square if report.benford.chi_square is not None else 'N/A'}",
        ])

        if report.red_flags:
            self.add_table(
                "Red Flags",
                ["Severity", "Code", "Message"],
                [[flag.severity.upper(), flag.code, flag.message] for flag in report.red_flags],
            )


class ValuationPage(ContentPage):
    def __init__(self) -> None:
        super().__init__("Valuation")

    def set_bundle(self, bundle) -> None:
        self.clear_content()

        if bundle.valuation is None:
            self.add_bullets(["Valuation unavailable for this dataset."])
            return

        report = bundle.valuation

        self.add_bullets([
            f"Current price: {report.price if report.price is not None else 'N/A'}",
            f"Intrinsic value/share: {report.intrinsic_value if report.intrinsic_value is not None else 'N/A'}",
            f"Margin of safety: {report.margin_of_safety if report.margin_of_safety is not None else 'N/A'}%",
            f"Signal: {report.valuation_signal.upper()}",
        ])

        self.add_table(
            "Multiples",
            ["Metric", "Value"],
            [
                ["P/E", "N/A" if report.multiples.pe is None else f"{report.multiples.pe:.2f}"],
                ["P/B", "N/A" if report.multiples.pb is None else f"{report.multiples.pb:.2f}"],
                ["P/S", "N/A" if report.multiples.ps is None else f"{report.multiples.ps:.2f}"],
                ["EV/EBITDA", "N/A" if report.multiples.ev_ebitda is None else f"{report.multiples.ev_ebitda:.2f}"],
            ],
        )

        self.add_table(
            "Scenarios",
            ["Scenario", "DCF", "Comparable", "Final"],
            [
                [scenario.name,
                 "N/A" if scenario.dcf_intrinsic is None else f"{scenario.dcf_intrinsic:.2f}",
                 "N/A" if scenario.comparable_intrinsic is None else f"{scenario.comparable_intrinsic:.2f}",
                 "N/A" if scenario.final_intrinsic is None else f"{scenario.final_intrinsic:.2f}"]
                for scenario in report.scenarios
            ],
        )

        sensitivity_rows = []
        for wacc, row in zip(report.sensitivity.wacc_values, report.sensitivity.matrix):
            sensitivity_rows.append([f"{wacc:.2%}"] + ["N/A" if v is None else f"{v:.2f}" for v in row])

        if sensitivity_rows:
            headers = ["WACC"] + [f"{t:.2%}" for t in report.sensitivity.terminal_growth_values]
            self.add_table("DCF Sensitivity (intrinsic/share)", headers, sensitivity_rows)


class ScenarioPage(ContentPage):
    def __init__(self) -> None:
        super().__init__("Scenario & Forecast")

    def set_bundle(self, bundle) -> None:
        self.clear_content()

        if bundle.scenario is None:
            self.add_bullets(["Scenario analysis unavailable for this dataset."])
            return

        report = bundle.scenario

        self.add_bullets([
            f"Base target price: {report.base_target_price if report.base_target_price is not None else 'N/A'}",
            f"Target range: {report.target_price_lower if report.target_price_lower is not None else 'N/A'} "
            f"to {report.target_price_upper if report.target_price_upper is not None else 'N/A'}",
            f"Macro overlay adjustment: {report.macro.adjustment:.2%}",
        ])

        rows = []
        for scenario in report.scenarios:
            final_revenue = scenario.revenue[-1].value if scenario.revenue else None
            final_ebitda = scenario.ebitda[-1].value if scenario.ebitda else None
            final_eps = scenario.eps[-1].value if scenario.eps else None

            rows.append([
                scenario.name.title(),
                f"{scenario.growth_rate:.2%}",
                "N/A" if final_revenue is None else f"{final_revenue:,.2f}",
                "N/A" if final_ebitda is None else f"{final_ebitda:,.2f}",
                "N/A" if final_eps is None else f"{final_eps:.3f}",
                "N/A" if scenario.target_price is None else f"{scenario.target_price:.2f}",
                "N/A" if scenario.upside_pct is None else f"{scenario.upside_pct:.1f}%",
            ])

        self.add_table(
            "Three-Year Scenarios",
            ["Scenario", "Revenue Growth", "Final Revenue", "Final EBITDA", "Final EPS", "Target", "Upside"],
            rows,
        )


class ChartPage(QWidget):
    """TradingView-style chart workspace."""

    RANGES = [("1M", 22), ("6M", 132), ("1Y", 252), ("3Y", 756), ("5Y", 1260), ("10Y", None)]

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        self._range_buttons: list[QPushButton] = []
        for label, _ in self.RANGES:
            button = QPushButton(label)
            button.setObjectName("TfButton")
            button.setCheckable(True)
            button.clicked.connect(lambda _=False, text=label: self._select_range(text))
            toolbar.addWidget(button)
            self._range_buttons.append(button)

        self._range_buttons[-1].setChecked(True)

        toolbar.addStretch(1)
        self._hint = QLabel("Candles · Volume · SMA · Bollinger · RSI · MACD")
        self._hint.setObjectName("SubtitleLabel")
        toolbar.addWidget(self._hint)

        layout.addLayout(toolbar)

        self._placeholder = QLabel("No price data available for this company.")
        self._placeholder.setObjectName("SubtitleLabel")
        layout.addWidget(self._placeholder)

        self._canvas: TradingViewChartCanvas | None = None
        self._report = None
        layout.addStretch(1)

    def _select_range(self, label: str) -> None:
        for button, (text, rows) in zip(self._range_buttons, self.RANGES):
            button.setChecked(text == label)

        if self._canvas is not None:
            rows = dict(self.RANGES)[label]
            self._canvas.set_range(rows)

    def set_bundle(self, bundle) -> None:
        if self._canvas is not None:
            self._canvas.deleteLater()
            self._canvas = None

        if bundle.technical is None:
            self._placeholder.setVisible(True)
            return

        self._placeholder.setVisible(False)
        self._report = bundle.technical
        self._canvas = TradingViewChartCanvas(bundle.technical, bundle.company.company.ticker)
        self.layout().addWidget(self._canvas)
