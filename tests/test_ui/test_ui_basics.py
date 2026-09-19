from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from src.calculations.decision import DecisionEngine
from src.models import CompanyProfile, FinancialLine, NormalizedCompany
from src.ui.ingestion_widget import IngestionWidget
from src.ui.pages.summary_page import build_company_narrative


def test_decision_breakdown_present():
    decision = DecisionEngine().decide(
        valuation_report=SimpleNamespace(valuation_signal="undervalued"),
        forensic_report=SimpleNamespace(fraud_probability=10.0, piotroski=SimpleNamespace(score=8)),
        scenario_report=SimpleNamespace(scenarios=[SimpleNamespace(name="base", upside_pct=35.0)]),
        technical_report=SimpleNamespace(trend="uptrend"),
    )

    breakdown = decision.inputs.get("component_breakdown")

    assert breakdown
    assert len(breakdown) >= 4
    assert all({"component", "reading", "points"} <= set(item) for item in breakdown)


def test_company_narrative_contains_key_facts():
    company = NormalizedCompany(
        company=CompanyProfile(ticker="TEST", name="Test Company", sector="technology"),
        financials=[
            FinancialLine(fiscal_year=2023, statement_type="pnl", line_item="Revenue", value=1000.0),
            FinancialLine(fiscal_year=2023, statement_type="pnl", line_item="Net Profit", value=100.0),
        ],
    )

    bundle = SimpleNamespace(forensic=None, valuation=None, decision=None)
    narrative = build_company_narrative(company, bundle)

    assert "TEST" in narrative
    assert "technology" in narrative
    assert "10.0%" in narrative


def test_ingestion_widget_uses_accessible_search_controls():
    app = QApplication.instance() or QApplication([])
    widget = IngestionWidget()

    assert widget.ticker_input.isClearButtonEnabled() is True
    assert widget.ticker_input.minimumHeight() >= 44
    assert widget.fetch_btn.minimumHeight() >= 44
