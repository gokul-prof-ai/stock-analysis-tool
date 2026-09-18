from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field, field_validator

StatementType = Literal["balance_sheet", "pnl", "cashflow"]


class FinancialLine(BaseModel):
    """One normalized financial statement line item."""

    fiscal_year: int = Field(ge=1900, le=2100)
    statement_type: StatementType
    line_item: str = Field(min_length=1, max_length=200)
    value: float

    @field_validator("line_item")
    @classmethod
    def _clean_line_item(cls, value: str) -> str:
        cleaned = " ".join(str(value).split())
        if not cleaned:
            raise ValueError("line_item cannot be empty")
        return cleaned

    @field_validator("value")
    @classmethod
    def _finite_value(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("value must be finite")
        return value
