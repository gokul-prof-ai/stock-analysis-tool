from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Recommendation = Literal["buy", "hold", "avoid", "unavailable"]
ChecklistStatus = Literal["covered", "partial", "not_covered"]
ReportStatus = Literal["complete", "partial", "unavailable"]


class InvestmentDecision(BaseModel):
    """Final investment decision output."""

    recommendation: Recommendation = "unavailable"
    score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    rationale: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)


class ChecklistItem(BaseModel):
    """One mapped checklist item."""

    item_id: str
    section: str
    description: str
    module: str
    status: ChecklistStatus = "not_covered"


class ReportTable(BaseModel):
    """Generic report table."""

    title: str
    headers: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)


class ReportSection(BaseModel):
    """One report section."""

    title: str
    summary: str = ""
    bullets: list[str] = Field(default_factory=list)
    tables: list[ReportTable] = Field(default_factory=list)


class RiskMetrics(BaseModel):
    """Price-based risk metrics."""

    observation_count: int = 0
    annualized_volatility: Optional[float] = None
    max_drawdown: Optional[float] = None
    var_95: Optional[float] = None
    beta: Optional[float] = None
    interpretation: str = ""


class FinalReport(BaseModel):
    """Complete capstone report model."""

    ticker: Optional[str] = None
    company_name: Optional[str] = None
    sector: Optional[str] = None
    generated_at: datetime

    executive_summary: list[str] = Field(default_factory=list)
    sections: list[ReportSection] = Field(default_factory=list)
    checklist: list[ChecklistItem] = Field(default_factory=list)
    investment_decision: InvestmentDecision
    chart_paths: dict[str, str] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    status: ReportStatus = "partial"
