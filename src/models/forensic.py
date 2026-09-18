from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

ForensicStatus = Literal["ok", "partial", "unavailable"]
RiskSeverity = Literal["info", "warning", "high"]
AltmanZone = Literal["safe", "grey", "distress", "not_available"]


class AltmanResult(BaseModel):
    """Altman Z-Score result."""

    z_score: Optional[float] = None
    zone: AltmanZone = "not_available"
    inputs: dict[str, Optional[float]] = Field(default_factory=dict)
    formula: str = ""
    interpretation: str = ""


class BeneishResult(BaseModel):
    """Beneish M-Score result."""

    m_score: Optional[float] = None
    variables: dict[str, Optional[float]] = Field(default_factory=dict)
    likely_manipulator: Optional[bool] = None
    formula: str = ""
    interpretation: str = ""


class PiotroskiResult(BaseModel):
    """Piotroski F-Score result."""

    score: Optional[int] = Field(default=None, ge=0, le=9)
    signals: dict[str, bool] = Field(default_factory=dict)
    formula: str = ""
    interpretation: str = ""


class BenfordResult(BaseModel):
    """Benford's Law digit-distribution result."""

    observation_count: int = 0
    chi_square: Optional[float] = None
    critical_value: float = 15.507
    suspicious: Optional[bool] = None
    distribution: dict[int, float] = Field(default_factory=dict)
    formula: str = ""
    interpretation: str = ""


class RedFlag(BaseModel):
    """Forensic red flag explanation."""

    code: str
    severity: RiskSeverity
    message: str


class ForensicReport(BaseModel):
    """Complete forensic analysis output."""

    fiscal_year: int
    altman: AltmanResult
    beneish: BeneishResult
    piotroski: PiotroskiResult
    benford: BenfordResult
    fraud_probability: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    red_flags: list[RedFlag] = Field(default_factory=list)
    status: ForensicStatus = "unavailable"
