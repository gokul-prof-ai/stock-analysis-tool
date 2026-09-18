from __future__ import annotations

import math
import tomllib
from pathlib import Path
from typing import Any, Optional

from ..models.ratios import BenchmarkComparison, RatioResult


class BenchmarkError(Exception):
    """Raised when benchmark configuration cannot be loaded."""


class BenchmarkProvider:
    """Provides configurable ratio benchmarks from TOML or dictionaries."""

    def __init__(self, benchmarks: dict[str, Any] | None = None) -> None:
        data = benchmarks or {}
        self._default = self._clean_map(data.get("default", {}))
        self._sectors: dict[str, dict[str, float]] = {}

        for sector, ratios in (data.get("sectors", {}) or {}).items():
            self._sectors[str(sector).lower()] = self._clean_map(ratios)

    @classmethod
    def from_toml(cls, path: str | Path) -> BenchmarkProvider:
        config_path = Path(path)

        if not config_path.exists():
            return cls({})

        try:
            payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise BenchmarkError(f"Failed to load benchmark file: {config_path}") from exc

        return cls(payload)

    def get(self, ratio_name: str, sector: Optional[str] = None) -> Optional[float]:
        if sector:
            sector_map = self._sectors.get(sector.lower())
            if sector_map and ratio_name in sector_map:
                return sector_map[ratio_name]

        return self._default.get(ratio_name)

    def compare(
        self,
        result: RatioResult,
        sector: Optional[str] = None,
    ) -> BenchmarkComparison:
        benchmark = self.get(result.name, sector)

        if result.value is None:
            return BenchmarkComparison(
                ratio_name=result.name,
                fiscal_year=result.fiscal_year,
                company_value=None,
                benchmark_value=benchmark,
                deviation=None,
                status="missing_company_value",
            )

        if benchmark is None:
            return BenchmarkComparison(
                ratio_name=result.name,
                fiscal_year=result.fiscal_year,
                company_value=result.value,
                benchmark_value=None,
                deviation=None,
                status="missing_benchmark",
            )

        return BenchmarkComparison(
            ratio_name=result.name,
            fiscal_year=result.fiscal_year,
            company_value=result.value,
            benchmark_value=benchmark,
            deviation=result.value - benchmark,
            status="ok",
        )

    @staticmethod
    def _clean_map(raw: Any) -> dict[str, float]:
        cleaned: dict[str, float] = {}

        for key, value in (raw or {}).items():
            try:
                parsed = float(value)
            except (TypeError, ValueError):
                continue

            if math.isfinite(parsed):
                cleaned[str(key)] = parsed

        return cleaned
