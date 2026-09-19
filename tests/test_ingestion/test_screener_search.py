from src.ingestion.screener import (
    ScreenerScraper,
    parse_duckduckgo_html,
    parse_search_html,
)


def test_candidate_slugs_name_and_fused():
    scraper = ScreenerScraper()

    assert scraper._candidate_slugs("axis bank ltd.")[0] == "AXISBANK"
    assert "AXISBANK" in scraper._candidate_slugs("axisbankltd")
    assert scraper._candidate_slugs("AXISBANK")[0] == "AXISBANK"


def test_has_company_tables():
    assert ScreenerScraper._has_company_tables("<table></table><table></table>") is True
    assert ScreenerScraper._has_company_tables("<html><p>nope</p></html>") is False


def test_parse_search_html():
    html = (
        '<a href="/company/AXISBANK/">Axis Bank Ltd.</a>'
        '<a href="/company/AXISBANK/">duplicate</a>'
        '<a href="/login/">Login</a>'
    )

    assert parse_search_html(html) == [{"name": "Axis Bank Ltd.", "slug": "AXISBANK"}]


def test_parse_duckduckgo_html():
    html = "uddg=https%3A%2F%2Fwww.screener.in%2Fcompany%2FAXISBANK%2F&rut=abc"

    assert parse_duckduckgo_html(html) == [{"name": "AXISBANK", "slug": "AXISBANK"}]


def test_search_companies_uses_name_to_slug_fallback():
    scraper = ScreenerScraper()

    results = scraper.search_companies("axis bank", limit=5)

    assert results
    assert results[0]["slug"] == "AXISBANK"


def test_apify_payload_extraction_handles_nested_html():
    payload = {
        "url": "https://www.screener.in/company/AXISBANK/",
        "page": {
            "content": "<html><body><table><tr><th>Price</th></tr></table></body></html>"
        },
    }

    html = ScreenerScraper._extract_apify_html(payload)

    assert "<table" in html
    assert "Price" in html
