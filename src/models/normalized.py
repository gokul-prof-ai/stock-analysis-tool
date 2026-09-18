from __future__ import annotations

from pydantic import BaseModel, Field

from .company import CompanyProfile
from .financials import FinancialLine
from .market import PricePoint, ShareholdingPoint


class NormalizedCompany(BaseModel):
    """Source-agnostic normalized dataset for downstream analysis."""

    company: CompanyProfile
    financials: list[FinancialLine] = []
    prices: list[PricePoint] = []
    shareholding: list[ShareholdingPoint] = []
    source_ratios: dict[str, dict[int, float]] = Field(default_factory=dict)
