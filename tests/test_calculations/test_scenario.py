from datetime import date

import pytest

from src.calculations.scenario import ScenarioAnalyzer, ScenarioConfig
from src.models import CompanyProfile, FinancialLine, NormalizedCompany, PricePoint

PNL_ITEMS = {
    "Revenue",
    "EBITDA",
    "Net Profit",
}

CASH_ITEMS = set()


def _company_multi_year(ticker, sector, years_values, price):
    financials = []

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


def _sample_years_values():
    return {
        2020: {
            "Revenue": 1000.0,
            "EBITDA": 200.0,
            "Net Profit": 100.0,
            "Shares Outstanding": 100.0,
            "Cash and Equivalents": 50.0,
            "Total Debt": 100.0,
        },
        2021: {
            "Revenue": 1100.0,
            "EBITDA": 220.0,
            "Net Profit": 110.0,
            "Shares Outstanding": 100.0,
            "Cash and Equivalents": 50.0,
            "Total Debt": 100.0,
        },
        2022: {
            "Revenue": 1210.0,
            "EBITDA": 242.0,
            "Net Profit": 121.0,
            "Shares Outstanding": 100.0,
            "Cash and Equivalents": 50.0,
            "Total Debt": 100.0,
        },
        2023: {
            "Revenue": 1331.0,
            "EBITDA": 266.2,
            "Net Profit": 133.1,
            "Shares Outstanding": 100.0,
            "Cash and Equivalents": 50.0,
            "Total Debt": 100.0,
        },
    }


def _no_macro_config():
    return ScenarioConfig(
        projection_years=3,
        macro_sensitivity=0.0,
        bull_adjust=0.03,
        bear_adjust=0.03,
    )


def test_historical_cagr():
    analyzer = ScenarioAnalyzer()

    growth = analyzer._estimate_growth([1000.0, 1100.0, 1210.0, 1331.0])

    assert growth == pytest.approx(0.10)


def test_macro_overlay():
    config = ScenarioConfig(
        macro_gdp_growth=0.06,
        macro_interest_rate=0.07,
        macro_inflation=0.05,
        macro_sensitivity=0.25,
    )

    analyzer = ScenarioAnalyzer(config)
    macro = analyzer._macro_overlay()

    assert macro.adjustment == pytest.approx(-0.015)


def test_base_forecast_and_target():
    analyzer = ScenarioAnalyzer(_no_macro_config())
    company = _company_multi_year("SCEN", "scenario", _sample_years_values(), price=20.0)

    report = analyzer.analyze(company)
    base = next(scenario for scenario in report.scenarios if scenario.name == "base")

    assert report.base_growth == pytest.approx(0.10)
    assert base.revenue[-1].value == pytest.approx(1771.561)
    assert base.ebitda[-1].value == pytest.approx(354.3122)
    assert base.eps[-1].value == pytest.approx(1.771561)
    assert base.target_price == pytest.approx(26.70275, rel=1e-4)


def test_scenarios_are_distinct():
    analyzer = ScenarioAnalyzer(_no_macro_config())
    company = _company_multi_year("SCEN", "scenario", _sample_years_values(), price=20.0)

    report = analyzer.analyze(company)

    bull = next(scenario for scenario in report.scenarios if scenario.name == "bull")
    base = next(scenario for scenario in report.scenarios if scenario.name == "base")
    bear = next(scenario for scenario in report.scenarios if scenario.name == "bear")

    assert bull.growth_rate > base.growth_rate > bear.growth_rate
    assert bull.target_price > base.target_price > bear.target_price


def test_confidence_range_and_status():
    analyzer = ScenarioAnalyzer(_no_macro_config())
    company = _company_multi_year("SCEN", "scenario", _sample_years_values(), price=20.0)

    report = analyzer.analyze(company)

    assert report.status == "ok"
    assert report.target_price_lower is not None
    assert report.target_price_upper is not None
    assert report.target_price_lower < report.target_price_upper
