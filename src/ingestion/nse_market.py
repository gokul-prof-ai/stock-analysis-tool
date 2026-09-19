from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import http.cookiejar
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..models import PricePoint
from .base import IngestionError


NSE_HISTORICAL_URL = "https://www.nseindia.com/api/historical/cm/equity"


class NSEMarketData:
    """Loads public daily NSE candles for the technical-analysis workspace."""

    def __init__(self, timeout: int = 20, user_agent: str | None = None) -> None:
        self.timeout = timeout
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )

    def fetch_daily(self, symbol: str, days: int = 400) -> list[PricePoint]:
        symbol = str(symbol or "").strip().upper()
        if not symbol:
            return []

        end = date.today()
        start = end - timedelta(days=max(days, 30))
        params = urllib.parse.urlencode(
            {
                "symbol": symbol,
                "series": '["EQ"]',
                "from": start.strftime("%d-%m-%Y"),
                "to": end.strftime("%d-%m-%Y"),
            }
        )
        request = urllib.request.Request(
            f"{NSE_HISTORICAL_URL}?{params}",
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.nseindia.com/",
                "Connection": "keep-alive",
            },
        )

        try:
            cookie_jar = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(cookie_jar)
            )
            opener.open(
                urllib.request.Request(
                    "https://www.nseindia.com/",
                    headers={
                        "User-Agent": self.user_agent,
                        "Accept": "text/html,application/xhtml+xml,*/*",
                    },
                ),
                timeout=self.timeout,
            ).close()
            with opener.open(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
            return self._fetch_public_fallback(symbol, start, end)

        rows = payload.get("data", []) if isinstance(payload, dict) else []
        prices: list[PricePoint] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            parsed = self._parse_row(row)
            if parsed is not None:
                prices.append(parsed)

        return sorted(prices, key=lambda item: item.date)

    def _fetch_public_fallback(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> list[PricePoint]:
        """Use the public quote feed when NSE blocks automated historical requests."""
        period_start = int(datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp())
        period_end = int(datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp())
        url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{urllib.parse.quote(symbol)}.NS?period1={period_start}&period2={period_end}"
            "&interval=1d&events=history"
        )
        request = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent, "Accept": "application/json"},
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
            raise IngestionError(f"Public historical data unavailable for {symbol}: {exc}") from exc

        result = ((payload.get("chart") or {}).get("result") or [None])[0]
        if not isinstance(result, dict):
            return []

        timestamps = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [None])[0] or {}
        prices: list[PricePoint] = []
        for index, timestamp in enumerate(timestamps):
            try:
                values = [
                    quote["open"][index],
                    quote["high"][index],
                    quote["low"][index],
                    quote["close"][index],
                ]
                if any(value is None for value in values):
                    continue
                prices.append(
                    PricePoint(
                        date=datetime.fromtimestamp(timestamp, timezone.utc).date(),
                        open=float(values[0]),
                        high=float(values[1]),
                        low=float(values[2]),
                        close=float(values[3]),
                        volume=max(int(quote.get("volume", [0])[index] or 0), 0),
                    )
                )
            except (IndexError, TypeError, ValueError, OverflowError):
                continue

        return sorted(prices, key=lambda item: item.date)

    @staticmethod
    def _parse_row(row: dict[str, Any]) -> PricePoint | None:
        parsed_date = NSEMarketData._parse_date(row.get("CH_TIMESTAMP") or row.get("mTIMESTAMP"))
        values = [
            NSEMarketData._number(row.get("CH_OPENING_PRICE")),
            NSEMarketData._number(row.get("CH_TRADE_HIGH_PRICE")),
            NSEMarketData._number(row.get("CH_TRADE_LOW_PRICE")),
            NSEMarketData._number(row.get("CH_CLOSING_PRICE")),
        ]
        volume = NSEMarketData._number(row.get("CH_TOT_TRADED_QTY")) or 0

        if parsed_date is None or any(value is None for value in values):
            return None

        return PricePoint(
            date=parsed_date,
            open=values[0],
            high=values[1],
            low=values[2],
            close=values[3],
            volume=max(int(volume), 0),
        )

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if not value:
            return None
        text = str(value).strip()
        for pattern in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return float(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            return None
