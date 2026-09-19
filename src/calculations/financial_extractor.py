from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Optional

from ..models import NormalizedCompany

CONTAINS_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("operating_cash_flow", ("operating_cash_flow", "cash_flow_from_operations", "net_cash_from_operating", "cash_generated_from_operations", "cash_from_operating")),
    ("cash_and_equivalents", ("cash_and_equivalents", "cash_equivalents", "cash_balance", "cash_in_hand")),
    ("short_term_investments", ("short_term_investment", "marketable_securities", "investments")),
    ("receivables", ("receivable", "sundry_debtor")),
    ("inventory", ("inventory", "inventories", "stock_in_trade")),
    ("payables", ("payable", "sundry_creditor")),
    ("current_assets", ("current_asset",)),
    ("current_liabilities", ("current_liabilit",)),
    ("fixed_assets", ("fixed_asset", "property_plant", "ppe")),
    ("long_term_debt", ("long_term_debt", "long_term_borrowing", "non_current_borrowing")),
    ("total_debt", ("total_debt", "borrowing", "debt")),
    ("retained_earnings", ("retained_earnings", "retained_earning")),
    ("equity_capital", ("equity_capital", "share_capital")),
    ("reserves", ("reserves", "surplus")),
    ("total_equity", ("total_equity", "shareholders_equity", "net_worth", "total_shareholders_funds")),
    ("total_assets", ("total_asset",)),
    ("total_liabilities", ("total_liabilit",)),
    ("capex", ("capex", "capital_expenditure")),
    ("shares_outstanding", ("shares_outstanding", "outstanding_share", "number_of_share", "equity_share")),
    ("eps", ("eps", "earnings_per_share")),
    ("revenue", ("revenue", "net_sales", "sales", "total_income")),
    ("cogs", ("cost_of_goods", "cost_of_revenue", "cost_of_sales", "cogs", "purchase")),
    ("gross_profit", ("gross_profit",)),
    ("operating_expenses", ("operating_expense", "operating_expenses", "expenses", "opex", "selling_general", "sga")),
    ("operating_profit", ("operating_profit", "operating_income", "financing_profit")),
    ("ebitda", ("ebitda",)),
    ("ebit", ("ebit", "profit_before_interest_and_tax", "profit_before_tax")),
    ("interest_expense", ("interest_expense", "finance_cost", "interest_paid", "interest")),
    ("net_profit", ("net_profit", "net_income", "profit_after_tax", "profit_for_the_year", "pat")),
    ("depreciation_amortization", ("depreciation", "amortization")),
]


def normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def map_line_item(line_item: str) -> Optional[str]:
    token = normalize_token(line_item)
    if not token:
        return None

    for canonical, fragments in CONTAINS_RULES:
        if any(fragment in token for fragment in fragments):
            return canonical

    return None


@dataclass
class FinancialSnapshot:
    """Canonical financial values for one fiscal year."""

    fiscal_year: int
    values: dict[str, float] = field(default_factory=dict)

    def get(self, key: str) -> Optional[float]:
        return self.values.get(key)


class FinancialExtractor:
    """Extracts canonical financial inputs from normalized company data."""

    def __init__(self, company: NormalizedCompany) -> None:
        self._company = company

    def fiscal_years(self) -> list[int]:
        return sorted({line.fiscal_year for line in self._company.financials})

    def latest_fiscal_year(self) -> Optional[int]:
        years = self.fiscal_years()
        return years[-1] if years else None

    def latest_close(self) -> Optional[float]:
        if not self._company.prices:
            return None
        return sorted(self._company.prices, key=lambda price: price.date)[-1].close

    def snapshot(self, fiscal_year: int) -> FinancialSnapshot:
        values: dict[str, float] = {}
        lines = sorted(self._company.financials, key=lambda line: (line.statement_type, line.line_item))

        for line in lines:
            if line.fiscal_year != fiscal_year:
                continue

            canonical = map_line_item(line.line_item)
            if canonical and canonical not in values:
                values[canonical] = line.value

        self._apply_fallbacks(values)
        return FinancialSnapshot(fiscal_year=fiscal_year, values=values)

    def _apply_fallbacks(self, values: dict[str, float]) -> None:
        if values.get("total_equity") is None:
            equity_capital = values.get("equity_capital")
            reserves = values.get("reserves")

            if equity_capital is not None and reserves is not None:
                values["total_equity"] = equity_capital + reserves
            elif values.get("total_assets") is not None and values.get("total_liabilities") is not None:
                values["total_equity"] = values["total_assets"] - values["total_liabilities"]

        revenue = values.get("revenue")
        cogs = values.get("cogs")
        operating_profit = values.get("operating_profit")
        ebitda = values.get("ebitda")
        depreciation = values.get("depreciation_amortization")

        if values.get("gross_profit") is None and revenue is not None and cogs is not None:
            values["gross_profit"] = revenue - cogs

        if values.get("ebit") is None and operating_profit is not None:
            values["ebit"] = operating_profit

        if values.get("operating_profit") is None and ebitda is not None and depreciation is not None:
            values["operating_profit"] = ebitda - depreciation

        if values.get("ebitda") is None and operating_profit is not None and depreciation is not None:
            values["ebitda"] = operating_profit + depreciation

        if values.get("total_debt") is None and values.get("total_liabilities") is not None:
            values["total_debt"] = values["total_liabilities"]

        # Public company pages often omit current classifications, especially for banks.
        if values.get("current_assets") is None:
            total_assets = values.get("total_assets")
            fixed_assets = values.get("fixed_assets")
            if total_assets is not None:
                values["current_assets"] = total_assets - (fixed_assets or 0.0)

        if values.get("current_liabilities") is None:
            total_liabilities = values.get("total_liabilities")
            total_equity = values.get("total_equity")
            if total_liabilities is not None:
                values["current_liabilities"] = max(
                    total_liabilities - (total_equity or 0.0), 0.0
                )

        if values.get("shares_outstanding") is None:
            net_profit = values.get("net_profit")
            eps = values.get("eps")
            if net_profit is not None and eps is not None and not math.isclose(eps, 0.0):
                values["shares_outstanding"] = net_profit / eps
