from __future__ import annotations

import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from ..models import (
    CompanyProfile,
    FinancialLine,
    NormalizedCompany,
    PricePoint,
    ShareholdingPoint,
)
from .base import IngestionError, ParsedTable, RawExtract


class NormalizationError(IngestionError):
    """Raised when raw extract cannot be normalized."""


STATEMENT_ALIASES: dict[str, str] = {
    "balance_sheet": "balance_sheet",
    "balancesheet": "balance_sheet",
    "balance": "balance_sheet",
    "bs": "balance_sheet",
    "pnl": "pnl",
    "profit_loss": "pnl",
    "profit_and_loss": "pnl",
    "income_statement": "pnl",
    "income": "pnl",
    "pl": "pnl",
    "cashflow": "cashflow",
    "cash_flow": "cashflow",
    "cash_flows": "cashflow",
    "cashflow_statement": "cashflow",
    "cf": "cashflow",
}

HEADER_ALIASES: dict[str, str] = {
    "year": "fiscal_year",
    "fy": "fiscal_year",
    "statement": "statement_type",
    "type": "statement_type",
    "item": "line_item",
    "particular": "line_item",
    "particulars": "line_item",
    "amount": "value",
    "trade_date": "date",
    "close_price": "close",
    "open_price": "open",
    "high_price": "high",
    "low_price": "low",
    "vol": "volume",
    "promoter": "promoter_pct",
    "fii": "fii_pct",
    "dii": "dii_pct",
    "public": "public_pct",
}

SKIP_TABLE_FRAGMENTS = (
    "quarterly",
    "ratios",
    "peer",
    "competitor",
    "industry",
    "comparison",
    "graph",
)

BALANCE_SHEET_KEYWORDS = {
    "equity",
    "asset",
    "liabilit",
    "debt",
    "capital",
    "reserve",
    "current_asset",
    "current_liab",
    "fixed_asset",
    "investment",
}

PNL_KEYWORDS = {
    "revenue",
    "sales",
    "income",
    "profit",
    "ebitda",
    "ebit",
    "expense",
    "cost",
    "eps",
    "net_profit",
}

CASHFLOW_KEYWORDS = {
    "operating_cash",
    "investing_cash",
    "financing_cash",
    "capex",
    "free_cash",
    "cash_generated",
}


def _clean_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None

    text = str(value).strip()
    if not text:
        return None

    negative = text.startswith("(") and text.endswith(")")
    text = text.replace("(", "").replace(")", "")
    text = text.replace(",", "").replace(" ", "")

    match = re.search(r"[-+]?\d*\.?\d+", text.replace("%", ""))
    if not match:
        return None

    parsed = float(match.group(0))
    if negative:
        parsed = -parsed

    return parsed if math.isfinite(parsed) else None


def _to_year(value: Any) -> int | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        year = int(value)
    else:
        text = str(value).strip()
        match = re.search(r"(19|20)\d{2}", text)
        if match:
            year = int(match.group(0))
        else:
            try:
                year = int(float(text))
            except Exception:
                return None

    if 1900 <= year <= 2100:
        return year

    if 0 <= year <= 99:
        return 2000 + year if year < 70 else 1900 + year

    return None


def _statement_type(value: Any) -> str | None:
    token = _clean_token(value)
    if not token:
        return None

    if token in STATEMENT_ALIASES:
        return STATEMENT_ALIASES[token]

    for key, normalized in STATEMENT_ALIASES.items():
        if key in token:
            return normalized

    return None


def _infer_statement_from_item(value: Any) -> str | None:
    token = _clean_token(value)
    if not token:
        return None

    if "cash_flow" in token or token.startswith("cf"):
        return "cashflow"

    if any(keyword in token for keyword in BALANCE_SHEET_KEYWORDS):
        return "balance_sheet"

    if any(keyword in token for keyword in PNL_KEYWORDS):
        return "pnl"

    if any(keyword in token for keyword in CASHFLOW_KEYWORDS):
        return "cashflow"

    return None


def _canonical_header_map(headers: list[str]) -> dict[str, int]:
    index: dict[str, int] = {}

    for idx, header in enumerate(headers):
        index.setdefault(header, idx)

    for alias, canonical in HEADER_ALIASES.items():
        if canonical not in index and alias in index:
            index[canonical] = index[alias]

    return index


class DataNormalizer:
    """Converts RawExtract objects into NormalizedCompany models."""

    def normalize(self, extract: RawExtract) -> NormalizedCompany:
        if extract.metadata.get("json") is not None:
            return self._normalize_json(extract)
        return self._normalize_tabular(extract)

    def _normalize_json(self, extract: RawExtract) -> NormalizedCompany:
        payload = extract.metadata.get("json")

        if isinstance(payload, list):
            payload = {"financials": payload}

        if not isinstance(payload, dict):
            raise NormalizationError("JSON payload must be an object or array")

        company_raw = payload.get("company", {})
        if not isinstance(company_raw, dict):
            raise NormalizationError("JSON company section must be an object")

        company = self._profile_from_dict(company_raw, extract)

        financials = self._validate_rows(payload.get("financials", []), FinancialLine)
        prices = self._validate_rows(payload.get("prices", []), PricePoint)
        shareholding = self._validate_rows(
            payload.get("shareholding", []),
            ShareholdingPoint,
        )

        return NormalizedCompany(
            company=company,
            financials=financials,
            prices=prices,
            shareholding=shareholding,
        )

    def _normalize_tabular(self, extract: RawExtract) -> NormalizedCompany:
        metadata: dict[str, Any] = dict(extract.metadata)
        tables = list(extract.tables)

        for table in tables:
            if self._is_key_value_table(table):
                metadata.update(self._key_value_map(table))

        company = self._profile_from_dict(metadata, extract)

        financials: list[FinancialLine] = []
        prices: list[PricePoint] = []
        shareholding: list[ShareholdingPoint] = []


        for table in tables:
            if self._is_key_value_table(table):
                continue

            name_token = _clean_token(table.name)

            if "shareholding" in name_token or "share_holder" in name_token:
                shareholding.extend(self._shareholding_wide(table))
                continue

            if any(fragment in name_token for fragment in SKIP_TABLE_FRAGMENTS):
                continue

            financials.extend(self._financials_from_table(table, metadata))
            prices.extend(self._prices_from_table(table))
            shareholding.extend(self._shareholding_from_table(table))

        current_price = _to_float(metadata.get("current_price"))
        if not prices and current_price is not None and current_price >= 0:
            today = date.today()
            prices.append(
                PricePoint(
                    date=today,
                    open=current_price,
                    high=current_price,
                    low=current_price,
                    close=current_price,
                )
            )

        source_ratios = self._source_ratios_from_tables(tables)

        return NormalizedCompany(
            company=company,
            financials=financials,
            prices=prices,
            shareholding=shareholding,
            source_ratios=source_ratios,
        )

    def _validate_rows(self, rows: Any, model: type[BaseModel]) -> list[Any]:
        if rows is None:
            return []

        if not isinstance(rows, list):
            raise NormalizationError(f"{model.__name__} payload must be an array")

        normalized: list[Any] = []
        for row in rows:
            try:
                normalized.append(model.model_validate(row))
            except ValidationError as exc:
                raise NormalizationError(f"Invalid {model.__name__} row: {row}") from exc

        return normalized

    def _profile_from_dict(
        self,
        data: dict[str, Any],
        extract: RawExtract,
    ) -> CompanyProfile:
        ticker = str(
            data.get("ticker")
            or data.get("symbol")
            or data.get("company_ticker")
            or ""
        ).strip()

        name = str(
            data.get("name")
            or data.get("company_name")
            or data.get("company")
            or ""
        ).strip()

        if not ticker:
            ticker = self._fallback_ticker(extract)

        if not name:
            name = ticker

        try:
            return CompanyProfile(
                ticker=ticker,
                name=name,
                sector=data.get("sector") or None,
                industry=data.get("industry") or None,
            )
        except ValidationError as exc:
            raise NormalizationError("Company profile validation failed") from exc

    def _fallback_ticker(self, extract: RawExtract) -> str:
        if extract.source_file:
            stem = Path(extract.source_file).stem.strip().upper().replace(" ", "_")
            if stem:
                return stem[:40]

        if extract.metadata.get("ticker"):
            return str(extract.metadata["ticker"]).strip().upper()[:40]

        return "UNKNOWN"

    def _is_key_value_table(self, table: ParsedTable) -> bool:
        if len(table.columns) != 2:
            return False

        headers = [_clean_token(column) for column in table.columns]
        return headers[0] in {
            "key",
            "field",
            "metric",
            "label",
            "item",
            "particular",
        } and headers[1] in {"value", "text"}

    def _key_value_map(self, table: ParsedTable) -> dict[str, Any]:
        result: dict[str, Any] = {}

        for row in table.rows:
            key = self._cell(row, 0)
            value = self._cell(row, 1)
            key_token = _clean_token(key)
            if key_token:
                result[key_token] = value

        return result

    def _financials_from_table(
        self,
        table: ParsedTable,
        metadata: dict[str, Any],
    ) -> list[FinancialLine]:
        headers = [_clean_token(column) for column in table.columns]
        index = _canonical_header_map(headers)

        required = {"statement_type", "fiscal_year", "line_item", "value"}
        if required.issubset(index):
            return self._financials_long(table, index, metadata)

        return self._financials_wide(table, metadata)

    def _financials_long(
        self,
        table: ParsedTable,
        index: dict[str, int],
        metadata: dict[str, Any],
    ) -> list[FinancialLine]:
        rows: list[FinancialLine] = []

        for row in table.rows:
            statement_raw = self._cell(row, index["statement_type"])
            year_raw = self._cell(row, index["fiscal_year"])
            item_raw = self._cell(row, index["line_item"])
            value_raw = self._cell(row, index["value"])

            statement = _statement_type(statement_raw) or _statement_type(
                metadata.get("statement_type")
            )
            fiscal_year = _to_year(year_raw)
            line_item = str(item_raw or "").strip()
            value = _to_float(value_raw)

            if statement is None or fiscal_year is None or not line_item or value is None:
                continue

            try:
                rows.append(
                    FinancialLine(
                        fiscal_year=fiscal_year,
                        statement_type=statement,
                        line_item=line_item,
                        value=value,
                    )
                )
            except ValidationError:
                continue

        return rows

    def _financials_wide(
        self,
        table: ParsedTable,
        metadata: dict[str, Any],
    ) -> list[FinancialLine]:
        if not table.columns:
            return []

        first_header = _clean_token(table.columns[0])
        if first_header in {"year", "fy", "fiscal_year"}:
            return self._financials_transposed(table, metadata)

        base_statement = (
            _statement_type(table.name)
            or _statement_type(metadata.get("statement_type"))
            or _statement_type(metadata.get("statement"))
        )

        year_columns: list[tuple[int, int]] = []
        for idx in range(1, len(table.columns)):
            year = _to_year(table.columns[idx])
            if year is not None:
                year_columns.append((idx, year))

        if not year_columns:
            return []

        rows: list[FinancialLine] = []

        for row in table.rows:
            line_item = str(self._cell(row, 0) or "").strip()
            if not line_item:
                continue

            statement = (
                base_statement
                or _statement_type(line_item)
                or _infer_statement_from_item(line_item)
            )

            if statement is None:
                continue

            for idx, year in year_columns:
                value = _to_float(self._cell(row, idx))
                if value is None:
                    continue

                try:
                    rows.append(
                        FinancialLine(
                            fiscal_year=year,
                            statement_type=statement,
                            line_item=line_item,
                            value=value,
                        )
                    )
                except ValidationError:
                    continue

        return rows

    def _financials_transposed(
        self,
        table: ParsedTable,
        metadata: dict[str, Any],
    ) -> list[FinancialLine]:
        rows: list[FinancialLine] = []
        default_statement = _statement_type(metadata.get("statement_type"))

        for row in table.rows:
            fiscal_year = _to_year(self._cell(row, 0))
            if fiscal_year is None:
                continue

            for idx in range(1, len(table.columns)):
                line_item = str(table.columns[idx]).strip()
                value = _to_float(self._cell(row, idx))

                if not line_item or value is None:
                    continue

                statement = (
                    _statement_type(line_item)
                    or default_statement
                    or _infer_statement_from_item(line_item)
                )

                if statement is None:
                    continue

                try:
                    rows.append(
                        FinancialLine(
                            fiscal_year=fiscal_year,
                            statement_type=statement,
                            line_item=line_item,
                            value=value,
                        )
                    )
                except ValidationError:
                    continue

        return rows

    def _prices_from_table(self, table: ParsedTable) -> list[PricePoint]:
        headers = [_clean_token(column) for column in table.columns]
        index = _canonical_header_map(headers)

        required = {"date", "open", "high", "low", "close"}
        if not required.issubset(index):
            return []

        rows: list[PricePoint] = []

        for row in table.rows:
            parsed_date = self._parse_date(self._cell(row, index["date"]))
            open_price = _to_float(self._cell(row, index["open"]))
            high_price = _to_float(self._cell(row, index["high"]))
            low_price = _to_float(self._cell(row, index["low"]))
            close_price = _to_float(self._cell(row, index["close"]))

            if parsed_date is None or None in {
                open_price,
                high_price,
                low_price,
                close_price,
            }:
                continue

            volume_raw = self._cell(row, index.get("volume", -1)) if "volume" in index else 0
            volume_float = _to_float(volume_raw)
            volume = int(volume_float) if volume_float is not None else 0

            try:
                rows.append(
                    PricePoint(
                        date=parsed_date,
                        open=float(open_price),
                        high=float(high_price),
                        low=float(low_price),
                        close=float(close_price),
                        volume=max(volume, 0),
                    )
                )
            except ValidationError:
                continue

        return rows

    def _shareholding_from_table(self, table: ParsedTable) -> list[ShareholdingPoint]:
        headers = [_clean_token(column) for column in table.columns]
        index = _canonical_header_map(headers)

        if "quarter" not in index:
            return []

        if not any(
            key in index
            for key in ("promoter_pct", "fii_pct", "dii_pct", "public_pct")
        ):
            return []

        rows: list[ShareholdingPoint] = []

        for row in table.rows:
            quarter = str(self._cell(row, index["quarter"]) or "").strip()
            if not quarter:
                continue

            promoter = _to_float(self._cell(row, index["promoter_pct"])) if "promoter_pct" in index else None
            fii = _to_float(self._cell(row, index["fii_pct"])) if "fii_pct" in index else None
            dii = _to_float(self._cell(row, index["dii_pct"])) if "dii_pct" in index else None
            public = _to_float(self._cell(row, index["public_pct"])) if "public_pct" in index else None

            try:
                rows.append(
                    ShareholdingPoint(
                        quarter=quarter,
                        promoter_pct=promoter,
                        fii_pct=fii,
                        dii_pct=dii,
                        public_pct=public,
                    )
                )
            except ValidationError:
                continue

        return rows

    def _shareholding_wide(self, table: ParsedTable) -> list[ShareholdingPoint]:
        rows: list[ShareholdingPoint] = []

        if len(table.columns) < 2:
            return rows

        quarter_columns = [
            (idx, str(column).strip())
            for idx, column in enumerate(table.columns)
            if idx > 0 and str(column).strip()
        ]

        field_by_row: dict[int, str] = {}

        for row_idx, row in enumerate(table.rows):
            key = _clean_token(self._cell(row, 0))

            if key.startswith("promoter"):
                field_by_row[row_idx] = "promoter_pct"
            elif key.startswith("fii") or key.startswith("foreign"):
                field_by_row[row_idx] = "fii_pct"
            elif key.startswith("dii") or key.startswith("domestic"):
                field_by_row[row_idx] = "dii_pct"
            elif key.startswith("public") or key.startswith("retail"):
                field_by_row[row_idx] = "public_pct"

        for col_idx, quarter in quarter_columns:
            values: dict[str, float] = {}

            for row_idx, field in field_by_row.items():
                if row_idx >= len(table.rows):
                    continue

                parsed = _to_float(self._cell(table.rows[row_idx], col_idx))

                if parsed is not None:
                    values[field] = parsed

            if not values:
                continue

            try:
                rows.append(ShareholdingPoint(quarter=quarter, **values))
            except ValidationError:
                continue

        return rows

    def _parse_date(self, value: Any) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value

        text = str(value or "").strip()
        if not text:
            return None

        formats = (
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%d-%b-%Y",
            "%Y/%m/%d",
        )

        for fmt in formats:
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                pass

        try:
            return datetime.fromisoformat(text).date()
        except ValueError:
            return None

    SOURCE_RATIO_MAP = {
        "current_ratio": "current_ratio",
        "debt_to_equity": "debt_to_equity",
        "roe": "roe",
        "roce": "roce",
        "eps": "eps",
        "interest_coverage": "interest_coverage",
        "inventory_turnover": "inventory_turnover",
        "asset_turnover": "asset_turnover",
    }

    def _source_ratios_from_tables(self, tables: list[ParsedTable]) -> dict[str, dict[int, float]]:
        source: dict[str, dict[int, float]] = {}

        for table in tables:
            name_token = _clean_token(table.name)

            if "ratios" not in name_token:
                continue

            year_columns = []
            for idx, column in enumerate(table.columns):
                year = _to_year(column)
                if year is not None:
                    year_columns.append((idx, year))

            for row in table.rows:
                key = self.SOURCE_RATIO_MAP.get(_clean_token(self._cell(row, 0)))

                if key is None:
                    continue

                for idx, year in year_columns:
                    value = _to_float(self._cell(row, idx))

                    if value is not None:
                        source.setdefault(key, {})[year] = value

        return source

    def _cell(self, row: list[Any], idx: int | None) -> Any:
        if idx is None or idx < 0:
            return None
        return row[idx] if idx < len(row) else None
