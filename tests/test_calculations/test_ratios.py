import pytest

from src.calculations.ratios import RatioCalculator
from src.models import CompanyProfile, FinancialLine, NormalizedCompany


def test_all_26_ratios_hand_calculated(sample_company):
    result = RatioCalculator().calculate_all(sample_company)

    assert result.fiscal_year == 2023
    assert len(result.ratios) == 26

    values = {ratio.name: ratio.value for ratio in result.ratios}

    assert values["current_ratio"] == pytest.approx(1.2)
    assert values["quick_ratio"] == pytest.approx(0.6)
    assert values["cash_ratio"] == pytest.approx(0.2)
    assert values["operating_cash_flow_ratio"] == pytest.approx(1.8)
    assert values["working_capital_ratio"] == pytest.approx(0.04)
    assert values["defensive_interval_ratio"] == pytest.approx(29.2)

    assert values["debt_to_equity"] == pytest.approx(1.5)
    assert values["debt_to_assets"] == pytest.approx(0.6)
    assert values["interest_coverage"] == pytest.approx(5.0)
    assert values["equity_multiplier"] == pytest.approx(2.5)
    assert values["long_term_debt_to_equity"] == pytest.approx(0.6)

    assert values["gross_margin"] == pytest.approx(0.4)
    assert values["operating_margin"] == pytest.approx(0.25)
    assert values["ebitda_margin"] == pytest.approx(0.3)
    assert values["net_profit_margin"] == pytest.approx(0.15)
    assert values["roa"] == pytest.approx(0.3)
    assert values["roe"] == pytest.approx(0.75)
    assert values["roce"] == pytest.approx(0.625)

    assert values["asset_turnover"] == pytest.approx(2.0)
    assert values["fixed_asset_turnover"] == pytest.approx(4.0)
    assert values["inventory_turnover"] == pytest.approx(15.0)
    assert values["receivables_turnover"] == pytest.approx(33.333333)
    assert values["payables_turnover"] == pytest.approx(12.0)

    assert values["eps"] == pytest.approx(1.5)
    assert values["pe_ratio"] == pytest.approx(200.0)
    assert values["pb_ratio"] == pytest.approx(150.0)


def test_missing_inputs_return_none():
    company = NormalizedCompany(
        company=CompanyProfile(ticker="MIN", name="Minimal"),
        financials=[
            FinancialLine(
                fiscal_year=2023,
                statement_type="pnl",
                line_item="Revenue",
                value=100.0,
            )
        ],
    )

    result = RatioCalculator().calculate_all(company)
    values = {ratio.name: ratio.value for ratio in result.ratios}

    assert len(result.ratios) == 26
    assert values["current_ratio"] is None
    assert values["gross_margin"] is None
    assert values["pe_ratio"] is None


def test_negative_equity_is_not_meaningful():
    company = NormalizedCompany(
        company=CompanyProfile(ticker="NEG", name="Negative Equity"),
        financials=[
            FinancialLine(fiscal_year=2023, statement_type="balance_sheet", line_item="Total Equity", value=-10.0),
            FinancialLine(fiscal_year=2023, statement_type="balance_sheet", line_item="Total Liabilities", value=110.0),
            FinancialLine(fiscal_year=2023, statement_type="pnl", line_item="Net Profit", value=5.0),
            FinancialLine(fiscal_year=2023, statement_type="pnl", line_item="Revenue", value=100.0),
        ],
    )

    result = RatioCalculator().calculate_all(company)
    ratios = {ratio.name: ratio for ratio in result.ratios}

    assert ratios["debt_to_equity"].value is None
    assert ratios["debt_to_equity"].status == "not_meaningful"
    assert ratios["roe"].value is None
    assert ratios["roe"].status == "not_meaningful"


def test_multi_year_returns_last_five_years():
    financials = [
        FinancialLine(
            fiscal_year=year,
            statement_type="pnl",
            line_item="Revenue",
            value=100.0,
        )
        for year in range(2018, 2024)
    ]

    company = NormalizedCompany(
        company=CompanyProfile(ticker="TREND", name="Trend Company"),
        financials=financials,
    )

    results = RatioCalculator().calculate_multi_year(company, years=5)

    assert [result.fiscal_year for result in results] == [2019, 2020, 2021, 2022, 2023]
