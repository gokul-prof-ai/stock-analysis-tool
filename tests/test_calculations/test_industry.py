from src.calculations.industry import IndustryAnalyzer, calculate_percentile
from src.models import CompanyProfile, FinancialLine, NormalizedCompany

PNL_ITEMS = {
    "Revenue",
    "Cost of Goods Sold",
    "Gross Profit",
    "Operating Expenses",
    "Operating Profit",
    "EBITDA",
    "EBIT",
    "Interest Expense",
    "Net Profit",
    "Depreciation Amortization",
}

CASH_ITEMS = {"Operating Cash Flow"}


def _company(ticker, sector, values, industry=None, year=2023):
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
                fiscal_year=year,
                statement_type=statement_type,
                line_item=line_item,
                value=float(value),
            )
        )

    return NormalizedCompany(
        company=CompanyProfile(
            ticker=ticker,
            name=ticker,
            sector=sector,
            industry=industry,
        ),
        financials=financials,
    )


def test_peer_selection_filters_sector():
    analyzer = IndustryAnalyzer()

    target = _company(
        "TARG",
        "logistics",
        {
            "Current Assets": 120,
            "Current Liabilities": 100,
            "Total Assets": 1000,
            "Revenue": 1000,
        },
        industry="transportation",
    )

    same_sector = _company(
        "PEER1",
        "logistics",
        {
            "Total Assets": 900,
            "Revenue": 900,
        },
        industry="transportation",
    )

    other_sector = _company(
        "PEER2",
        "manufacturing",
        {
            "Total Assets": 1000,
            "Revenue": 1000,
        },
    )

    peers = analyzer.select_peers(target, [same_sector, other_sector])

    assert [peer.ticker for peer in peers] == ["PEER1"]


def test_percentile_calculation():
    assert calculate_percentile(1.2, [1.0, 1.2, 1.5]) == 50.0
    assert calculate_percentile(None, [1.0]) is None
    assert calculate_percentile(2.0, []) is None


def test_industry_report_rankings_and_porter():
    analyzer = IndustryAnalyzer()

    target = _company(
        "TARG",
        "logistics",
        {
            "Current Assets": 120,
            "Current Liabilities": 100,
            "Total Assets": 1000,
            "Total Equity": 500,
            "Total Liabilities": 500,
            "Revenue": 1000,
            "Net Profit": 100,
            "Fixed Assets": 300,
            "Receivables": 100,
            "Gross Profit": 400,
            "Operating Profit": 200,
            "EBIT": 200,
            "Cost of Goods Sold": 600,
            "Payables": 50,
            "Operating Cash Flow": 120,
        },
        industry="transportation",
    )

    peer_one = _company(
        "PEER1",
        "logistics",
        {
            "Current Assets": 100,
            "Current Liabilities": 100,
            "Total Assets": 900,
            "Total Equity": 400,
            "Total Liabilities": 500,
            "Revenue": 900,
            "Net Profit": 90,
            "Fixed Assets": 250,
            "Receivables": 90,
            "Gross Profit": 360,
            "Operating Profit": 180,
            "EBIT": 180,
            "Cost of Goods Sold": 540,
            "Payables": 45,
            "Operating Cash Flow": 100,
        },
        industry="transportation",
    )

    peer_two = _company(
        "PEER2",
        "logistics",
        {
            "Current Assets": 150,
            "Current Liabilities": 100,
            "Total Assets": 1200,
            "Total Equity": 700,
            "Total Liabilities": 500,
            "Revenue": 1200,
            "Net Profit": 150,
            "Fixed Assets": 400,
            "Receivables": 120,
            "Gross Profit": 480,
            "Operating Profit": 240,
            "EBIT": 240,
            "Cost of Goods Sold": 720,
            "Payables": 60,
            "Operating Cash Flow": 160,
        },
        industry="transportation",
    )

    report = analyzer.analyze(target, [peer_one, peer_two])

    assert len(report.peers) == 2
    assert report.status == "ok"

    current_ratio_ranking = next(
        ranking for ranking in report.rankings if ranking.ratio_name == "current_ratio"
    )

    assert current_ratio_ranking.percentile == 50.0
    assert current_ratio_ranking.peer_count == 3

    assert report.porter.overall_score is not None
    assert 1.0 <= report.porter.overall_score <= 5.0
    assert report.position.composite_score is not None


def test_no_peers_partial():
    analyzer = IndustryAnalyzer()

    target = _company(
        "TARG",
        "logistics",
        {
            "Current Assets": 120,
            "Current Liabilities": 100,
            "Total Assets": 1000,
            "Revenue": 1000,
        },
    )

    report = analyzer.analyze(target, [])

    assert report.peers == []
    assert report.status == "partial"
