from src.calculations.ratios import RatioCalculator
from src.calculations.repository import RatioRepository
from src.database import get_connection, init_db, store_normalized


def test_load_normalized_and_store_ratios(tmp_path, sample_company):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)

    company_id = store_normalized(
        conn,
        sample_company,
        source="file_upload",
        source_file="full_sample.json",
    )

    repository = RatioRepository(conn)
    loaded = repository.load_normalized_company(sample_company.company.ticker)

    assert loaded.company.ticker == "FULL"
    assert len(loaded.financials) == len(sample_company.financials)
    assert len(loaded.prices) == len(sample_company.prices)

    ratio_set = RatioCalculator().calculate_all(loaded)
    stored = repository.store_ratios(company_id, ratio_set.ratios)

    assert stored == 26

    row = conn.execute(
        "SELECT COUNT(*) AS count FROM ratios WHERE company_id = ?",
        (company_id,),
    ).fetchone()

    assert row["count"] == 26
    conn.close()
