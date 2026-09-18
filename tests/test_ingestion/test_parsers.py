import json

import fitz
import pandas as pd

from src.ingestion.excel_parser import ExcelParser
from src.ingestion.json_parser import JSONParser
from src.ingestion.normalizer import DataNormalizer
from src.ingestion.pdf_parser import PDFParser
from src.ingestion.screener import ScreenerScraper

CSV_CONTENT = """statement_type,fiscal_year,line_item,value
balance_sheet,2023,Equity,100
pnl,2023,Revenue,200
cashflow,2023,Operating Cash Flow,50
"""


def test_csv_parser_and_normalizer(tmp_path):
    path = tmp_path / "sample.csv"
    path.write_text(CSV_CONTENT, encoding="utf-8")

    extract = ExcelParser().load(path)
    normalized = DataNormalizer().normalize(extract)

    assert normalized.company.ticker == "SAMPLE"
    assert len(normalized.financials) == 3
    assert normalized.financials[0].statement_type == "balance_sheet"


def test_xlsx_parser_and_normalizer(tmp_path):
    path = tmp_path / "sample.xlsx"

    frame = pd.DataFrame(
        [
            {
                "statement_type": "balance_sheet",
                "fiscal_year": 2023,
                "line_item": "Equity",
                "value": 100,
            },
            {
                "statement_type": "pnl",
                "fiscal_year": 2023,
                "line_item": "Revenue",
                "value": 200,
            },
        ]
    )

    frame.to_excel(path, index=False, sheet_name="financials")

    extract = ExcelParser().load(path)
    normalized = DataNormalizer().normalize(extract)

    assert normalized.company.ticker == "SAMPLE"
    assert len(normalized.financials) == 2


def test_json_parser_and_normalizer(tmp_path):
    payload = {
        "company": {
            "ticker": "TEST",
            "name": "Test Co",
            "sector": "Technology",
        },
        "financials": [
            {
                "fiscal_year": 2023,
                "statement_type": "pnl",
                "line_item": "Revenue",
                "value": 100,
            }
        ],
        "prices": [
            {
                "date": "2023-01-02",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "volume": 1000,
            }
        ],
        "shareholding": [
            {
                "quarter": "2023Q1",
                "promoter_pct": 51.0,
                "fii_pct": 10.0,
                "dii_pct": 9.0,
                "public_pct": 30.0,
            }
        ],
    }

    path = tmp_path / "sample.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    extract = JSONParser().load(path)
    normalized = DataNormalizer().normalize(extract)

    assert normalized.company.ticker == "TEST"
    assert len(normalized.financials) == 1
    assert len(normalized.prices) == 1
    assert len(normalized.shareholding) == 1


def test_pdf_parser_and_normalizer(tmp_path):
    path = tmp_path / "sample.pdf"

    text = (
        "statement_type,fiscal_year,line_item,value\n"
        "balance_sheet,2023,Equity,100\n"
        "pnl,2023,Revenue,200\n"
    )

    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(72, 72, 540, 720), text, fontsize=10)
    doc.save(str(path))
    doc.close()

    extract = PDFParser().load(path)
    normalized = DataNormalizer().normalize(extract)

    assert normalized.company.ticker == "SAMPLE"
    assert len(normalized.financials) == 2


def test_screener_html_parser_and_normalizer():
    html = """
    <html>
      <body>
        <h1>Test Co</h1>
        <table>
          <tr><th>Year</th><th>Revenue</th></tr>
          <tr><td>2023</td><td>100</td></tr>
        </table>
      </body>
    </html>
    """

    extract = ScreenerScraper().parse_html(html, "TEST")
    normalized = DataNormalizer().normalize(extract)

    assert extract.metadata["ticker"] == "TEST"
    assert extract.metadata["name"] == "Test Co"
    assert normalized.company.ticker == "TEST"
    assert normalized.financials[0].line_item == "Revenue"
    assert normalized.financials[0].value == 100.0
