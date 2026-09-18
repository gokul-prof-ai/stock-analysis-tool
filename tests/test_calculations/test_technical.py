from datetime import date, timedelta
from pathlib import Path

import pytest

from src.calculations.technical import TechnicalAnalyzer, TechnicalConfig
from src.calculations.technical_charts import TechnicalChartGenerator
from src.models import PricePoint


def _prices(values: list[float]) -> list[PricePoint]:
    start = date(2023, 1, 2)
    prices: list[PricePoint] = []

    for index, value in enumerate(values):
        day = start + timedelta(days=index)
        prices.append(
            PricePoint(
                date=day,
                open=float(value),
                high=float(value) + 1.0,
                low=max(float(value) - 1.0, 0.01),
                close=float(value),
                volume=100,
            )
        )

    return prices


def _small_config() -> TechnicalConfig:
    return TechnicalConfig(
        sma_fast_period=3,
        sma_slow_period=5,
        rsi_period=2,
        bollinger_period=3,
        bollinger_std=2.0,
        macd_fast_period=3,
        macd_slow_period=5,
        macd_signal_period=3,
        pivot_window=2,
    )


def test_sma_and_ema():
    analyzer = TechnicalAnalyzer()

    sma = analyzer._rolling_sma([1.0, 2.0, 3.0, 4.0, 5.0], 3)

    assert sma[0] is None
    assert sma[1] is None
    assert sma[2] == pytest.approx(2.0)
    assert sma[3] == pytest.approx(3.0)
    assert sma[4] == pytest.approx(4.0)

    ema = analyzer._ema([1.0, 2.0, 3.0, 4.0, 5.0], 3)

    assert ema[2] == pytest.approx(2.0)
    assert ema[3] == pytest.approx(3.0)
    assert ema[4] == pytest.approx(4.0)


def test_rsi_wilder():
    analyzer = TechnicalAnalyzer()

    rsi = analyzer._rsi([1.0, 2.0, 3.0, 2.0, 3.0, 4.0], 2)

    assert rsi[0] is None
    assert rsi[1] is None
    assert rsi[2] == pytest.approx(100.0)
    assert rsi[3] == pytest.approx(50.0)
    assert rsi[4] == pytest.approx(75.0)
    assert rsi[5] == pytest.approx(87.5)


def test_bollinger_bands():
    analyzer = TechnicalAnalyzer()

    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    middle = analyzer._rolling_sma(values, 3)
    std = analyzer._rolling_std(values, 3)

    upper = middle[2] + 2.0 * std[2]
    lower = middle[2] - 2.0 * std[2]

    assert middle[2] == pytest.approx(2.0)
    assert upper == pytest.approx(3.632993)
    assert lower == pytest.approx(0.367007)


def test_macd_alignment():
    analyzer = TechnicalAnalyzer(
        TechnicalConfig(
            macd_fast_period=3,
            macd_slow_period=5,
            macd_signal_period=3,
        )
    )

    values = [float(value) for value in range(1, 21)]
    macd, signal, histogram = analyzer._macd(values)

    fast = analyzer._ema(values, 3)
    slow = analyzer._ema(values, 5)

    for index in range(len(values)):
        if macd[index] is not None:
            assert macd[index] == pytest.approx(fast[index] - slow[index])

    assert any(value is not None for value in signal)


def test_golden_cross_pattern():
    analyzer = TechnicalAnalyzer(
        TechnicalConfig(
            sma_fast_period=3,
            sma_slow_period=5,
            pivot_window=2,
        )
    )

    values = [10.0] * 6 + [12.0, 14.0, 16.0, 18.0]
    report = analyzer.analyze_prices(_prices(values), ticker="TEST")

    names = [pattern.name for pattern in report.patterns]

    assert "golden_cross" in names


def test_report_and_support_resistance():
    analyzer = TechnicalAnalyzer(_small_config())

    values = [100.0, 105.0, 110.0, 105.0, 100.0, 95.0, 90.0, 95.0, 100.0, 105.0, 110.0]
    report = analyzer.analyze_prices(_prices(values), ticker="TEST")

    assert report.latest_close == pytest.approx(110.0)
    assert isinstance(report.support_levels, list)
    assert isinstance(report.resistance_levels, list)
    assert report.trend != ""


def test_chart_exports(tmp_path):
    analyzer = TechnicalAnalyzer(_small_config())

    values = [100.0 + float(index) + float(index % 3) for index in range(20)]
    report = analyzer.analyze_prices(_prices(values), ticker="TEST")

    generator = TechnicalChartGenerator(report)
    paths = generator.generate_all(tmp_path)

    assert len(paths) == 5

    for chart_path in paths.values():
        assert Path(chart_path).exists()
        assert Path(chart_path).stat().st_size > 0
