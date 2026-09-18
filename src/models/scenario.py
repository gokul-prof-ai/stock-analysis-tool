from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

ScenarioName = Literal["bull", "base", "bear"]
ScenarioStatus = Literal["ok", "partial", "unavailable"]


class HistoricalPoint(BaseModel):
    """Historical annual metric point."""

    fiscal_year: int
    revenue: Optional[float] = None
    ebitda: Optional[float] = None
    net_profit: Optional[float] = None
    eps: Optional[float] = None


class ForecastPoint(BaseModel):
    """Forecast metric point."""

    fiscal_year: int
    value: Optional[float] = None


class MacroOverlay(BaseModel):
    """Macro assumption overlay."""

    gdp_growth: float
    interest_rate: float
    inflation: float
    sensitivity: float
    adjustment: float
    interpretation: str


class ScenarioForecast(BaseModel):
    """One bull/base/bear scenario."""

    name: ScenarioName
    growth_rate: float
    ebitda_growth_rate: float
    eps_growth_rate: float
    revenue: list[ForecastPoint] = Field(default_factory=list)
    ebitda: list[ForecastPoint] = Field(default_factory=list)
    eps: list[ForecastPoint] = Field(default_factory=list)
    target_price: Optional[float] = None
    upside_pct: Optional[float] = None
    narrative: str = ""


class ScenarioReport(BaseModel):
    """Complete scenario and forecast output."""

    ticker: Optional[str] = None
    latest_fiscal_year: Optional[int] = None

    historical: list[HistoricalPoint] = Field(default_factory=list)

    base_growth: Optional[float] = None
    growth_rates: dict[str, Optional[float]] = Field(default_factory=dict)
    macro: MacroOverlay

    scenarios: list[ScenarioForecast] = Field(default_factory=list)

    base_target_price: Optional[float] = None
    target_price_lower: Optional[float] = None
    target_price_upper: Optional[float] = None

    assumptions: list[str] = Field(default_factory=list)
    status: ScenarioStatus = "unavailable"
