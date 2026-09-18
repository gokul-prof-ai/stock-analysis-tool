from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from ..models import NormalizedCompany
from ..models.valuation import (
    ComparableMetricResult,
    ComparableResult,
    DCFResult,
    DCFScenarioResult,
    MultiplesResult,
    ScenarioValuation,
    SensitivityResult,
    ValuationReport,
)
from .financial_extractor import FinancialExtractor, normalize_token
from .industry import IndustryAnalyzer


@dataclass
class ValuationInputs:
    """Canonical valuation inputs."""

    ticker: Optional[str] = None
    fiscal_year: Optional[int] = None
    price: Optional[float] = None
    shares_outstanding: Optional[float] = None
    market_cap: Optional[float] = None
    revenue: Optional[float] = None
    net_profit: Optional[float] = None
    total_equity: Optional[float] = None
    ebitda: Optional[float] = None
    cash: Optional[float] = None
    total_debt: Optional[float] = None
    net_debt: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    capex: Optional[float] = None
    free_cash_flow: Optional[float] = None


@dataclass(frozen=True)
class ValuationConfig:
    """Valuation assumptions."""

    projection_years: int = 5
    discount_rate: float = 0.10
    terminal_growth: float = 0.025
    bull_growth: float = 0.12
    base_growth: float = 0.08
    bear_growth: float = 0.03
    undervalued_threshold: float = 20.0
    fair_threshold: float = -10.0
    max_peers: int = 5
    sensitivity_wacc_values: tuple[float, ...] = (0.08, 0.09, 0.10, 0.11, 0.12)
    sensitivity_terminal_growth_values: tuple[float, ...] = (0.010, 0.015, 0.020, 0.025, 0.030)

    @classmethod
    def from_dict(cls, data: dict | None) -> ValuationConfig:
        base = cls()

        if not isinstance(data, dict):
            return base

        try:
            projection_years = int(data.get("projection_years", base.projection_years))
            discount_rate = float(data.get("discount_rate", base.discount_rate))
            terminal_growth = float(data.get("terminal_growth", base.terminal_growth))
            bull_growth = float(data.get("bull_growth", base.bull_growth))
            base_growth = float(data.get("base_growth", base.base_growth))
            bear_growth = float(data.get("bear_growth", base.bear_growth))
            undervalued_threshold = float(data.get("undervalued_threshold", base.undervalued_threshold))
            fair_threshold = float(data.get("fair_threshold", base.fair_threshold))
            max_peers = int(data.get("max_peers", base.max_peers))
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid valuation configuration") from exc

        wacc_values = base.sensitivity_wacc_values
        terminal_values = base.sensitivity_terminal_growth_values

        raw_wacc = data.get("sensitivity_wacc_values")
        if isinstance(raw_wacc, list):
            wacc_values = tuple(float(item) for item in raw_wacc)

        raw_terminal = data.get("sensitivity_terminal_growth_values")
        if isinstance(raw_terminal, list):
            terminal_values = tuple(float(item) for item in raw_terminal)

        return cls(
            projection_years=projection_years,
            discount_rate=discount_rate,
            terminal_growth=terminal_growth,
            bull_growth=bull_growth,
            base_growth=base_growth,
            bear_growth=bear_growth,
            undervalued_threshold=undervalued_threshold,
            fair_threshold=fair_threshold,
            max_peers=max_peers,
            sensitivity_wacc_values=wacc_values,
            sensitivity_terminal_growth_values=terminal_values,
        )


def _safe_div(
    numerator: Optional[float],
    denominator: Optional[float],
    require_positive_den: bool = True,
) -> Optional[float]:
    if numerator is None or denominator is None:
        return None

    if not math.isfinite(numerator) or not math.isfinite(denominator):
        return None

    if math.isclose(denominator, 0.0, abs_tol=1e-12):
        return None

    if require_positive_den and denominator <= 0:
        return None

    return numerator / denominator


def _median(values: list[float]) -> Optional[float]:
    cleaned = sorted(value for value in values if value is not None and math.isfinite(value))

    if not cleaned:
        return None

    mid = len(cleaned) // 2

    if len(cleaned) % 2 == 1:
        return cleaned[mid]

    return (cleaned[mid - 1] + cleaned[mid]) / 2.0


class ValuationExtractor:
    """Extracts valuation inputs from normalized company data."""

    def __init__(self, company: NormalizedCompany) -> None:
        self._company = company
        self._extractor = FinancialExtractor(company)

    def inputs(self) -> ValuationInputs:
        fiscal_year = self._extractor.latest_fiscal_year()

        if fiscal_year is None:
            return ValuationInputs(ticker=self._company.company.ticker)

        snapshot = self._extractor.snapshot(fiscal_year)

        price = self._extractor.latest_close()
        shares = snapshot.get("shares_outstanding")

        market_cap = None
        if price is not None and shares is not None and shares > 0:
            market_cap = price * shares

        cash_components = [
            value
            for value in (
                snapshot.get("cash_and_equivalents"),
                snapshot.get("short_term_investments"),
            )
            if value is not None
        ]

        cash = sum(cash_components) if cash_components else None
        total_debt = snapshot.get("total_debt")

        net_debt = None
        if total_debt is not None and cash is not None:
            net_debt = total_debt - cash

        operating_cash_flow = snapshot.get("operating_cash_flow")
        capex = self._capex(fiscal_year)

        free_cash_flow = None
        if operating_cash_flow is not None:
            free_cash_flow = operating_cash_flow if capex is None else operating_cash_flow - capex

        return ValuationInputs(
            ticker=self._company.company.ticker,
            fiscal_year=fiscal_year,
            price=price,
            shares_outstanding=shares,
            market_cap=market_cap,
            revenue=snapshot.get("revenue"),
            net_profit=snapshot.get("net_profit"),
            total_equity=snapshot.get("total_equity"),
            ebitda=snapshot.get("ebitda"),
            cash=cash,
            total_debt=total_debt,
            net_debt=net_debt,
            operating_cash_flow=operating_cash_flow,
            capex=capex,
            free_cash_flow=free_cash_flow,
        )

    def _capex(self, fiscal_year: int) -> Optional[float]:
        lines = sorted(self._company.financials, key=lambda line: (line.statement_type, line.line_item))

        for line in lines:
            if line.fiscal_year != fiscal_year:
                continue

            token = normalize_token(line.line_item)

            if "capex" in token or "capital_expenditure" in token:
                return abs(line.value)

        return None


class ValuationEngine:
    """M6 valuation engine: multiples, DCF, comparables, scenarios, sensitivity."""

    def __init__(self, config: ValuationConfig | None = None) -> None:
        self.config = config or ValuationConfig()

    def analyze(
        self,
        target: NormalizedCompany,
        candidates: list[NormalizedCompany] | None = None,
    ) -> ValuationReport:
        candidates = candidates or []

        target_inputs = self.inputs_from_company(target)
        multiples = self.calculate_multiples(target_inputs)
        dcf = self.calculate_dcf(target_inputs)
        sensitivity = self.calculate_sensitivity(target_inputs)

        peers = IndustryAnalyzer(max_peers=self.config.max_peers).select_peers(target, candidates)
        peer_map = {candidate.company.ticker: candidate for candidate in candidates}

        peer_inputs: list[ValuationInputs] = []
        for peer in peers:
            candidate = peer_map.get(peer.ticker)
            if candidate is not None:
                peer_inputs.append(self.inputs_from_company(candidate))

        comparable = self.calculate_comparable(target_inputs, peer_inputs)

        scenarios: list[ScenarioValuation] = []
        for scenario in dcf.scenarios:
            final_scenario = self._blend(scenario.intrinsic_per_share, comparable.median_implied_value)

            scenarios.append(
                ScenarioValuation(
                    name=scenario.name,
                    growth_rate=scenario.growth_rate,
                    dcf_intrinsic=scenario.intrinsic_per_share,
                    comparable_intrinsic=comparable.median_implied_value,
                    final_intrinsic=final_scenario,
                )
            )

        intrinsic_value = self._blend(dcf.base_intrinsic_per_share, comparable.median_implied_value)

        margin_of_safety = None
        if intrinsic_value is not None and target_inputs.price is not None and target_inputs.price > 0:
            margin_of_safety = 100.0 * (intrinsic_value - target_inputs.price) / target_inputs.price

        valuation_signal = self._signal(margin_of_safety)

        assumptions = list(dcf.assumptions)

        if target_inputs.price is None:
            assumptions.append("No latest market price available.")
        if target_inputs.shares_outstanding is None:
            assumptions.append("No shares outstanding available.")
        if target_inputs.capex is None and target_inputs.operating_cash_flow is not None:
            assumptions.append("Capex unavailable; using operating cash flow as free cash flow proxy.")
        if target_inputs.net_debt is None:
            assumptions.append("Net debt unavailable; assuming zero net debt in DCF.")

        multiple_available = any(
            value is not None
            for value in (multiples.pe, multiples.pb, multiples.ps, multiples.ev_ebitda)
        )
        dcf_available = dcf.base_intrinsic_per_share is not None
        comparable_available = comparable.median_implied_value is not None

        if not any((multiple_available, dcf_available, comparable_available)):
            status = "unavailable"
        elif all((multiple_available, dcf_available, comparable_available)):
            status = "ok"
        else:
            status = "partial"

        return ValuationReport(
            ticker=target.company.ticker,
            fiscal_year=target_inputs.fiscal_year,
            price=target_inputs.price,
            multiples=multiples,
            dcf=dcf,
            comparable=comparable,
            sensitivity=sensitivity,
            scenarios=scenarios,
            intrinsic_value=intrinsic_value,
            margin_of_safety=margin_of_safety,
            valuation_signal=valuation_signal,
            assumptions=assumptions,
            status=status,
        )

    def inputs_from_company(self, company: NormalizedCompany) -> ValuationInputs:
        return ValuationExtractor(company).inputs()

    def calculate_multiples(self, inputs: ValuationInputs) -> MultiplesResult:
        market_cap = inputs.market_cap

        debt = inputs.total_debt if inputs.total_debt is not None else 0.0
        cash = inputs.cash if inputs.cash is not None else 0.0

        enterprise_value = None
        if market_cap is not None:
            enterprise_value = market_cap + debt - cash

        pe = None
        if inputs.net_profit is not None and inputs.net_profit > 0:
            pe = _safe_div(market_cap, inputs.net_profit)

        pb = _safe_div(market_cap, inputs.total_equity)
        ps = _safe_div(market_cap, inputs.revenue)

        ev_ebitda = None
        if enterprise_value is not None and enterprise_value > 0:
            ev_ebitda = _safe_div(enterprise_value, inputs.ebitda)

        interpretation = (
            f"P/E={self._text(pe)}, P/B={self._text(pb)}, P/S={self._text(ps)}, "
            f"EV/EBITDA={self._text(ev_ebitda)}."
        )

        return MultiplesResult(
            pe=pe,
            pb=pb,
            ps=ps,
            ev_ebitda=ev_ebitda,
            enterprise_value=enterprise_value,
            market_cap=market_cap,
            inputs={
                "price": inputs.price,
                "shares_outstanding": inputs.shares_outstanding,
                "market_cap": market_cap,
                "net_profit": inputs.net_profit,
                "total_equity": inputs.total_equity,
                "revenue": inputs.revenue,
                "ebitda": inputs.ebitda,
                "total_debt": inputs.total_debt,
                "cash": inputs.cash,
                "enterprise_value": enterprise_value,
            },
            interpretation=interpretation,
        )

    def calculate_dcf(self, inputs: ValuationInputs) -> DCFResult:
        assumptions: list[str] = []

        if inputs.capex is None and inputs.operating_cash_flow is not None:
            assumptions.append("Capex unavailable; using operating cash flow as free cash flow proxy.")

        if inputs.net_debt is None:
            assumptions.append("Net debt unavailable; assuming zero net debt in DCF.")

        base_fcf = inputs.free_cash_flow

        if base_fcf is None or base_fcf <= 0:
            assumptions.append("DCF unavailable because free cash flow is missing or non-positive.")

            return DCFResult(
                base_fcf=base_fcf,
                discount_rate=self.config.discount_rate,
                terminal_growth=self.config.terminal_growth,
                projection_years=self.config.projection_years,
                assumptions=assumptions,
                scenarios=[],
                base_intrinsic_per_share=None,
            )

        scenario_definitions = [
            ("bull", self.config.bull_growth),
            ("base", self.config.base_growth),
            ("bear", self.config.bear_growth),
        ]

        scenarios: list[DCFScenarioResult] = []

        for name, growth in scenario_definitions:
            enterprise_value = self.dcf_enterprise_value(
                base_fcf=base_fcf,
                growth_rate=growth,
                discount_rate=self.config.discount_rate,
                terminal_growth=self.config.terminal_growth,
                projection_years=self.config.projection_years,
            )

            equity_value = None
            intrinsic_per_share = None

            if enterprise_value is not None:
                net_debt = inputs.net_debt if inputs.net_debt is not None else 0.0
                equity_value = enterprise_value - net_debt

                if inputs.shares_outstanding is not None and inputs.shares_outstanding > 0:
                    intrinsic_per_share = equity_value / inputs.shares_outstanding

            if enterprise_value is None:
                interpretation = (
                    f"{name.capitalize()} DCF unavailable because discount rate must exceed terminal growth."
                )
            else:
                interpretation = (
                    f"{name.capitalize()} scenario intrinsic value is "
                    f"{self._text(intrinsic_per_share)} per share."
                )

            scenarios.append(
                DCFScenarioResult(
                    name=name,
                    growth_rate=growth,
                    enterprise_value=enterprise_value,
                    equity_value=equity_value,
                    intrinsic_per_share=intrinsic_per_share,
                    formula=(
                        "PV(projected FCF) + PV(terminal value), "
                        "terminal value = FCF_n * (1+g) / (WACC-g)"
                    ),
                    interpretation=interpretation,
                )
            )

        base_intrinsic = next(
            (scenario.intrinsic_per_share for scenario in scenarios if scenario.name == "base"),
            None,
        )

        return DCFResult(
            base_fcf=base_fcf,
            discount_rate=self.config.discount_rate,
            terminal_growth=self.config.terminal_growth,
            projection_years=self.config.projection_years,
            assumptions=assumptions,
            scenarios=scenarios,
            base_intrinsic_per_share=base_intrinsic,
        )

    def calculate_sensitivity(self, inputs: ValuationInputs) -> SensitivityResult:
        wacc_values = list(self.config.sensitivity_wacc_values)
        terminal_values = list(self.config.sensitivity_terminal_growth_values)

        matrix: list[list[Optional[float]]] = []

        base_fcf = inputs.free_cash_flow
        net_debt = inputs.net_debt if inputs.net_debt is not None else 0.0

        for wacc in wacc_values:
            row: list[Optional[float]] = []

            for terminal_growth in terminal_values:
                if base_fcf is None or base_fcf <= 0:
                    row.append(None)
                    continue

                enterprise_value = self.dcf_enterprise_value(
                    base_fcf=base_fcf,
                    growth_rate=self.config.base_growth,
                    discount_rate=wacc,
                    terminal_growth=terminal_growth,
                    projection_years=self.config.projection_years,
                )

                if enterprise_value is None:
                    row.append(None)
                    continue

                equity_value = enterprise_value - net_debt

                if inputs.shares_outstanding is None or inputs.shares_outstanding <= 0:
                    row.append(None)
                    continue

                row.append(equity_value / inputs.shares_outstanding)

            matrix.append(row)

        return SensitivityResult(
            wacc_values=wacc_values,
            terminal_growth_values=terminal_values,
            matrix=matrix,
            interpretation="Intrinsic value per share by WACC and terminal growth rate.",
        )

    def calculate_comparable(
        self,
        target_inputs: ValuationInputs,
        peer_inputs: list[ValuationInputs],
    ) -> ComparableResult:
        target_multiples = self.calculate_multiples(target_inputs)

        peer_pe: list[float] = []
        peer_pb: list[float] = []
        peer_ps: list[float] = []
        peer_ev_ebitda: list[float] = []

        for peer in peer_inputs:
            peer_multiple = self.calculate_multiples(peer)

            if peer_multiple.pe is not None:
                peer_pe.append(peer_multiple.pe)
            if peer_multiple.pb is not None:
                peer_pb.append(peer_multiple.pb)
            if peer_multiple.ps is not None:
                peer_ps.append(peer_multiple.ps)
            if peer_multiple.ev_ebitda is not None:
                peer_ev_ebitda.append(peer_multiple.ev_ebitda)

        metrics: list[ComparableMetricResult] = []

        pe_median = _median(peer_pe)
        pe_implied = None
        target_eps = _safe_div(target_inputs.net_profit, target_inputs.shares_outstanding)

        if pe_median is not None and target_eps is not None and target_eps > 0:
            pe_implied = target_eps * pe_median

        metrics.append(
            ComparableMetricResult(
                name="pe",
                target_multiple=target_multiples.pe,
                median_multiple=pe_median,
                implied_value=pe_implied,
                peer_count=len(peer_pe),
            )
        )

        pb_median = _median(peer_pb)
        pb_implied = None
        target_bvps = _safe_div(target_inputs.total_equity, target_inputs.shares_outstanding)

        if pb_median is not None and target_bvps is not None and target_bvps > 0:
            pb_implied = target_bvps * pb_median

        metrics.append(
            ComparableMetricResult(
                name="pb",
                target_multiple=target_multiples.pb,
                median_multiple=pb_median,
                implied_value=pb_implied,
                peer_count=len(peer_pb),
            )
        )

        ps_median = _median(peer_ps)
        ps_implied = None
        target_rps = _safe_div(target_inputs.revenue, target_inputs.shares_outstanding)

        if ps_median is not None and target_rps is not None and target_rps > 0:
            ps_implied = target_rps * ps_median

        metrics.append(
            ComparableMetricResult(
                name="ps",
                target_multiple=target_multiples.ps,
                median_multiple=ps_median,
                implied_value=ps_implied,
                peer_count=len(peer_ps),
            )
        )

        ev_ebitda_median = _median(peer_ev_ebitda)
        ev_implied = None

        if (
            ev_ebitda_median is not None
            and target_inputs.ebitda is not None
            and target_inputs.ebitda > 0
        ):
            implied_ev = target_inputs.ebitda * ev_ebitda_median
            net_debt = target_inputs.net_debt if target_inputs.net_debt is not None else 0.0
            implied_equity = implied_ev - net_debt

            if (
                implied_equity > 0
                and target_inputs.shares_outstanding is not None
                and target_inputs.shares_outstanding > 0
            ):
                ev_implied = implied_equity / target_inputs.shares_outstanding

        metrics.append(
            ComparableMetricResult(
                name="ev_ebitda",
                target_multiple=target_multiples.ev_ebitda,
                median_multiple=ev_ebitda_median,
                implied_value=ev_implied,
                peer_count=len(peer_ev_ebitda),
            )
        )

        implied_values = [metric.implied_value for metric in metrics if metric.implied_value is not None]
        median_implied_value = _median(implied_values)

        return ComparableResult(
            peer_tickers=[peer.ticker for peer in peer_inputs if peer.ticker is not None],
            metrics=metrics,
            median_implied_value=median_implied_value,
            interpretation=(
                f"Comparable median implied value: {self._text(median_implied_value)} "
                f"based on {len(peer_inputs)} peers."
            ),
        )

    def dcf_enterprise_value(
        self,
        base_fcf: float,
        growth_rate: float,
        discount_rate: float,
        terminal_growth: float,
        projection_years: int,
    ) -> Optional[float]:
        if base_fcf <= 0:
            return None

        if projection_years <= 0:
            return None

        if discount_rate <= terminal_growth:
            return None

        present_value = 0.0
        fcf = base_fcf

        for year in range(1, projection_years + 1):
            fcf = fcf * (1.0 + growth_rate)
            present_value += fcf / ((1.0 + discount_rate) ** year)

        terminal_fcf = fcf * (1.0 + terminal_growth)
        terminal_value = terminal_fcf / (discount_rate - terminal_growth)
        present_value += terminal_value / ((1.0 + discount_rate) ** projection_years)

        return present_value

    def _blend(
        self,
        dcf_value: Optional[float],
        comparable_value: Optional[float],
    ) -> Optional[float]:
        if dcf_value is None:
            return comparable_value

        if comparable_value is None:
            return dcf_value

        return (dcf_value + comparable_value) / 2.0

    def _signal(self, margin_of_safety: Optional[float]) -> str:
        if margin_of_safety is None:
            return "unavailable"

        if margin_of_safety >= self.config.undervalued_threshold:
            return "undervalued"

        if margin_of_safety >= self.config.fair_threshold:
            return "fair"

        return "overvalued"

    @staticmethod
    def _text(value: Optional[float], digits: int = 4) -> str:
        return "N/A" if value is None else f"{value:.{digits}f}"
