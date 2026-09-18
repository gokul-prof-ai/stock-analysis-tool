from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

PatternDirection = Literal["bullish", "bearish", "neutral"]


class PatternSignal(BaseModel):
    """Detected technical pattern."""

    name: str
    date: date
    direction: PatternDirection
    description: str


class TechnicalReport(BaseModel):
    """Complete technical-analysis output."""

    ticker: Optional[str] = None

    dates: list[date] = Field(default_factory=list)
    open: list[float] = Field(default_factory=list)
    high: list[float] = Field(default_factory=list)
    low: list[float] = Field(default_factory=list)
    close: list[float] = Field(default_factory=list)
    volume: list[int] = Field(default_factory=list)

    sma_fast: list[Optional[float]] = Field(default_factory=list)
    sma_slow: list[Optional[float]] = Field(default_factory=list)

    bollinger_upper: list[Optional[float]] = Field(default_factory=list)
    bollinger_middle: list[Optional[float]] = Field(default_factory=list)
    bollinger_lower: list[Optional[float]] = Field(default_factory=list)

    rsi: list[Optional[float]] = Field(default_factory=list)

    macd_line: list[Optional[float]] = Field(default_factory=list)
    macd_signal_line: list[Optional[float]] = Field(default_factory=list)
    macd_histogram: list[Optional[float]] = Field(default_factory=list)

    latest_close: Optional[float] = None
    latest_rsi: Optional[float] = None
    trend: str = "insufficient_data"

    support_levels: list[float] = Field(default_factory=list)
    resistance_levels: list[float] = Field(default_factory=list)
    patterns: list[PatternSignal] = Field(default_factory=list)
