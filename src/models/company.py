from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

DataSourceType = Literal["screener", "file_upload"]


class CompanyProfile(BaseModel):
    """Normalized company identity."""

    ticker: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    sector: Optional[str] = None
    industry: Optional[str] = None

    @field_validator("ticker", "name", "sector", "industry")
    @classmethod
    def _strip_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = " ".join(str(value).split())
        return cleaned or None
