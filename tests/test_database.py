from src.database import get_connection, init_db, store_normalized
from src.models import CompanyProfile, FinancialLine, NormalizedCompany


def test_store_normalized(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)

    data = NormalizedCompany(
        company=CompanyProfile(ticker="TEST", name="Test Company"),
        financials=[
            FinancialLine(
                fiscal_year=2023,
                statement_type="balance_sheet",
                line_item="Equity",
                value=100.0,
            )
        ],
    )

    company_id = store_normalized(
        conn,
        data,
        source="file_upload",
        source_file="test.csv",
    )

    row = conn.execute(
        "SELECT COUNT(*) AS count FROM financials WHERE company_id = ?",
        (company_id,),
    ).fetchone()

    assert row["count"] == 1
    conn.close()
