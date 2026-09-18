from src.ingestion.normalizer import DataNormalizer
from src.ingestion.screener import ScreenerScraper

REALISTIC_HTML = """
<html>
  <body>
    <h1>Axis Bank Ltd.</h1>
    <h2>Profit & Loss</h2>
    <table>
      <tr><td></td><th>Mar 2023</th><th>Mar 2024</th><th>TTM</th></tr>
      <tr><td>Sales</td><td>1,000</td><td>1,100</td><td>1,150</td></tr>
      <tr><td>Operating Profit</td><td>300</td><td>330</td><td>345</td></tr>
      <tr><td>Net Profit</td><td>100</td><td>120</td><td>130</td></tr>
    </table>
    <h2>Balance Sheet</h2>
    <table>
      <tr><td></td><th>Mar 2023</th><th>Mar 2024</th></tr>
      <tr><td>Equity Capital</td><td>50</td><td>50</td></tr>
      <tr><td>Reserves</td><td>450</td><td>520</td></tr>
      <tr><td>Total Assets</td><td>1,000</td><td>1,200</td></tr>
    </table>
    <h2>Cash Flows</h2>
    <table>
      <tr><td></td><th>Mar 2023</th><th>Mar 2024</th></tr>
      <tr><td>Cash from Operating Activity</td><td>150</td><td>180</td></tr>
    </table>
    <h2>Shareholding</h2>
    <table>
      <tr><td></td><th>Dec 2024</th><th>Mar 2025</th></tr>
      <tr><td>Promoters</td><td>50.1</td><td>50.2</td></tr>
      <tr><td>FII</td><td>20.0</td><td>20.5</td></tr>
      <tr><td>DII</td><td>15.0</td><td>15.1</td></tr>
      <tr><td>Public</td><td>14.9</td><td>14.2</td></tr>
      <tr><td>No. of Shareholders</td><td>1200000</td><td>1250000</td></tr>
    </table>
  </body>
</html>
"""


def test_parse_realistic_screener_html():
    extract = ScreenerScraper().parse_html(REALISTIC_HTML, "AXISBANK")
    normalized = DataNormalizer().normalize(extract)

    assert normalized.company.ticker == "AXISBANK"
    assert normalized.company.name == "Axis Bank Ltd."

    years = {line.fiscal_year for line in normalized.financials}
    assert years == {2023, 2024}

    sales_2024 = next(
        line
        for line in normalized.financials
        if line.line_item == "Sales" and line.fiscal_year == 2024
    )
    assert sales_2024.statement_type == "pnl"
    assert sales_2024.value == 1100.0

    equity_2024 = next(
        line
        for line in normalized.financials
        if line.line_item == "Equity Capital" and line.fiscal_year == 2024
    )
    assert equity_2024.statement_type == "balance_sheet"
    assert equity_2024.value == 50.0

    operating_cash = next(
        line
        for line in normalized.financials
        if line.line_item == "Cash from Operating Activity" and line.fiscal_year == 2024
    )
    assert operating_cash.statement_type == "cashflow"
    assert operating_cash.value == 180.0

    assert len(normalized.shareholding) == 2

    latest_shareholding = normalized.shareholding[-1]
    assert latest_shareholding.quarter == "Mar 2025"
    assert latest_shareholding.promoter_pct == 50.2
    assert latest_shareholding.fii_pct == 20.5
    assert latest_shareholding.public_pct == 14.2
