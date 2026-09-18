from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from ..models import PricePoint
from ..models.technical import PatternSignal, TechnicalReport


@dataclass(frozen=True)
class TechnicalConfig:
    """Technical-analysis parameters."""

    sma_fast_period: int = 20
    sma_slow_period: int = 50
    rsi_period: int = 14
    bollinger_period: int = 20
    bollinger_std: float = 2.0
    macd_fast_period: int = 12
    macd_slow_period: int = 26
    macd_signal_period: int = 9
    pivot_window: int = 5
    pattern_tolerance: float = 0.01
    max_support_levels: int = 3
    max_resistance_levels: int = 3


class TechnicalAnalyzer:
    """Computes price trends, indicators, support/resistance, and patterns."""

    def __init__(self, config: TechnicalConfig | None = None) -> None:
        self.config = config or TechnicalConfig()

    def analyze_prices(
        self,
        prices: list[PricePoint],
        ticker: str | None = None,
    ) -> TechnicalReport:
        if not prices:
            raise ValueError("No price data available")

        ordered = sorted(prices, key=lambda price: price.date)

        dates = [price.date for price in ordered]
        opens = [float(price.open) for price in ordered]
        highs = [float(price.high) for price in ordered]
        lows = [float(price.low) for price in ordered]
        closes = [float(price.close) for price in ordered]
        volumes = [int(price.volume) for price in ordered]

        sma_fast = self._rolling_sma(closes, self.config.sma_fast_period)
        sma_slow = self._rolling_sma(closes, self.config.sma_slow_period)

        bollinger_middle = self._rolling_sma(closes, self.config.bollinger_period)
        bollinger_std = self._rolling_std(closes, self.config.bollinger_period)

        bollinger_upper: list[Optional[float]] = [None] * len(closes)
        bollinger_lower: list[Optional[float]] = [None] * len(closes)

        for index, middle in enumerate(bollinger_middle):
            std = bollinger_std[index]
            if middle is not None and std is not None:
                bollinger_upper[index] = middle + self.config.bollinger_std * std
                bollinger_lower[index] = middle - self.config.bollinger_std * std

        rsi = self._rsi(closes, self.config.rsi_period)
        macd_line, macd_signal_line, macd_histogram = self._macd(closes)

        support_levels, resistance_levels = self._support_resistance(highs, lows, closes)
        patterns = self._detect_patterns(dates, closes, highs, lows, sma_fast, sma_slow)
        trend = self._trend(closes, sma_fast, sma_slow)

        return TechnicalReport(
            ticker=ticker,
            dates=dates,
            open=opens,
            high=highs,
            low=lows,
            close=closes,
            volume=volumes,
            sma_fast=sma_fast,
            sma_slow=sma_slow,
            bollinger_upper=bollinger_upper,
            bollinger_middle=bollinger_middle,
            bollinger_lower=bollinger_lower,
            rsi=rsi,
            macd_line=macd_line,
            macd_signal_line=macd_signal_line,
            macd_histogram=macd_histogram,
            latest_close=closes[-1],
            latest_rsi=rsi[-1],
            trend=trend,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            patterns=patterns,
        )

    def _rolling_sma(self, values: list[float], period: int) -> list[Optional[float]]:
        output: list[Optional[float]] = [None] * len(values)

        if period <= 0 or len(values) < period:
            return output

        window_sum = 0.0

        for index, value in enumerate(values):
            window_sum += value

            if index >= period:
                window_sum -= values[index - period]

            if index >= period - 1:
                output[index] = window_sum / period

        return output

    def _rolling_std(self, values: list[float], period: int) -> list[Optional[float]]:
        output: list[Optional[float]] = [None] * len(values)

        if period <= 0 or len(values) < period:
            return output

        for index in range(period - 1, len(values)):
            window = values[index - period + 1 : index + 1]
            mean = sum(window) / period
            variance = sum((item - mean) ** 2 for item in window) / period
            output[index] = math.sqrt(variance)

        return output

    def _ema(self, values: list[float], period: int) -> list[Optional[float]]:
        output: list[Optional[float]] = [None] * len(values)

        if period <= 0 or len(values) < period:
            return output

        seed = sum(values[:period]) / period
        output[period - 1] = seed

        multiplier = 2.0 / (period + 1.0)
        previous = seed

        for index in range(period, len(values)):
            previous = values[index] * multiplier + previous * (1.0 - multiplier)
            output[index] = previous

        return output

    def _rsi(self, values: list[float], period: int) -> list[Optional[float]]:
        output: list[Optional[float]] = [None] * len(values)

        if period <= 0 or len(values) <= period:
            return output

        gains: list[float] = []
        losses: list[float] = []

        for index in range(1, period + 1):
            change = values[index] - values[index - 1]
            gains.append(max(change, 0.0))
            losses.append(max(-change, 0.0))

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        output[period] = self._rsi_value(avg_gain, avg_loss)

        for index in range(period + 1, len(values)):
            change = values[index] - values[index - 1]
            gain = max(change, 0.0)
            loss = max(-change, 0.0)

            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period

            output[index] = self._rsi_value(avg_gain, avg_loss)

        return output

    def _rsi_value(self, avg_gain: float, avg_loss: float) -> float:
        if math.isclose(avg_loss, 0.0, abs_tol=1e-12):
            if math.isclose(avg_gain, 0.0, abs_tol=1e-12):
                return 50.0
            return 100.0

        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def _macd(self, closes: list[float]) -> tuple[list[Optional[float]], list[Optional[float]], list[Optional[float]]]:
        ema_fast = self._ema(closes, self.config.macd_fast_period)
        ema_slow = self._ema(closes, self.config.macd_slow_period)

        macd_line: list[Optional[float]] = [None] * len(closes)

        for index in range(len(closes)):
            fast = ema_fast[index]
            slow = ema_slow[index]

            if fast is not None and slow is not None:
                macd_line[index] = fast - slow

        macd_signal_line: list[Optional[float]] = [None] * len(closes)

        valid = [(index, value) for index, value in enumerate(macd_line) if value is not None]

        if len(valid) >= self.config.macd_signal_period:
            macd_values = [value for _, value in valid]
            signal_values = self._ema(macd_values, self.config.macd_signal_period)

            for (original_index, _), signal_value in zip(valid, signal_values):
                macd_signal_line[original_index] = signal_value

        macd_histogram: list[Optional[float]] = [None] * len(closes)

        for index in range(len(closes)):
            macd = macd_line[index]
            signal = macd_signal_line[index]

            if macd is not None and signal is not None:
                macd_histogram[index] = macd - signal

        return macd_line, macd_signal_line, macd_histogram

    def _trend(
        self,
        closes: list[float],
        sma_fast: list[Optional[float]],
        sma_slow: list[Optional[float]],
    ) -> str:
        latest_close = closes[-1]
        fast = sma_fast[-1]
        slow = sma_slow[-1]

        if fast is None or slow is None:
            return "insufficient_data"

        if latest_close > fast > slow:
            return "uptrend"

        if latest_close < fast < slow:
            return "downtrend"

        if latest_close > fast:
            return "short_term_bullish"

        if latest_close < fast:
            return "short_term_bearish"

        return "sideways"

    def _support_resistance(
        self,
        highs: list[float],
        lows: list[float],
        closes: list[float],
    ) -> tuple[list[float], list[float]]:
        window = self.config.pivot_window

        if len(closes) < (2 * window + 1):
            return [], []

        pivot_high_values = [value for _, value in self._pivot_indices(highs, window, "high")]
        pivot_low_values = [value for _, value in self._pivot_indices(lows, window, "low")]

        high_levels = self._cluster_levels(pivot_high_values)
        low_levels = self._cluster_levels(pivot_low_values)

        latest_close = closes[-1]

        resistance = sorted(level for level in high_levels if level > latest_close)
        support = sorted((level for level in low_levels if level < latest_close), reverse=True)

        return (
            support[: self.config.max_support_levels],
            resistance[: self.config.max_resistance_levels],
        )

    def _pivot_indices(
        self,
        values: list[float],
        window: int,
        mode: str,
    ) -> list[tuple[int, float]]:
        pivots: list[tuple[int, float]] = []

        for index in range(window, len(values) - window):
            segment = values[index - window : index + window + 1]

            if mode == "high" and values[index] >= max(segment):
                pivots.append((index, values[index]))
            elif mode == "low" and values[index] <= min(segment):
                pivots.append((index, values[index]))

        return pivots

    def _cluster_levels(self, values: list[float]) -> list[float]:
        if not values:
            return []

        sorted_values = sorted(values)
        groups: list[list[float]] = []

        for value in sorted_values:
            if not groups:
                groups.append([value])
                continue

            last_group = groups[-1]
            reference = last_group[-1]

            if math.isclose(reference, 0.0, abs_tol=1e-12):
                tolerance = self.config.pattern_tolerance
            else:
                tolerance = abs(reference) * self.config.pattern_tolerance

            if abs(value - reference) <= max(tolerance, 1e-9):
                last_group.append(value)
            else:
                groups.append([value])

        return [sum(group) / len(group) for group in groups]

    def _detect_patterns(
        self,
        dates: list[date],
        closes: list[float],
        highs: list[float],
        lows: list[float],
        sma_fast: list[Optional[float]],
        sma_slow: list[Optional[float]],
    ) -> list[PatternSignal]:
        patterns: list[PatternSignal] = []

        for index in range(1, len(closes)):
            previous_fast = sma_fast[index - 1]
            previous_slow = sma_slow[index - 1]
            current_fast = sma_fast[index]
            current_slow = sma_slow[index]

            if None in (previous_fast, previous_slow, current_fast, current_slow):
                continue

            if previous_fast <= previous_slow and current_fast > current_slow:
                patterns.append(
                    PatternSignal(
                        name="golden_cross",
                        date=dates[index],
                        direction="bullish",
                        description=(
                            f"SMA{self.config.sma_fast_period} crossed above "
                            f"SMA{self.config.sma_slow_period}."
                        ),
                    )
                )
            elif previous_fast >= previous_slow and current_fast < current_slow:
                patterns.append(
                    PatternSignal(
                        name="death_cross",
                        date=dates[index],
                        direction="bearish",
                        description=(
                            f"SMA{self.config.sma_fast_period} crossed below "
                            f"SMA{self.config.sma_slow_period}."
                        ),
                    )
                )

        patterns.extend(self._double_top_bottom(dates, closes, highs, lows))

        return patterns

    def _double_top_bottom(
        self,
        dates: list[date],
        closes: list[float],
        highs: list[float],
        lows: list[float],
    ) -> list[PatternSignal]:
        patterns: list[PatternSignal] = []
        window = self.config.pivot_window

        if len(closes) < (2 * window + 1):
            return patterns

        pivot_highs = self._pivot_indices(highs, window, "high")
        pivot_lows = self._pivot_indices(lows, window, "low")

        if len(pivot_highs) >= 2:
            first_index, first_peak = pivot_highs[-2]
            second_index, second_peak = pivot_highs[-1]

            if second_index - first_index >= window:
                tolerance = abs(second_peak) * self.config.pattern_tolerance

                if (
                    abs(first_peak - second_peak) <= max(tolerance, 1e-9)
                    and closes[-1] < second_peak * (1.0 - self.config.pattern_tolerance)
                ):
                    patterns.append(
                        PatternSignal(
                            name="double_top",
                            date=dates[second_index],
                            direction="bearish",
                            description="Two similar highs formed before price moved lower.",
                        )
                    )

        if len(pivot_lows) >= 2:
            first_index, first_trough = pivot_lows[-2]
            second_index, second_trough = pivot_lows[-1]

            if second_index - first_index >= window:
                tolerance = abs(second_trough) * self.config.pattern_tolerance

                if (
                    abs(first_trough - second_trough) <= max(tolerance, 1e-9)
                    and closes[-1] > second_trough * (1.0 + self.config.pattern_tolerance)
                ):
                    patterns.append(
                        PatternSignal(
                            name="double_bottom",
                            date=dates[second_index],
                            direction="bullish",
                            description="Two similar lows formed before price moved higher.",
                        )
                    )

        return patterns
