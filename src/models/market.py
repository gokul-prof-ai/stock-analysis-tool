from __future__ import annotations

import math
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class PricePoint(BaseModel):
    """Normalized OHLCV price row."""

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int = Field(default=0, ge=0)

    @field_validator("open", "high", "low", "close")
    @classmethod
    def _finite_price(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("price must be finite")
        return value


class ShareholdingPoint(BaseModel):
    """Normalized shareholding pattern row."""

    quarter: str = Field(min_length=1, max_length=20)
    promoter_pct: Optional[float] = Field(default=None, ge=0, le=100)
    fii_pct: Optional[float] = Field(default=None, ge=0, le=100)
    dii_pct: Optional[float] = Field(default=None, ge=0, le=100)
    public_pct: Optional[float] = Field(default=None, ge=0, le=100)

    @field_validator("quarter")
    @classmethod
    def _clean_quarter(cls, value: str) -> str:
        cleaned = " ".join(str(value).split())
        if not cleaned:
            raise ValueError("quarter cannot be empty")
        return cleaned

    @field_validator("promoter_pct", "fii_pct", "dii_pct", "public_pct")
    @classmethod
    def _finite_pct(cls, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        if not math.isfinite(value):
            raise ValueError("percentage must be finite")
        return value
