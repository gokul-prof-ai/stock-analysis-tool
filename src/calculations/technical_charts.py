from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from ..models.technical import TechnicalReport


class TechnicalChartGenerator:
    """Exports the five M5 chart types as PNG files."""

    def __init__(self, report: TechnicalReport) -> None:
        self.report = report

    def generate_all(self, output_dir: str | Path) -> dict[str, Path]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        paths = {
            "candlestick": output_path / "candlestick.png",
            "line": output_path / "line.png",
            "volume": output_path / "volume.png",
            "indicators": output_path / "indicators.png",
            "patterns": output_path / "patterns.png",
        }

        self.candlestick(paths["candlestick"])
        self.line(paths["line"])
        self.volume(paths["volume"])
        self.indicators(paths["indicators"])
        self.patterns(paths["patterns"])

        return paths

    def candlestick(self, path: str | Path) -> None:
        report = self.report
        figure, axis = plt.subplots(figsize=(12, 6))

        for index in range(len(report.close)):
            open_price = report.open[index]
            close_price = report.close[index]
            high_price = report.high[index]
            low_price = report.low[index]

            color = "#26a69a" if close_price >= open_price else "#ef5350"

            axis.vlines(index, low_price, high_price, color=color, linewidth=1.0)

            body_height = abs(close_price - open_price)
            body_bottom = min(open_price, close_price)

            if body_height < 1e-9:
                body_height = max(abs(close_price) * 0.001, 0.01)

            axis.add_patch(
                Rectangle(
                    (index - 0.3, body_bottom),
                    0.6,
                    body_height,
                    facecolor=color,
                    edgecolor=color,
                )
            )

        self._format_x_axis(axis)

        min_low = min(report.low)
        max_high = max(report.high)
        padding = (max_high - min_low) * 0.05

        if padding <= 0:
            padding = max(abs(max_high) * 0.01, 1.0)

        axis.set_ylim(min_low - padding, max_high + padding)
        axis.set_title("Candlestick Chart")
        axis.set_ylabel("Price")

        self._save(figure, path)

    def line(self, path: str | Path) -> None:
        report = self.report
        figure, axis = plt.subplots(figsize=(12, 6))

        axis.plot(range(len(report.close)), report.close, color="#1976d2", linewidth=1.5)

        self._format_x_axis(axis)
        axis.set_title("Line Chart")
        axis.set_ylabel("Close")

        self._save(figure, path)

    def volume(self, path: str | Path) -> None:
        report = self.report
        figure, axis = plt.subplots(figsize=(12, 4))

        colors = [
            "#26a69a" if report.close[index] >= report.open[index] else "#ef5350"
            for index in range(len(report.close))
        ]

        axis.bar(range(len(report.volume)), report.volume, color=colors, width=0.6)

        self._format_x_axis(axis)
        axis.set_title("Volume Chart")
        axis.set_ylabel("Volume")

        self._save(figure, path)

    def indicators(self, path: str | Path) -> None:
        report = self.report
        figure, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

        price_axis, rsi_axis, macd_axis = axes

        close_x, close_y = self._clean_xy(report.close)
        price_axis.plot(close_x, close_y, label="Close", color="#1976d2", linewidth=1.4)

        for values, label, color in [
            (report.sma_fast, "SMA Fast", "#fb8c00"),
            (report.sma_slow, "SMA Slow", "#8e24aa"),
        ]:
            x, y = self._clean_xy(values)
            if x:
                price_axis.plot(x, y, label=label, color=color, linewidth=1.1)

        bollinger_x: list[int] = []
        bollinger_upper: list[float] = []
        bollinger_lower: list[float] = []

        for index in range(len(report.close)):
            upper = report.bollinger_upper[index]
            lower = report.bollinger_lower[index]

            if upper is not None and lower is not None:
                bollinger_x.append(index)
                bollinger_upper.append(upper)
                bollinger_lower.append(lower)

        if bollinger_x:
            price_axis.fill_between(
                bollinger_x,
                bollinger_lower,
                bollinger_upper,
                color="#90caf9",
                alpha=0.25,
                label="Bollinger Bands",
            )

        price_axis.legend(loc="upper left")
        price_axis.set_title("Price Indicators")
        price_axis.set_ylabel("Price")

        rsi_x, rsi_y = self._clean_xy(report.rsi)
        if rsi_x:
            rsi_axis.plot(rsi_x, rsi_y, color="#7b1fa2", linewidth=1.2)

        rsi_axis.axhline(70, color="red", linestyle="--", linewidth=0.8)
        rsi_axis.axhline(30, color="green", linestyle="--", linewidth=0.8)
        rsi_axis.set_ylim(0, 100)
        rsi_axis.set_title("RSI")

        macd_x, macd_y = self._clean_xy(report.macd_line)
        signal_x, signal_y = self._clean_xy(report.macd_signal_line)
        histogram_x, histogram_y = self._clean_xy(report.macd_histogram)

        if macd_x:
            macd_axis.plot(macd_x, macd_y, label="MACD", color="#1976d2")
        if signal_x:
            macd_axis.plot(signal_x, signal_y, label="Signal", color="#fb8c00")
        if histogram_x:
            macd_axis.bar(histogram_x, histogram_y, color="#9e9e9e", width=0.6, label="Histogram")

        macd_axis.legend(loc="upper left")
        macd_axis.set_title("MACD")

        self._format_x_axis(macd_axis)
        self._save(figure, path)

    def patterns(self, path: str | Path) -> None:
        report = self.report
        figure, axis = plt.subplots(figsize=(12, 6))

        close_x, close_y = self._clean_xy(report.close)
        axis.plot(close_x, close_y, color="#1976d2", linewidth=1.3, label="Close")

        for level in report.support_levels:
            axis.axhline(level, color="green", linestyle="--", linewidth=0.9, alpha=0.75)

        for level in report.resistance_levels:
            axis.axhline(level, color="red", linestyle="--", linewidth=0.9, alpha=0.75)

        date_index = {report.dates[index]: index for index in range(len(report.dates))}

        for pattern in report.patterns:
            index = date_index.get(pattern.date)

            if index is None:
                continue

            if pattern.direction == "bullish":
                marker = "^"
                color = "green"
            elif pattern.direction == "bearish":
                marker = "v"
                color = "red"
            else:
                marker = "o"
                color = "blue"

            axis.scatter(index, report.close[index], marker=marker, s=90, color=color, zorder=5)

        self._format_x_axis(axis)
        axis.set_title("Patterns, Support, and Resistance")
        axis.set_ylabel("Price")
        axis.legend(loc="upper left")

        self._save(figure, path)

    def _clean_xy(self, values: list[Optional[float]]) -> tuple[list[int], list[float]]:
        x: list[int] = []
        y: list[float] = []

        for index, value in enumerate(values):
            if value is not None and math.isfinite(value):
                x.append(index)
                y.append(value)

        return x, y

    def _format_x_axis(self, axis) -> None:
        dates = self.report.dates
        step = max(1, len(dates) // 8)
        ticks = list(range(0, len(dates), step))

        axis.set_xticks(ticks)
        axis.set_xticklabels([dates[index].isoformat() for index in ticks], rotation=30, ha="right")
        axis.grid(True, alpha=0.3)

    def _save(self, figure, path: str | Path) -> None:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output_path, dpi=120, bbox_inches="tight")
        plt.close(figure)
