from pathlib import Path

import pytest

from src.calculations.financial_extractor import FinancialSnapshot
from src.calculations.forensic import ForensicAnalyzer
from src.calculations.forensic_repository import ForensicRepository
from src.database import get_connection, init_db, store_normalized
from src.ingestion.json_parser import JSONParser
from src.ingestion.normalizer import DataNormalizer

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def _load_company(filename: str):
    extract = JSONParser().load(FIXTURE_DIR / filename)
    return DataNormalizer().normalize(extract)


def test_altman_zones():
    analyzer = ForensicAnalyzer()

    healthy = FinancialSnapshot(
        fiscal_year=2023,
        values={
            "current_assets": 120.0,
            "current_liabilities": 100.0,
            "retained_earnings": 50.0,
            "ebit": 250.0,
            "total_assets": 500.0,
            "total_liabilities": 300.0,
            "revenue": 1000.0,
        },
    )

    healthy_result = analyzer.calculate_altman(healthy, market_cap=1000.0)

    assert healthy_result.z_score == pytest.approx(5.838)
    assert healthy_result.zone == "safe"

    distress = FinancialSnapshot(
        fiscal_year=2023,
        values={
            "current_assets": 80.0,
            "current_liabilities": 100.0,
            "retained_earnings": -50.0,
            "ebit": -100.0,
            "total_assets": 500.0,
            "total_liabilities": 500.0,
            "revenue": 200.0,
        },
    )

    distress_result = analyzer.calculate_altman(distress, market_cap=10.0)

    assert distress_result.z_score == pytest.approx(-0.436)
    assert distress_result.zone == "distress"


def test_beneish_manipulation_signal():
    analyzer = ForensicAnalyzer()

    current = FinancialSnapshot(
        fiscal_year=2023,
        values={
            "receivables": 200.0,
            "revenue": 1000.0,
            "gross_profit": 100.0,
            "total_assets": 2000.0,
            "fixed_assets": 100.0,
            "current_assets": 100.0,
            "short_term_investments": 0.0,
            "depreciation_amortization": 10.0,
            "operating_expenses": 300.0,
            "net_profit": 200.0,
            "operating_cash_flow": -100.0,
            "total_liabilities": 1500.0,
        },
    )

    prior = FinancialSnapshot(
        fiscal_year=2022,
        values={
            "receivables": 50.0,
            "revenue": 500.0,
            "gross_profit": 200.0,
            "total_assets": 1000.0,
            "fixed_assets": 100.0,
            "current_assets": 300.0,
            "short_term_investments": 0.0,
            "depreciation_amortization": 100.0,
            "operating_expenses": 100.0,
            "total_liabilities": 400.0,
        },
    )

    result = analyzer.calculate_beneish(current, prior)

    assert result.m_score is not None
    assert result.m_score == pytest.approx(2.481225)
    assert result.likely_manipulator is True


def test_piotroski_perfect_score():
    analyzer = ForensicAnalyzer()

    current = FinancialSnapshot(
        fiscal_year=2023,
        values={
            "net_profit": 100.0,
            "total_assets": 1000.0,
            "operating_cash_flow": 120.0,
            "long_term_debt": 100.0,
            "current_assets": 200.0,
            "current_liabilities": 100.0,
            "shares_outstanding": 100.0,
            "gross_profit": 400.0,
            "revenue": 1000.0,
        },
    )

    prior = FinancialSnapshot(
        fiscal_year=2022,
        values={
            "net_profit": 50.0,
            "total_assets": 900.0,
            "long_term_debt": 150.0,
            "current_assets": 150.0,
            "current_liabilities": 100.0,
            "shares_outstanding": 100.0,
            "gross_profit": 300.0,
            "revenue": 800.0,
        },
    )

    result = analyzer.calculate_piotroski(current, prior)

    assert result.score == 9
    assert all(result.signals.values())


def test_benford_suspicious_and_insufficient():
    analyzer = ForensicAnalyzer()

    suspicious = analyzer.calculate_benford([9.0] * 20)

    assert suspicious.chi_square is not None
    assert suspicious.chi_square > analyzer.config.benford_critical
    assert suspicious.suspicious is True

    insufficient = analyzer.calculate_benford([1.0, 2.0])

    assert insufficient.observation_count == 2
    assert insufficient.chi_square is None
    assert insufficient.suspicious is None


def test_full_forensic_healthy():
    company = _load_company("forensic_healthy.json")
    report = ForensicAnalyzer().analyze(company)

    assert report.status == "ok"
    assert report.altman.zone == "safe"
    assert report.beneish.likely_manipulator is False
    assert report.piotroski.score == 9
    assert report.fraud_probability == pytest.approx(0.0)
    assert report.red_flags == []


def test_full_forensic_distress():
    company = _load_company("forensic_distress.json")
    report = ForensicAnalyzer().analyze(company)

    codes = {flag.code for flag in report.red_flags}

    assert report.status == "ok"
    assert report.altman.zone == "distress"
    assert report.beneish.likely_manipulator is True
    assert report.piotroski.score == 1
    assert report.fraud_probability == pytest.approx(80.0)
    assert {"ALTMAN_DISTRESS", "BENEISH_MANIPULATION", "PIOTROVSKI_WEAK"} <= codes


def test_forensic_repository(tmp_path, sample_company):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)

    company_id = store_normalized(
        conn,
        sample_company,
        source="file_upload",
        source_file="full_sample.json",
    )

    report = ForensicAnalyzer().analyze(sample_company)
    repository = ForensicRepository(conn)
    row_id = repository.store_report(company_id, report)

    assert row_id > 0

    row = conn.execute(
        "SELECT COUNT(*) AS count FROM forensic_scores WHERE company_id = ?",
        (company_id,),
    ).fetchone()

    assert row["count"] == 1
    conn.close()
