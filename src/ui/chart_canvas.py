from __future__ import annotations

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle


class TradingViewChartCanvas(FigureCanvasQTAgg):
    """TradingView-style dark candlestick chart with volume, RSI and MACD panes."""

    BG = "#131722"
    GRID = "#2a2e39"
    TEXT = "#9598a1"
    UP = "#089981"
    DOWN = "#f23645"
    ACCENT = "#2962ff"

    def __init__(self, report, ticker: str, parent=None) -> None:
        self.fig = Figure(figsize=(11, 7), dpi=100, facecolor=self.BG)
        super().__init__(self.fig)
        self.setParent(parent)
        self.report = report
        self.ticker = ticker
        self.max_rows: int | None = None
        self.draw_chart()

    def set_range(self, max_rows: int | None) -> None:
        self.max_rows = max_rows
        self.draw_chart()

    def _slice(self, values: list) -> list:
        if self.max_rows is None:
            return list(values)
        return list(values)[-self.max_rows :]

    def _style(self, axis) -> None:
        axis.set_facecolor(self.BG)
        axis.tick_params(colors=self.TEXT, labelsize=8)
        axis.grid(True, color=self.GRID, alpha=0.6, linewidth=0.6)
        for spine in axis.spines.values():
            spine.set_color(self.GRID)

    def draw_chart(self) -> None:
        self.fig.clear()

        dates = self._slice(self.report.dates)
        opens = self._slice(self.report.open)
        highs = self._slice(self.report.high)
        lows = self._slice(self.report.low)
        closes = self._slice(self.report.close)
        volumes = self._slice(self.report.volume)
        sma_fast = self._slice(self.report.sma_fast)
        sma_slow = self._slice(self.report.sma_slow)
        bollinger_upper = self._slice(self.report.bollinger_upper)
        bollinger_lower = self._slice(self.report.bollinger_lower)
        rsi = self._slice(self.report.rsi)
        macd = self._slice(self.report.macd_line)
        signal = self._slice(self.report.macd_signal_line)
        hist = self._slice(self.report.macd_histogram)

        grid = self.fig.add_gridspec(
            4, 1,
            height_ratios=[3, 1, 1, 1],
            hspace=0.08,
            left=0.07, right=0.95, top=0.94, bottom=0.07,
        )

        ax_c = self.fig.add_subplot(grid[0])
        ax_v = self.fig.add_subplot(grid[1], sharex=ax_c)
        ax_r = self.fig.add_subplot(grid[2], sharex=ax_c)
        ax_m = self.fig.add_subplot(grid[3], sharex=ax_c)

        for axis in (ax_c, ax_v, ax_r, ax_m):
            self._style(axis)

        for index in range(len(closes)):
            color = self.UP if closes[index] >= opens[index] else self.DOWN
            ax_c.vlines(index, lows[index], highs[index], color=color, linewidth=0.8)
            body = max(abs(closes[index] - opens[index]), 1e-9)
            ax_c.add_patch(
                Rectangle((index - 0.32, min(opens[index], closes[index])), 0.64, body,
                          facecolor=color, edgecolor=color)
            )
            ax_v.bar(index, volumes[index], color=color, width=0.64)

        for values, label, color in (
            (sma_fast, "SMA 20", "#f5a623"),
            (sma_slow, "SMA 50", "#42a5f5"),
        ):
            value_x = [index for index, value in enumerate(values) if value is not None]
            value_y = [value for value in values if value is not None]
            if value_x:
                ax_c.plot(value_x, value_y, color=color, linewidth=1.0, label=label)

        band_x = [
            index
            for index, (upper, lower) in enumerate(zip(bollinger_upper, bollinger_lower))
            if upper is not None and lower is not None
        ]
        if band_x:
            upper = [bollinger_upper[index] for index in band_x]
            lower = [bollinger_lower[index] for index in band_x]
            ax_c.fill_between(band_x, lower, upper, color=self.ACCENT, alpha=0.08, label="Bollinger")

        if len(closes) > 1:
            ax_c.legend(loc="upper left", fontsize=7, frameon=False, labelcolor=self.TEXT)

        ax_c.text(0.01, 0.95, f"{self.ticker} · candles · vol · RSI · MACD",
                  transform=ax_c.transAxes, color=self.TEXT, fontsize=9, alpha=0.85)

        rsi_x = [i for i, v in enumerate(rsi) if v is not None]
        rsi_y = [v for v in rsi if v is not None]
        if rsi_x:
            ax_r.plot(rsi_x, rsi_y, color="#b26eea", linewidth=1.1)
        ax_r.axhline(70, color=self.DOWN, linewidth=0.7, linestyle="--")
        ax_r.axhline(30, color=self.UP, linewidth=0.7, linestyle="--")
        ax_r.set_ylim(0, 100)
        ax_r.text(0.01, 0.85, "RSI 14", transform=ax_r.transAxes, color=self.TEXT, fontsize=8)

        macd_x = [i for i, v in enumerate(macd) if v is not None]
        macd_y = [v for v in macd if v is not None]
        sig_x = [i for i, v in enumerate(signal) if v is not None]
        sig_y = [v for v in signal if v is not None]
        hist_x = [i for i, v in enumerate(hist) if v is not None]
        hist_y = [v for v in hist if v is not None]

        if macd_x:
            ax_m.plot(macd_x, macd_y, color=self.ACCENT, linewidth=1.1)
        if sig_x:
            ax_m.plot(sig_x, sig_y, color="#ff9800", linewidth=1.0)
        if hist_x:
            colors = [self.UP if v >= 0 else self.DOWN for v in hist_y]
            ax_m.bar(hist_x, hist_y, color=colors, width=0.6)
        ax_m.text(0.01, 0.85, "MACD 12/26/9", transform=ax_m.transAxes, color=self.TEXT, fontsize=8)

        step = max(1, len(dates) // 6)
        ticks = list(range(0, len(dates), step))
        ax_m.set_xticks(ticks)
        ax_m.set_xticklabels([str(dates[i])[:10] for i in ticks], rotation=0, fontsize=8)

        for axis in (ax_c, ax_v, ax_r):
            plt_set = axis.get_xticklabels()
            for label in plt_set:
                label.set_visible(False)

        ax_c.set_xlim(-1, max(len(closes), 1))
        self.draw_idle()
