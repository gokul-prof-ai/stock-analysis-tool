from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from ..models import NormalizedCompany
from ..models.scenario import (
    ForecastPoint,
    HistoricalPoint,
    MacroOverlay,
    ScenarioForecast,
    ScenarioReport,
)
from .financial_extractor import FinancialExtractor
from .valuation import ValuationExtractor


@dataclass(frozen=True)
class ScenarioConfig:
    """Scenario and forecast assumptions."""

    projection_years: int = 3
    default_growth: float = 0.05
    bull_adjust: float = 0.03
    bear_adjust: float = 0.03
    max_growth: float = 0.25
    min_growth: float = -0.20

    macro_gdp_growth: float = 0.06
    macro_interest_rate: float = 0.07
    macro_inflation: float = 0.05
    macro_sensitivity: float = 0.0

    default_target_pe: float = 15.0
    default_ev_ebitda: float = 8.0
    bull_multiple_adjust: float = 0.10
    bear_multiple_adjust: float = -0.10

    @classmethod
    def from_dict(cls, data: dict | None) -> ScenarioConfig:
        base = cls()

        if not isinstance(data, dict):
            return base

        try:
            return cls(
                projection_years=int(data.get("projection_years", base.projection_years)),
                default_growth=float(data.get("default_growth", base.default_growth)),
                bull_adjust=float(data.get("bull_adjust", base.bull_adjust)),
                bear_adjust=float(data.get("bear_adjust", base.bear_adjust)),
                max_growth=float(data.get("max_growth", base.max_growth)),
                min_growth=float(data.get("min_growth", base.min_growth)),
                macro_gdp_growth=float(data.get("macro_gdp_growth", base.macro_gdp_growth)),
                macro_interest_rate=float(data.get("macro_interest_rate", base.macro_interest_rate)),
                macro_inflation=float(data.get("macro_inflation", base.macro_inflation)),
                macro_sensitivity=float(data.get("macro_sensitivity", base.macro_sensitivity)),
                default_target_pe=float(data.get("default_target_pe", base.default_target_pe)),
                default_ev_ebitda=float(data.get("default_ev_ebitda", base.default_ev_ebitda)),
                bull_multiple_adjust=float(data.get("bull_multiple_adjust", base.bull_multiple_adjust)),
                bear_multiple_adjust=float(data.get("bear_multiple_adjust", base.bear_multiple_adjust)),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid scenario configuration") from exc


def _median(values: list[float]) -> Optional[float]:
    cleaned = sorted(value for value in values if value is not None and math.isfinite(value))

    if not cleaned:
        return None

    mid = len(cleaned) // 2

    if len(cleaned) % 2 == 1:
        return cleaned[mid]

    return (cleaned[mid - 1] + cleaned[mid]) / 2.0


class ScenarioAnalyzer:
    """M7 scenario, forecast, macro overlay, and target-price engine."""

    def __init__(self, config: ScenarioConfig | None = None) -> None:
        self.config = config or ScenarioConfig()

    def analyze(self, company: NormalizedCompany) -> ScenarioReport:
        extractor = FinancialExtractor(company)
        years = extractor.fiscal_years()

        if not years:
            raise ValueError("No financial years available for scenario analysis")

        valuation_inputs = ValuationExtractor(company).inputs()

        historical: list[HistoricalPoint] = []

        for fiscal_year in years:
            snapshot = extractor.snapshot(fiscal_year)

            revenue = snapshot.get("revenue")
            ebitda = snapshot.get("ebitda")
            net_profit = snapshot.get("net_profit")
            shares = snapshot.get("shares_outstanding")

            if shares is None:
                shares = valuation_inputs.shares_outstanding

            eps = None
            if net_profit is not None and shares is not None and shares > 0:
                eps = net_profit / shares

            historical.append(
                HistoricalPoint(
                    fiscal_year=fiscal_year,
                    revenue=revenue,
                    ebitda=ebitda,
                    net_profit=net_profit,
                    eps=eps,
                )
            )

        latest_year = years[-1]
        latest = historical[-1]

        revenue_values = [point.revenue for point in historical if point.revenue is not None]
        ebitda_values = [point.ebitda for point in historical if point.ebitda is not None]
        eps_values = [point.eps for point in historical if point.eps is not None]

        revenue_base = self._estimate_growth(revenue_values)
        ebitda_base = self._estimate_growth(ebitda_values)
        eps_base = self._estimate_growth(eps_values)

        assumptions: list[str] = []

        fallback_growth = next(
            value
            for value in (revenue_base, ebitda_base, eps_base, self.config.default_growth)
            if value is not None
        )

        if revenue_base is None:
            revenue_base = fallback_growth
            assumptions.append("Revenue growth unavailable; using fallback growth assumption.")

        if ebitda_base is None:
            ebitda_base = revenue_base
            assumptions.append("EBITDA growth unavailable; using revenue growth assumption.")

        if eps_base is None:
            eps_base = revenue_base
            assumptions.append("EPS growth unavailable; using revenue growth assumption.")

        macro = self._macro_overlay()

        revenue_base = self._cap_growth(revenue_base + macro.adjustment)
        ebitda_base = self._cap_growth(ebitda_base + macro.adjustment)
        eps_base = self._cap_growth(eps_base + macro.adjustment)

        if self.config.macro_sensitivity == 0:
            assumptions.append("Macro overlay sensitivity is zero; macro variables are disclosed but not applied.")

        assumptions.append("Shares outstanding are assumed constant over the projection period.")
        assumptions.append(
            "Target price blends forward P/E and forward EV/EBITDA implied values when both are available."
        )

        scenario_definitions = [
            ("bull", self.config.bull_adjust),
            ("base", 0.0),
            ("bear", -self.config.bear_adjust),
        ]

        scenarios: list[ScenarioForecast] = []

        for name, scenario_adjust in scenario_definitions:
            revenue_growth = self._cap_growth(revenue_base + scenario_adjust)
            ebitda_growth = self._cap_growth(ebitda_base + scenario_adjust)
            eps_growth = self._cap_growth(eps_base + scenario_adjust)

            revenue_forecast = self._forecast_points(latest.revenue, revenue_growth, latest_year)
            ebitda_forecast = self._forecast_points(latest.ebitda, ebitda_growth, latest_year)
            eps_forecast = self._forecast_points(latest.eps, eps_growth, latest_year)

            target_price = self._target_price(
                scenario_name=name,
                ebitda_forecast=ebitda_forecast,
                eps_forecast=eps_forecast,
                valuation_inputs=valuation_inputs,
                latest=latest,
            )

            upside_pct = None
            if (
                target_price is not None
                and valuation_inputs.price is not None
                and valuation_inputs.price > 0
            ):
                upside_pct = 100.0 * (target_price - valuation_inputs.price) / valuation_inputs.price

            narrative = (
                f"{name.capitalize()} scenario assumes revenue growth of {revenue_growth:.2%}, "
                f"EBITDA growth of {ebitda_growth:.2%}, and EPS growth of {eps_growth:.2%}."
            )

            scenarios.append(
                ScenarioForecast(
                    name=name,
                    growth_rate=revenue_growth,
                    ebitda_growth_rate=ebitda_growth,
                    eps_growth_rate=eps_growth,
                    revenue=revenue_forecast,
                    ebitda=ebitda_forecast,
                    eps=eps_forecast,
                    target_price=target_price,
                    upside_pct=upside_pct,
                    narrative=narrative,
                )
            )

        base_scenario = next(scenario for scenario in scenarios if scenario.name == "base")
        bull_scenario = next(scenario for scenario in scenarios if scenario.name == "bull")
        bear_scenario = next(scenario for scenario in scenarios if scenario.name == "bear")

        target_price_lower = None
        target_price_upper = None

        if bear_scenario.target_price is not None and bull_scenario.target_price is not None:
            target_price_lower = bear_scenario.target_price
            target_price_upper = bull_scenario.target_price
        else:
            bear_revenue = bear_scenario.revenue[-1].value if bear_scenario.revenue else None
            bull_revenue = bull_scenario.revenue[-1].value if bull_scenario.revenue else None

            target_price_lower = bear_revenue
            target_price_upper = bull_revenue

        if base_scenario.target_price is not None:
            status = "ok"
        elif base_scenario.revenue:
            status = "partial"
        else:
            status = "unavailable"

        return ScenarioReport(
            ticker=company.company.ticker,
            latest_fiscal_year=latest_year,
            historical=historical,
            base_growth=revenue_base,
            growth_rates={
                "revenue": revenue_base,
                "ebitda": ebitda_base,
                "eps": eps_base,
            },
            macro=macro,
            scenarios=scenarios,
            base_target_price=base_scenario.target_price,
            target_price_lower=target_price_lower,
            target_price_upper=target_price_upper,
            assumptions=assumptions,
            status=status,
        )

    def _estimate_growth(self, values: list[Optional[float]]) -> Optional[float]:
        cleaned = [value for value in values if value is not None and math.isfinite(value)]

        if len(cleaned) >= 2 and cleaned[0] > 0 and cleaned[-1] > 0:
            periods = len(cleaned) - 1
            cagr = (cleaned[-1] / cleaned[0]) ** (1.0 / periods) - 1.0

            if math.isfinite(cagr):
                return cagr

        yoy_changes: list[float] = []

        for index in range(1, len(cleaned)):
            previous = cleaned[index - 1]
            current = cleaned[index]

            if previous > 0:
                change = (current - previous) / previous

                if math.isfinite(change):
                    yoy_changes.append(change)

        if yoy_changes:
            return _median(yoy_changes)

        return None

    def _macro_overlay(self) -> MacroOverlay:
        adjustment = self.config.macro_sensitivity * (
            self.config.macro_gdp_growth
            - self.config.macro_inflation
            - self.config.macro_interest_rate
        )

        interpretation = (
            "Macro overlay adjustment = sensitivity * (GDP growth - inflation - interest rate). "
            f"Computed adjustment is {adjustment:.2%}."
        )

        return MacroOverlay(
            gdp_growth=self.config.macro_gdp_growth,
            interest_rate=self.config.macro_interest_rate,
            inflation=self.config.macro_inflation,
            sensitivity=self.config.macro_sensitivity,
            adjustment=adjustment,
            interpretation=interpretation,
        )

    def _forecast_points(
        self,
        latest_value: Optional[float],
        growth_rate: float,
        latest_year: int,
    ) -> list[ForecastPoint]:
        if latest_value is None:
            return []

        points: list[ForecastPoint] = []

        for step in range(1, self.config.projection_years + 1):
            value = latest_value * ((1.0 + growth_rate) ** step)

            points.append(
                ForecastPoint(
                    fiscal_year=latest_year + step,
                    value=value,
                )
            )

        return points

    def _target_price(
        self,
        scenario_name: str,
        ebitda_forecast: list[ForecastPoint],
        eps_forecast: list[ForecastPoint],
        valuation_inputs,
        latest: HistoricalPoint,
    ) -> Optional[float]:
        final_ebitda = ebitda_forecast[-1].value if ebitda_forecast else None
        final_eps = eps_forecast[-1].value if eps_forecast else None

        if scenario_name == "bull":
            multiple_adjust = self.config.bull_multiple_adjust
        elif scenario_name == "bear":
            multiple_adjust = self.config.bear_multiple_adjust
        else:
            multiple_adjust = 0.0

        multiple_factor = 1.0 + multiple_adjust

        target_pe = self._current_pe(valuation_inputs.price, latest.eps)
        if target_pe is None:
            target_pe = self.config.default_target_pe

        target_ev_ebitda = self._current_ev_ebitda(valuation_inputs, latest.ebitda)
        if target_ev_ebitda is None:
            target_ev_ebitda = self.config.default_ev_ebitda

        eps_target = None
        if final_eps is not None and final_eps > 0:
            eps_target = final_eps * target_pe * multiple_factor

        ev_target = None
        if (
            final_ebitda is not None
            and final_ebitda > 0
            and valuation_inputs.shares_outstanding is not None
            and valuation_inputs.shares_outstanding > 0
        ):
            market_cap = valuation_inputs.market_cap
            debt = valuation_inputs.total_debt if valuation_inputs.total_debt is not None else 0.0
            cash = valuation_inputs.cash if valuation_inputs.cash is not None else 0.0

            if market_cap is not None:
                enterprise_value = market_cap + debt - cash
                net_debt = valuation_inputs.net_debt if valuation_inputs.net_debt is not None else 0.0

                if enterprise_value > 0 and latest.ebitda is not None and latest.ebitda > 0:
                    target_ev = final_ebitda * target_ev_ebitda * multiple_factor
                    implied_equity = target_ev - net_debt

                    if implied_equity > 0:
                        ev_target = implied_equity / valuation_inputs.shares_outstanding

        candidates = [value for value in (eps_target, ev_target) if value is not None]

        if not candidates:
            return None

        return sum(candidates) / len(candidates)

    def _current_pe(self, price: Optional[float], eps: Optional[float]) -> Optional[float]:
        if price is None or eps is None or eps <= 0:
            return None

        return price / eps

    def _current_ev_ebitda(self, valuation_inputs, latest_ebitda: Optional[float]) -> Optional[float]:
        if (
            valuation_inputs.market_cap is None
            or latest_ebitda is None
            or latest_ebitda <= 0
        ):
            return None

        debt = valuation_inputs.total_debt if valuation_inputs.total_debt is not None else 0.0
        cash = valuation_inputs.cash if valuation_inputs.cash is not None else 0.0

        enterprise_value = valuation_inputs.market_cap + debt - cash

        if enterprise_value <= 0:
            return None

        return enterprise_value / latest_ebitda

    def _cap_growth(self, growth_rate: float) -> float:
        return max(self.config.min_growth, min(self.config.max_growth, growth_rate))
