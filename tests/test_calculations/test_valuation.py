from datetime import date

import pytest

from src.calculations.valuation import ValuationConfig, ValuationEngine, ValuationInputs
from src.models import CompanyProfile, FinancialLine, NormalizedCompany, PricePoint

PNL_ITEMS = {
    "Revenue",
    "Net Profit",
    "EBITDA",
}

CASH_ITEMS = {
    "Operating Cash Flow",
    "Capital Expenditure",
}


def _company(ticker, sector, values, price):
    financials = []

    for line_item, value in values.items():
        if line_item in CASH_ITEMS:
            statement_type = "cashflow"
        elif line_item in PNL_ITEMS:
            statement_type = "pnl"
        else:
            statement_type = "balance_sheet"

        financials.append(
            FinancialLine(
                fiscal_year=2023,
                statement_type=statement_type,
                line_item=line_item,
                value=float(value),
            )
        )

    prices = [
        PricePoint(
            date=date(2023, 12, 31),
            open=float(price),
            high=float(price) + 1.0,
            low=max(float(price) - 1.0, 0.01),
            close=float(price),
            volume=1000,
        )
    ]

    return NormalizedCompany(
        company=CompanyProfile(ticker=ticker, name=ticker, sector=sector),
        financials=financials,
        prices=prices,
    )


def _target_values():
    return {
        "Revenue": 1000,
        "Net Profit": 100,
        "Total Equity": 500,
        "EBITDA": 200,
        "Cash and Equivalents": 50,
        "Short Term Investments": 20,
        "Total Debt": 150,
        "Shares Outstanding": 100,
        "Operating Cash Flow": 150,
        "Capital Expenditure": 50,
    }


def test_multiples():
    engine = ValuationEngine()
    company = _company("VALT", "valuation", _target_values(), price=10.0)
    inputs = engine.inputs_from_company(company)
    multiples = engine.calculate_multiples(inputs)

    assert multiples.market_cap == pytest.approx(1000.0)
    assert multiples.enterprise_value == pytest.approx(1080.0)
    assert multiples.pe == pytest.approx(10.0)
    assert multiples.pb == pytest.approx(2.0)
    assert multiples.ps == pytest.approx(1.0)
    assert multiples.ev_ebitda == pytest.approx(5.4)


def test_dcf_hand_calculation():
    engine = ValuationEngine()

    enterprise_value = engine.dcf_enterprise_value(
        base_fcf=100.0,
        growth_rate=0.05,
        discount_rate=0.10,
        terminal_growth=0.02,
        projection_years=3,
    )

    assert enterprise_value == pytest.approx(1382.4637, rel=1e-4)


def test_sensitivity_matrix():
    config = ValuationConfig(
        projection_years=3,
        base_growth=0.05,
        sensitivity_wacc_values=(0.10,),
        sensitivity_terminal_growth_values=(0.02,),
    )

    engine = ValuationEngine(config)

    inputs = ValuationInputs(
        ticker="TEST",
        fiscal_year=2023,
        shares_outstanding=100.0,
        operating_cash_flow=100.0,
        capex=0.0,
        free_cash_flow=100.0,
        net_debt=0.0,
    )

    sensitivity = engine.calculate_sensitivity(inputs)

    assert sensitivity.matrix[0][0] == pytest.approx(13.8246, rel=1e-4)


def test_comparable_analysis():
    engine = ValuationEngine()

    target = _company("VALT", "valuation", _target_values(), price=10.0)

    peer_one_values = {
        "Revenue": 1200,
        "Net Profit": 120,
        "Total Equity": 600,
        "EBITDA": 240,
        "Cash and Equivalents": 50,
        "Total Debt": 100,
        "Shares Outstanding": 100,
        "Operating Cash Flow": 170,
        "Capital Expenditure": 50,
    }

    peer_two_values = {
        "Revenue": 1500,
        "Net Profit": 150,
        "Total Equity": 750,
        "EBITDA": 300,
        "Cash and Equivalents": 75,
        "Total Debt": 150,
        "Shares Outstanding": 100,
        "Operating Cash Flow": 200,
        "Capital Expenditure": 60,
    }

    peer_one = _company("V1PE", "valuation", peer_one_values, price=12.0)
    peer_two = _company("V2PE", "valuation", peer_two_values, price=15.0)

    target_inputs = engine.inputs_from_company(target)
    peer_inputs = [engine.inputs_from_company(peer_one), engine.inputs_from_company(peer_two)]

    comparable = engine.calculate_comparable(target_inputs, peer_inputs)

    assert comparable.peer_tickers == ["V1PE", "V2PE"]
    assert comparable.median_implied_value == pytest.approx(10.0)


def test_full_valuation_report():
    engine = ValuationEngine()

    target = _company("VALT", "valuation", _target_values(), price=10.0)

    peer_one_values = {
        "Revenue": 1200,
        "Net Profit": 120,
        "Total Equity": 600,
        "EBITDA": 240,
        "Cash and Equivalents": 50,
        "Total Debt": 100,
        "Shares Outstanding": 100,
        "Operating Cash Flow": 170,
        "Capital Expenditure": 50,
    }

    peer_two_values = {
        "Revenue": 1500,
        "Net Profit": 150,
        "Total Equity": 750,
        "EBITDA": 300,
        "Cash and Equivalents": 75,
        "Total Debt": 150,
        "Shares Outstanding": 100,
        "Operating Cash Flow": 200,
        "Capital Expenditure": 60,
    }

    peer_one = _company("V1PE", "valuation", peer_one_values, price=12.0)
    peer_two = _company("V2PE", "valuation", peer_two_values, price=15.0)

    report = engine.analyze(target, [peer_one, peer_two])

    assert report.status == "ok"
    assert report.multiples.pe == pytest.approx(10.0)
    assert report.dcf.base_intrinsic_per_share == pytest.approx(16.40, rel=1e-2)
    assert report.comparable.median_implied_value == pytest.approx(10.0)
    assert report.intrinsic_value == pytest.approx(13.20, rel=1e-2)
    assert report.margin_of_safety > 20.0
    assert report.valuation_signal == "undervalued"
