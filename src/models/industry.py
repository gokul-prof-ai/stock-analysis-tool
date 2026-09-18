from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

IndustryStatus = Literal["ok", "partial", "unavailable"]
PositionClassification = Literal["leader", "strong", "average", "laggard", "unavailable"]


class PeerCompany(BaseModel):
    """Selected peer company."""

    ticker: str
    name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    size_metric: Optional[float] = None
    similarity_score: float = 0.0


class PercentileRanking(BaseModel):
    """Target-company percentile ranking for one ratio."""

    ratio_name: str
    company_value: Optional[float] = None
    peer_count: int = 0
    percentile: Optional[float] = None
    peer_min: Optional[float] = None
    peer_median: Optional[float] = None
    peer_max: Optional[float] = None
    higher_is_better: bool = True


class PorterForceScore(BaseModel):
    """One Porter force score."""

    force: str
    score: int = Field(ge=1, le=5)
    interpretation: str
    inputs: dict[str, Optional[float]] = Field(default_factory=dict)


class PorterFiveForcesResult(BaseModel):
    """Porter's Five Forces result."""

    forces: list[PorterForceScore] = Field(default_factory=list)
    overall_score: Optional[float] = None
    interpretation: str = ""


class CompetitivePosition(BaseModel):
    """Composite competitive position against peers."""

    composite_score: Optional[float] = None
    classification: PositionClassification = "unavailable"
    adjusted_percentiles: dict[str, Optional[float]] = Field(default_factory=dict)


class IndustryReport(BaseModel):
    """Complete industry and peer analysis output."""

    target_ticker: str
    fiscal_year: Optional[int] = None
    peers: list[PeerCompany] = Field(default_factory=list)
    peer_metrics: dict[str, dict[str, Optional[float]]] = Field(default_factory=dict)
    rankings: list[PercentileRanking] = Field(default_factory=list)
    porter: PorterFiveForcesResult
    position: CompetitivePosition
    status: IndustryStatus = "unavailable"
