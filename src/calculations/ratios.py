from __future__ import annotations

import math
from typing import Optional

from ..models import NormalizedCompany
from ..models.ratios import RatioResult, RatioSet
from .financial_extractor import FinancialExtractor, FinancialSnapshot


class RatioCalculator:
    """Calculates the 26 locked M2 financial ratios."""

    def calculate_all(
        self,
        company: NormalizedCompany,
        fiscal_year: int | None = None,
    ) -> RatioSet:
        extractor = FinancialExtractor(company)

        if fiscal_year is None:
            fiscal_year = extractor.latest_fiscal_year()

        if fiscal_year is None:
            raise ValueError("No fiscal years available")

        snapshot = extractor.snapshot(fiscal_year)
        latest_year = extractor.latest_fiscal_year()
        close = extractor.latest_close() if fiscal_year == latest_year else None

        ratios: list[RatioResult] = []

        def interpret(name: str, value: Optional[float], status: str) -> str:
            if status == "ok":
                return f"{name} = {value:.6f}. Compare against historical trend and benchmark."
            if status == "missing_inputs":
                return f"{name} unavailable because required inputs are missing."
            if status == "division_by_zero":
                return f"{name} unavailable because the denominator is zero."
            return f"{name} is not meaningful for the current inputs."

        def add(
            name: str,
            category: str,
            value: Optional[float],
            status: str,
            formula: str,
            inputs: dict[str, Optional[float]],
        ) -> None:
            ratios.append(
                RatioResult(
                    name=name,
                    category=category,
                    fiscal_year=fiscal_year,
                    value=value,
                    formula=formula,
                    interpretation=interpret(name, value, status),
                    inputs=inputs,
                    status=status,
                )
            )

        def divide(numerator: Optional[float], denominator: Optional[float]) -> tuple[Optional[float], str]:
            if numerator is None or denominator is None:
                return None, "missing_inputs"
            if math.isclose(denominator, 0.0, abs_tol=1e-12):
                return None, "division_by_zero"
            if denominator <= 0:
                return None, "not_meaningful"
            if not math.isfinite(numerator) or not math.isfinite(denominator):
                return None, "missing_inputs"
            return numerator / denominator, "ok"

        current_assets = snapshot.get("current_assets")
        current_liabilities = snapshot.get("current_liabilities")
        cash = snapshot.get("cash_and_equivalents")
        operating_cash_flow = snapshot.get("operating_cash_flow")
        total_assets = snapshot.get("total_assets")

        value, status = divide(current_assets, current_liabilities)
        add("current_ratio", "liquidity", value, status, "current_assets / current_liabilities", {
            "current_assets": current_assets,
            "current_liabilities": current_liabilities,
        })

        quick_assets = self._quick_assets(snapshot)
        value, status = divide(quick_assets, current_liabilities)
        add("quick_ratio", "liquidity", value, status, "quick_assets / current_liabilities", {
            "quick_assets": quick_assets,
            "current_liabilities": current_liabilities,
        })

        value, status = divide(cash, current_liabilities)
        add("cash_ratio", "liquidity", value, status, "cash_and_equivalents / current_liabilities", {
            "cash_and_equivalents": cash,
            "current_liabilities": current_liabilities,
        })

        value, status = divide(operating_cash_flow, current_liabilities)
        add("operating_cash_flow_ratio", "liquidity", value, status, "operating_cash_flow / current_liabilities", {
            "operating_cash_flow": operating_cash_flow,
            "current_liabilities": current_liabilities,
        })

        working_capital = None
        if current_assets is not None and current_liabilities is not None:
            working_capital = current_assets - current_liabilities

        value, status = divide(working_capital, total_assets)
        add("working_capital_ratio", "liquidity", value, status, "(current_assets - current_liabilities) / total_assets", {
            "working_capital": working_capital,
            "total_assets": total_assets,
        })

        defensive_assets = self._defensive_assets(snapshot)
        daily_operating_expenses = self._daily_operating_expenses(snapshot)
        value, status = divide(defensive_assets, daily_operating_expenses)
        add("defensive_interval_ratio", "liquidity", value, status, "defensive_assets / daily_operating_expenses", {
            "defensive_assets": defensive_assets,
            "daily_operating_expenses": daily_operating_expenses,
        })

        total_debt = snapshot.get("total_debt")
        total_equity = snapshot.get("total_equity")
        long_term_debt = snapshot.get("long_term_debt")

        value, status = divide(total_debt, total_equity)
        add("debt_to_equity", "solvency", value, status, "total_debt / total_equity", {
            "total_debt": total_debt,
            "total_equity": total_equity,
        })

        value, status = divide(total_debt, total_assets)
        add("debt_to_assets", "solvency", value, status, "total_debt / total_assets", {
            "total_debt": total_debt,
            "total_assets": total_assets,
        })

        ebit = snapshot.get("ebit")
        interest_expense = snapshot.get("interest_expense")
        value, status = divide(ebit, interest_expense)
        add("interest_coverage", "solvency", value, status, "ebit / interest_expense", {
            "ebit": ebit,
            "interest_expense": interest_expense,
        })

        value, status = divide(total_assets, total_equity)
        add("equity_multiplier", "solvency", value, status, "total_assets / total_equity", {
            "total_assets": total_assets,
            "total_equity": total_equity,
        })

        value, status = divide(long_term_debt, total_equity)
        add("long_term_debt_to_equity", "solvency", value, status, "long_term_debt / total_equity", {
            "long_term_debt": long_term_debt,
            "total_equity": total_equity,
        })

        revenue = snapshot.get("revenue")
        gross_profit = snapshot.get("gross_profit")
        operating_profit = snapshot.get("operating_profit")
        ebitda = snapshot.get("ebitda")
        net_profit = snapshot.get("net_profit")

        value, status = divide(gross_profit, revenue)
        add("gross_margin", "profitability", value, status, "gross_profit / revenue", {
            "gross_profit": gross_profit,
            "revenue": revenue,
        })

        value, status = divide(operating_profit, revenue)
        add("operating_margin", "profitability", value, status, "operating_profit / revenue", {
            "operating_profit": operating_profit,
            "revenue": revenue,
        })

        value, status = divide(ebitda, revenue)
        add("ebitda_margin", "profitability", value, status, "ebitda / revenue", {
            "ebitda": ebitda,
            "revenue": revenue,
        })

        value, status = divide(net_profit, revenue)
        add("net_profit_margin", "profitability", value, status, "net_profit / revenue", {
            "net_profit": net_profit,
            "revenue": revenue,
        })

        value, status = divide(net_profit, total_assets)
        add("roa", "profitability", value, status, "net_profit / total_assets", {
            "net_profit": net_profit,
            "total_assets": total_assets,
        })

        value, status = divide(net_profit, total_equity)
        add("roe", "profitability", value, status, "net_profit / total_equity", {
            "net_profit": net_profit,
            "total_equity": total_equity,
        })

        capital_employed = None
        if total_assets is not None and current_liabilities is not None:
            capital_employed = total_assets - current_liabilities

        value, status = divide(ebit, capital_employed)
        add("roce", "profitability", value, status, "ebit / (total_assets - current_liabilities)", {
            "ebit": ebit,
            "capital_employed": capital_employed,
        })

        fixed_assets = snapshot.get("fixed_assets")
        inventory = snapshot.get("inventory")
        receivables = snapshot.get("receivables")
        payables = snapshot.get("payables")
        cogs = snapshot.get("cogs")

        value, status = divide(revenue, total_assets)
        add("asset_turnover", "efficiency", value, status, "revenue / total_assets", {
            "revenue": revenue,
            "total_assets": total_assets,
        })

        value, status = divide(revenue, fixed_assets)
        add("fixed_asset_turnover", "efficiency", value, status, "revenue / fixed_assets", {
            "revenue": revenue,
            "fixed_assets": fixed_assets,
        })

        value, status = divide(cogs, inventory)
        add("inventory_turnover", "efficiency", value, status, "cogs / inventory", {
            "cogs": cogs,
            "inventory": inventory,
        })

        value, status = divide(revenue, receivables)
        add("receivables_turnover", "efficiency", value, status, "revenue / receivables", {
            "revenue": revenue,
            "receivables": receivables,
        })

        value, status = divide(cogs, payables)
        add("payables_turnover", "efficiency", value, status, "cogs / payables", {
            "cogs": cogs,
            "payables": payables,
        })

        shares_outstanding = snapshot.get("shares_outstanding")

        eps, eps_status = divide(net_profit, shares_outstanding)
        add("eps", "market", eps, eps_status, "net_profit / shares_outstanding", {
            "net_profit": net_profit,
            "shares_outstanding": shares_outstanding,
        })

        pe_value = None
        if eps is None:
            pe_status = eps_status
        elif close is None:
            pe_status = "missing_inputs"
        elif eps <= 0:
            pe_status = "not_meaningful"
        else:
            pe_value = close / eps
            pe_status = "ok"

        add("pe_ratio", "market", pe_value, pe_status, "latest_close / eps", {
            "latest_close": close,
            "eps": eps,
        })

        book_value_per_share, bv_status = divide(total_equity, shares_outstanding)
        pb_value = None
        if book_value_per_share is None:
            pb_status = bv_status
        elif close is None:
            pb_status = "missing_inputs"
        elif book_value_per_share <= 0:
            pb_status = "not_meaningful"
        else:
            pb_value = close / book_value_per_share
            pb_status = "ok"

        add("pb_ratio", "market", pb_value, pb_status, "latest_close / (total_equity / shares_outstanding)", {
            "latest_close": close,
            "book_value_per_share": book_value_per_share,
        })

        source_ratios = getattr(company, "source_ratios", {}) or {}

        if source_ratios:
            merged: list[RatioResult] = []

            for ratio in ratios:
                if ratio.value is None:
                    source_value = (source_ratios.get(ratio.name) or {}).get(fiscal_year)

                    if source_value is not None:
                        ratio = ratio.model_copy(
                            update={"value": float(source_value), "status": "source_provided"}
                        )

                merged.append(ratio)

            ratios = merged

        return RatioSet(fiscal_year=fiscal_year, ratios=ratios)

    def calculate_multi_year(
        self,
        company: NormalizedCompany,
        years: int = 5,
    ) -> list[RatioSet]:
        extractor = FinancialExtractor(company)
        all_years = extractor.fiscal_years()

        if not all_years:
            return []

        selected_years = all_years[-years:]
        return [self.calculate_all(company, fiscal_year=year) for year in selected_years]

    def _quick_assets(self, snapshot: FinancialSnapshot) -> Optional[float]:
        cash = snapshot.get("cash_and_equivalents")
        investments = snapshot.get("short_term_investments")
        receivables = snapshot.get("receivables")

        if cash is not None and investments is not None and receivables is not None:
            return cash + investments + receivables

        current_assets = snapshot.get("current_assets")
        inventory = snapshot.get("inventory")

        if current_assets is not None and inventory is not None:
            return current_assets - inventory

        return None

    def _defensive_assets(self, snapshot: FinancialSnapshot) -> Optional[float]:
        cash = snapshot.get("cash_and_equivalents")
        investments = snapshot.get("short_term_investments")
        receivables = snapshot.get("receivables")

        if cash is not None and investments is not None and receivables is not None:
            return cash + investments + receivables

        return None

    def _daily_operating_expenses(self, snapshot: FinancialSnapshot) -> Optional[float]:
        cogs = snapshot.get("cogs")
        operating_expenses = snapshot.get("operating_expenses")

        if operating_expenses is None:
            revenue = snapshot.get("revenue")
            operating_profit = snapshot.get("operating_profit")

            if revenue is not None and cogs is not None and operating_profit is not None:
                operating_expenses = revenue - cogs - operating_profit

        if operating_expenses is None:
            return None

        base = (cogs if cogs is not None else 0.0) + operating_expenses

        if base <= 0:
            return None

        return base / 365.0
