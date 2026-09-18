import pytest

from src.calculations.benchmarks import BenchmarkProvider
from src.models.ratios import RatioResult


def test_benchmark_lookup_and_comparison():
    provider = BenchmarkProvider(
        {
            "default": {"current_ratio": 1.0},
            "sectors": {"logistics": {"current_ratio": 1.5}},
        }
    )

    assert provider.get("current_ratio", "logistics") == 1.5
    assert provider.get("current_ratio", "unknown") == 1.0

    result = RatioResult(
        name="current_ratio",
        category="liquidity",
        fiscal_year=2023,
        value=1.2,
        formula="current_assets / current_liabilities",
        interpretation="test",
    )

    comparison = provider.compare(result, sector="logistics")

    assert comparison.deviation == pytest.approx(-0.3)
    assert comparison.status == "ok"


def test_benchmark_from_toml(tmp_path):
    path = tmp_path / "benchmarks.toml"
    path.write_text(
        "[default]\n"
        "current_ratio = 1.25\n"
        "\n"
        "[sectors.logistics]\n"
        "current_ratio = 1.75\n",
        encoding="utf-8",
    )

    provider = BenchmarkProvider.from_toml(path)

    assert provider.get("current_ratio") == 1.25
    assert provider.get("current_ratio", "LOGISTICS") == 1.75
