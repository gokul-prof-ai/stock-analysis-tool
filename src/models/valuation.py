from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

ValuationStatus = Literal["ok", "partial", "unavailable"]
ValuationSignal = Literal["undervalued", "fair", "overvalued", "unavailable"]
ScenarioName = Literal["bull", "base", "bear"]


class MultiplesResult(BaseModel):
    """Relative valuation multiples."""

    pe: Optional[float] = None
    pb: Optional[float] = None
    ps: Optional[float] = None
    ev_ebitda: Optional[float] = None
    enterprise_value: Optional[float] = None
    market_cap: Optional[float] = None
    inputs: dict[str, Optional[float]] = Field(default_factory=dict)
    interpretation: str = ""


class DCFScenarioResult(BaseModel):
    """One DCF scenario."""

    name: ScenarioName
    growth_rate: float
    enterprise_value: Optional[float] = None
    equity_value: Optional[float] = None
    intrinsic_per_share: Optional[float] = None
    formula: str = ""
    interpretation: str = ""


class DCFResult(BaseModel):
    """Discounted cash flow result."""

    base_fcf: Optional[float] = None
    discount_rate: float
    terminal_growth: float
    projection_years: int
    assumptions: list[str] = Field(default_factory=list)
    scenarios: list[DCFScenarioResult] = Field(default_factory=list)
    base_intrinsic_per_share: Optional[float] = None


class SensitivityResult(BaseModel):
    """DCF sensitivity matrix."""

    wacc_values: list[float] = Field(default_factory=list)
    terminal_growth_values: list[float] = Field(default_factory=list)
    matrix: list[list[Optional[float]]] = Field(default_factory=list)
    interpretation: str = ""


class ComparableMetricResult(BaseModel):
    """One comparable-company multiple and implied value."""

    name: str
    target_multiple: Optional[float] = None
    median_multiple: Optional[float] = None
    implied_value: Optional[float] = None
    peer_count: int = 0


class ComparableResult(BaseModel):
    """Comparable-company valuation result."""

    peer_tickers: list[str] = Field(default_factory=list)
    metrics: list[ComparableMetricResult] = Field(default_factory=list)
    median_implied_value: Optional[float] = None
    interpretation: str = ""


class ScenarioValuation(BaseModel):
    """Blended scenario valuation."""

    name: ScenarioName
    growth_rate: float
    dcf_intrinsic: Optional[float] = None
    comparable_intrinsic: Optional[float] = None
    final_intrinsic: Optional[float] = None


class ValuationReport(BaseModel):
    """Complete valuation output."""

    ticker: Optional[str] = None
    fiscal_year: Optional[int] = None
    price: Optional[float] = None

    multiples: MultiplesResult
    dcf: DCFResult
    comparable: ComparableResult
    sensitivity: SensitivityResult
    scenarios: list[ScenarioValuation] = Field(default_factory=list)

    intrinsic_value: Optional[float] = None
    margin_of_safety: Optional[float] = None
    valuation_signal: ValuationSignal = "unavailable"
    assumptions: list[str] = Field(default_factory=list)
    status: ValuationStatus = "unavailable"
