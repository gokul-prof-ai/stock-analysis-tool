from src.calculations.financial_extractor import FinancialExtractor


def test_alias_mapping_and_fallbacks(sample_company):
    extractor = FinancialExtractor(sample_company)
    snapshot = extractor.snapshot(2023)

    assert snapshot.get("current_assets") == 120
    assert snapshot.get("gross_profit") == 400
    assert snapshot.get("total_debt") == 300
    assert extractor.latest_close() == 300
