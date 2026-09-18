from __future__ import annotations

import math

from ..models import PricePoint
from ..models.report import RiskMetrics


class RiskAnalyzer:
    """Price-based risk metrics: volatility, drawdown, historical VaR."""

    def analyze_prices(self, prices: list[PricePoint]) -> RiskMetrics:
        if not prices:
            return RiskMetrics(
                observation_count=0,
                interpretation="No price data available for risk analysis.",
            )

        ordered = sorted(prices, key=lambda price: price.date)
        closes = [float(price.close) for price in ordered]

        returns: list[float] = []

        for index in range(1, len(closes)):
            previous = closes[index - 1]
            current = closes[index]

            if previous > 0:
                returns.append((current / previous) - 1.0)

        if len(returns) < 2:
            return RiskMetrics(
                observation_count=len(closes),
                interpretation="Insufficient price history for risk metrics.",
            )

        mean_return = sum(returns) / len(returns)
        variance = sum((item - mean_return) ** 2 for item in returns) / len(returns)
        annualized_volatility = math.sqrt(variance) * math.sqrt(252.0)

        peak = closes[0]
        max_drawdown = 0.0

        for close in closes:
            peak = max(peak, close)

            if peak > 0:
                drawdown = (peak - close) / peak
                max_drawdown = max(max_drawdown, drawdown)

        sorted_returns = sorted(returns)
        index = max(0, min(int(0.05 * (len(sorted_returns) - 1)), len(sorted_returns) - 1))
        var_95 = -sorted_returns[index]

        return RiskMetrics(
            observation_count=len(closes),
            annualized_volatility=annualized_volatility,
            max_drawdown=max_drawdown,
            var_95=var_95,
            beta=None,
            interpretation=(
                "Risk metrics are computed from historical closing prices. "
                "Beta is unavailable unless benchmark series is provided."
            ),
        )
