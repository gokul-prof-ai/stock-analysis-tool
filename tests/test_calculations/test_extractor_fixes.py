import pytest

from src.calculations.financial_extractor import FinancialExtractor
from src.calculations.ratios import RatioCalculator
from src.models import CompanyProfile, FinancialLine, NormalizedCompany


def _company(lines):
    return NormalizedCompany(
        company=CompanyProfile(ticker="FIX", name="Fix Company"),
        financials=lines,
    )


def test_equity_fallback_equity_capital_plus_reserves():
    company = _company([
        FinancialLine(fiscal_year=2026, statement_type="balance_sheet", line_item="Equity Capital", value=4.24),
        FinancialLine(fiscal_year=2026, statement_type="balance_sheet", line_item="Reserves", value=1150.0),
        FinancialLine(fiscal_year=2026, statement_type="pnl", line_item="Net Profit", value=100.0),
    ])

    snapshot = FinancialExtractor(company).snapshot(2026)

    assert snapshot.get("total_equity") == pytest.approx(1154.24)


def test_equity_fallback_assets_minus_liabilities():
    company = _company([
        FinancialLine(fiscal_year=2026, statement_type="balance_sheet", line_item="Total Assets", value=3000.0),
        FinancialLine(fiscal_year=2026, statement_type="balance_sheet", line_item="Total Liabilities", value=1800.0),
    ])

    snapshot = FinancialExtractor(company).snapshot(2026)

    assert snapshot.get("total_equity") == pytest.approx(1200.0)


def test_operating_cash_flow_alias():
    company = _company([
        FinancialLine(fiscal_year=2026, statement_type="cashflow", line_item="Cash from Operating Activity", value=250.0),
    ])

    snapshot = FinancialExtractor(company).snapshot(2026)

    assert snapshot.get("operating_cash_flow") == pytest.approx(250.0)


def test_source_ratios_merge_into_ratio_set():
    company = NormalizedCompany(
        company=CompanyProfile(ticker="FIX", name="Fix Company"),
        financials=[
            FinancialLine(fiscal_year=2026, statement_type="pnl", line_item="Revenue", value=1000.0),
        ],
        source_ratios={"current_ratio": {2026: 1.5}, "roe": {2026: 0.18}},
    )

    ratio_set = RatioCalculator().calculate_all(company)

    current_ratio = ratio_set.get("current_ratio")
    roe = ratio_set.get("roe")

    assert current_ratio.value == pytest.approx(1.5)
    assert current_ratio.status == "source_provided"
    assert roe.value == pytest.approx(0.18)
    assert roe.status == "source_provided"
