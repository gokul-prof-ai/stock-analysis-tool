from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from .base import DataSource, IngestionError, ParsedTable, RawExtract

HEADING_TAGS = ["h1", "h2", "h3", "h4"]

COMPANY_URL = "https://www.screener.in/company/{slug}/"
SEARCH_PAGE_URL = "https://www.screener.in/search/?q={query}"
DUCKDUCKGO_URL = "https://html.duckduckgo.com/html/?q={query}"

HTML_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

STOP_TOKENS = {
    "LTD",
    "LIMITED",
    "INC",
    "CORP",
    "CORPORATION",
    "CO",
    "COMPANY",
    "INDIA",
    "OF",
    "THE",
    "AND",
    "PLC",
    "LLP",
    "PVT",
    "PRIVATE",
}

COMPANY_SUFFIXES = ("LIMITED", "LTD", "CORPORATION", "CORP", "INC", "CO", "PLC", "LLP")

EXCLUDED_SLUGS = {
    "CORPORATE",
    "API",
    "SCREENS",
    "CHART",
    "LOGIN",
    "REGISTER",
    "SEARCH",
    "ABOUT",
    "CONTACT",
    "TERMS",
    "PRIVACY",
    "COMPANIES",
}


def parse_search_html(html: str, limit: int = 8) -> list[dict[str, str]]:
    """Parse company links out of a Screener.in search results page."""
    soup = BeautifulSoup(html or "", "html.parser")
    results: list[dict[str, str]] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        match = re.search(r"/company/([A-Za-z0-9._-]+)/?", str(anchor["href"]))

        if not match:
            continue

        slug = match.group(1)
        key = slug.upper()

        if key in EXCLUDED_SLUGS or key in seen:
            continue

        seen.add(key)
        results.append({"name": anchor.get_text(strip=True) or slug, "slug": slug})

        if len(results) >= limit:
            break

    return results


def parse_duckduckgo_html(html: str, limit: int = 8) -> list[dict[str, str]]:
    """Parse Screener company slugs out of a DuckDuckGo site: search page."""
    decoded = urllib.parse.unquote(html or "")
    results: list[dict[str, str]] = []
    seen: set[str] = set()

    for match in re.finditer(r"screener\.in/company/([A-Za-z0-9._-]+)/?", decoded):
        slug = match.group(1)
        key = slug.upper()

        if key in EXCLUDED_SLUGS or key in seen:
            continue

        seen.add(key)
        results.append({"name": slug, "slug": slug})

        if len(results) >= limit:
            break

    return results


class ScreenerScraper(DataSource):
    """Screener.in scraper using pure web-scraping company resolution."""

    source_name = "screener"

    def __init__(self, timeout: int = 25, user_agent: str | None = None) -> None:
        self.timeout = timeout
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )

    def load(self, target: str | Path) -> RawExtract:
        ticker = str(target).strip()

        if not ticker:
            raise IngestionError("Ticker cannot be empty")

        html, slug = self._fetch_company_page(ticker)

        return self.parse_html(html, slug)

    def search_companies(self, query: str, limit: int = 8) -> list[dict[str, str]]:
        """Search for companies by scraping Screener search, then DuckDuckGo."""
        query = query.strip()

        if not query:
            return []

        try:
            html = self._fetch_urllib(
                SEARCH_PAGE_URL.format(query=urllib.parse.quote_plus(query))
            )
            results = parse_search_html(html, limit)
        except IngestionError:
            results = []

        if results:
            return results

        try:
            ddg_url = DUCKDUCKGO_URL.format(
                query=urllib.parse.quote_plus(f"site:screener.in/company {query}")
            )
            html = self._fetch_urllib(ddg_url)
            return parse_duckduckgo_html(html, limit)
        except IngestionError:
            return []

    def _fetch_company_page(self, ticker: str) -> tuple[str, str]:
        tried: set[str] = set()

        for slug in self._candidate_slugs(ticker):
            if slug in tried:
                continue

            tried.add(slug)
            html = self._try_company_url(slug)

            if html is not None:
                return html, slug

        for result in self.search_companies(ticker):
            slug = result["slug"].upper()

            if slug in tried:
                continue

            tried.add(slug)
            html = self._try_company_url(slug)

            if html is not None:
                return html, slug

        raise IngestionError(
            f"Could not fetch a Screener.in company page for '{ticker}'. "
            "Check your internet connection, or enter the exact Screener slug (e.g., AXISBANK)."
        )

    def _try_company_url(self, slug: str) -> str | None:
        url = COMPANY_URL.format(slug=slug)

        try:
            html = self._fetch_any(url)
        except IngestionError:
            return None

        if self._has_company_tables(html):
            return html

        return None

    def _candidate_slugs(self, ticker: str) -> list[str]:
        raw = ticker.strip()
        upper = raw.upper()
        candidates: list[str] = []

        def add(value: str) -> None:
            cleaned = re.sub(r"[^A-Z0-9._-]", "", value or "").strip(".")

            if len(cleaned) >= 3 and cleaned not in candidates and cleaned not in EXCLUDED_SLUGS:
                candidates.append(cleaned)

        if re.fullmatch(r"[A-Za-z0-9._-]+", raw):
            add(upper)

            for suffix in COMPANY_SUFFIXES:
                if upper.endswith(suffix) and len(upper) > len(suffix) + 2:
                    add(upper[: -len(suffix)])

        tokens = [token for token in re.split(r"[^A-Za-z0-9]+", upper) if token]
        kept = [token for token in tokens if token not in STOP_TOKENS]

        if kept:
            add("".join(kept))

        if tokens:
            add("".join(tokens))

        return candidates

    @staticmethod
    def _has_company_tables(html: str) -> bool:
        return html.lower().count("<table") >= 2

    def _fetch_any(self, url: str) -> str:
        try:
            return self._fetch_urllib(url)
        except IngestionError as exc:
            try:
                return self._fetch_selenium(url)
            except IngestionError:
                raise exc

    def _fetch_urllib(self, url: str) -> str:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": HTML_ACCEPT,
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.screener.in/",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except urllib.error.HTTPError as exc:
            raise IngestionError(f"Screener.in returned HTTP {exc.code} for {url}") from exc
        except urllib.error.URLError as exc:
            raise IngestionError(f"Network error while contacting {url}: {exc.reason}") from exc
        except Exception as exc:
            raise IngestionError(f"Failed to fetch {url}: {exc}") from exc

    def _fetch_selenium(self, url: str) -> str:
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
        except Exception as exc:
            raise IngestionError(f"Selenium unavailable for {url}: {exc}") from exc

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(f"user-agent={self.user_agent}")

        driver = None

        try:
            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(self.timeout)
            driver.get(url)
            WebDriverWait(driver, 15).until(lambda d: d.find_elements(By.TAG_NAME, "table"))
            return str(driver.page_source)
        except Exception as exc:
            raise IngestionError(f"Headless browser fetch failed for {url}: {exc}") from exc
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass

    def parse_html(self, html: str, ticker: str) -> RawExtract:
        """Parse Screener HTML into raw tables named by their section headings."""
        soup = BeautifulSoup(html, "html.parser")
        metadata = self._parse_metadata(soup, ticker)
        tables: list[ParsedTable] = []

        for idx, table in enumerate(soup.find_all("table")):
            rows: list[list[str]] = []

            for tr in table.find_all("tr"):
                cells = [cell.get_text(strip=True) for cell in tr.find_all(["th", "td"])]

                if cells:
                    rows.append(cells)

            if not rows:
                continue

            header = rows[0]
            body = rows[1:] if len(rows) > 1 else rows
            max_cols = max([len(header)] + [len(row) for row in body] + [1])
            columns = header + [f"col_{i}" for i in range(len(header), max_cols)]
            normalized_rows = [row + [""] * (len(columns) - len(row)) for row in body]

            heading = table.find_previous(HEADING_TAGS)
            heading_text = heading.get_text(strip=True) if heading is not None else ""
            name_token = re.sub(r"[^a-z0-9]+", "_", heading_text.lower()).strip("_")

            tables.append(
                ParsedTable(
                    name=name_token or f"table_{idx}",
                    columns=[str(column) for column in columns],
                    rows=normalized_rows,
                )
            )

        return RawExtract(
            source=self.source_name,
            source_file=None,
            metadata=metadata,
            tables=tables,
        )

    def _parse_metadata(self, soup: BeautifulSoup, ticker: str) -> dict[str, Any]:
        name_tag = soup.find("h1")
        company_name = name_tag.get_text(strip=True) if name_tag else ticker

        return {
            "ticker": ticker,
            "name": company_name,
        }
