from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from src.calculations.decision import DecisionEngine
from src.calculations.risk import RiskAnalyzer
from src.models import CompanyProfile, FinancialLine, NormalizedCompany, PricePoint
from src.reports.checklist import build_checklist
from src.reports.docx_generator import generate_docx
from src.reports.pdf_generator import generate_pdf
from src.reports.report_builder import ReportBuilder

PNL_ITEMS = {
    "Revenue",
    "EBITDA",
    "Net Profit",
}

CASH_ITEMS = {
    "Operating Cash Flow",
    "Capital Expenditure",
}


def _prices(count: int = 20) -> list[PricePoint]:
    start = date(2023, 1, 2)
    prices: list[PricePoint] = []

    for index in range(count):
        close = 20.0 + 0.10 * index
        day = start + timedelta(days=index)

        prices.append(
            PricePoint(
                date=day,
                open=close,
                high=close + 0.5,
                low=max(close - 0.5, 0.01),
                close=close,
                volume=1000,
            )
        )

    return prices


def _company() -> NormalizedCompany:
    years_values = {
        2022: {
            "Revenue": 1000.0,
            "EBITDA": 200.0,
            "Net Profit": 100.0,
            "Total Equity": 500.0,
            "Total Assets": 1000.0,
            "Current Assets": 300.0,
            "Current Liabilities": 200.0,
            "Total Debt": 200.0,
            "Cash and Equivalents": 50.0,
            "Shares Outstanding": 100.0,
            "Operating Cash Flow": 120.0,
            "Capital Expenditure": 30.0,
        },
        2023: {
            "Revenue": 1100.0,
            "EBITDA": 220.0,
            "Net Profit": 120.0,
            "Total Equity": 560.0,
            "Total Assets": 1100.0,
            "Current Assets": 330.0,
            "Current Liabilities": 220.0,
            "Total Debt": 200.0,
            "Cash and Equivalents": 60.0,
            "Shares Outstanding": 100.0,
            "Operating Cash Flow": 140.0,
            "Capital Expenditure": 35.0,
        },
    }

    financials: list[FinancialLine] = []

    for fiscal_year, values in years_values.items():
        for line_item, value in values.items():
            if line_item in CASH_ITEMS:
                statement_type = "cashflow"
            elif line_item in PNL_ITEMS:
                statement_type = "pnl"
            else:
                statement_type = "balance_sheet"

            financials.append(
                FinancialLine(
                    fiscal_year=fiscal_year,
                    statement_type=statement_type,
                    line_item=line_item,
                    value=float(value),
                )
            )

    return NormalizedCompany(
        company=CompanyProfile(ticker="TEST", name="Test Report Company", sector="testing"),
        financials=financials,
        prices=_prices(),
    )


def _build_report(tmp_path: Path):
    builder = ReportBuilder(chart_dir=tmp_path / "charts")
    return builder.build(_company(), [])


def test_report_builder(tmp_path):
    report = _build_report(tmp_path)

    assert report.ticker == "TEST"
    assert report.executive_summary
    assert report.sections
    assert len(report.checklist) == 227
    assert report.investment_decision.recommendation in {"buy", "hold", "avoid", "unavailable"}
    assert len(report.chart_paths) == 5

    for chart_path in report.chart_paths.values():
        assert Path(chart_path).exists()


def test_pdf_and_docx_generation(tmp_path):
    report = _build_report(tmp_path)

    pdf_path = generate_pdf(report, tmp_path / "report.pdf", include_checklist=False)
    docx_path = generate_docx(report, tmp_path / "report.docx", include_checklist=False)

    assert pdf_path.exists()
    assert docx_path.exists()
    assert pdf_path.stat().st_size > 0
    assert docx_path.stat().st_size > 0


def test_checklist_mapping():
    items = build_checklist({})

    assert len(items) == 227

    item_ids = [item.item_id for item in items]

    assert len(set(item_ids)) == 227


def test_risk_metrics():
    analyzer = RiskAnalyzer()
    metrics = analyzer.analyze_prices(_prices(30))

    assert metrics.observation_count == 30
    assert metrics.annualized_volatility is not None
    assert metrics.max_drawdown is not None
    assert metrics.var_95 is not None


def test_decision_engine():
    engine = DecisionEngine()

    bullish = engine.decide(
        valuation_report=SimpleNamespace(valuation_signal="undervalued"),
        forensic_report=SimpleNamespace(fraud_probability=10.0, piotroski=SimpleNamespace(score=8)),
        scenario_report=SimpleNamespace(scenarios=[SimpleNamespace(name="base", upside_pct=35.0)]),
        technical_report=SimpleNamespace(trend="uptrend"),
    )

    assert bullish.recommendation == "buy"
    assert bullish.score is not None
    assert bullish.score >= 70.0

    bearish = engine.decide(
        valuation_report=SimpleNamespace(valuation_signal="overvalued"),
        forensic_report=SimpleNamespace(fraud_probability=80.0, piotroski=SimpleNamespace(score=2)),
        scenario_report=SimpleNamespace(scenarios=[SimpleNamespace(name="base", upside_pct=-20.0)]),
        technical_report=SimpleNamespace(trend="downtrend"),
    )

    assert bearish.recommendation == "avoid"
    assert bearish.score is not None
    assert bearish.score < 50.0
