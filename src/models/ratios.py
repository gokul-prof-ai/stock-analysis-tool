from __future__ import annotations

import math
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

RatioCategory = Literal["liquidity", "solvency", "profitability", "efficiency", "market"]
RatioStatus = Literal["ok", "missing_inputs", "division_by_zero", "not_meaningful", "source_provided"]
BenchmarkStatus = Literal["ok", "missing_company_value", "missing_benchmark"]


class RatioResult(BaseModel):
    """One auditable financial ratio result."""

    name: str
    category: RatioCategory
    fiscal_year: int
    value: Optional[float]
    formula: str
    interpretation: str
    inputs: dict[str, Optional[float]] = Field(default_factory=dict)
    status: RatioStatus = "ok"

    @field_validator("value")
    @classmethod
    def _finite_value(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and not math.isfinite(value):
            raise ValueError("value must be finite")
        return value


class RatioSet(BaseModel):
    """All ratios for one fiscal year."""

    fiscal_year: int
    ratios: list[RatioResult]

    def get(self, name: str) -> Optional[RatioResult]:
        return next((ratio for ratio in self.ratios if ratio.name == name), None)


class BenchmarkComparison(BaseModel):
    """Company ratio compared against a benchmark."""

    ratio_name: str
    fiscal_year: int
    company_value: Optional[float]
    benchmark_value: Optional[float]
    deviation: Optional[float]
    status: BenchmarkStatus

    @field_validator("company_value", "benchmark_value", "deviation")
    @classmethod
    def _finite_value(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and not math.isfinite(value):
            raise ValueError("value must be finite")
        return value
