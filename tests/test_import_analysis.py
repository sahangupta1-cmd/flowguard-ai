from datetime import date
from pathlib import Path

from backend.app.ingestion.contracts import CONTRACTS
from backend.app.ingestion.service import CSVImportService
from backend.app.intelligence.service import CFOIntelligenceService


RAW_PATH = Path("data/raw")


def _files() -> dict[str, Path]:
    return {
        dataset_type: RAW_PATH / contract.filename
        for dataset_type, contract in CONTRACTS.items()
    }


def test_default_cfo_intelligence_demo_regression() -> None:
    overview = CFOIntelligenceService().build_overview(
        opening_cash_balance="500000.00",
        horizon_days=90,
    )

    assert overview["as_of_date"] == "2026-08-01"

    assert (
        overview["reconciliation"]["cases_processed"]
        == 100
    )

    assert (
        overview["receivables"]["open_invoices"]
        == 44
    )

    assert (
        overview["cashflow"][
            "projected_ending_balance"
        ]
        == "3674900.00"
    )


def test_cfo_intelligence_runs_on_isolated_import(
    tmp_path: Path,
) -> None:
    importer = CSVImportService(
        import_root=tmp_path / "imports"
    )

    imported = importer.create_import(
        _files()
    )

    normalized_path = Path(
        imported.normalized_path
    )

    assert normalized_path != RAW_PATH

    intelligence = CFOIntelligenceService(
        raw_dir=normalized_path,
        as_of_date=date(2026, 8, 1),
    )

    overview = intelligence.build_overview(
        opening_cash_balance="500000.00",
        horizon_days=90,
    )

    assert overview["as_of_date"] == "2026-08-01"

    assert (
        overview["reconciliation"]["cases_processed"]
        == 100
    )

    assert (
        overview["receivables"]["open_invoices"]
        == 44
    )

    assert (
        overview["receivables"]["high_risk_invoices"]
        == 36
    )

    assert (
        overview["receivables"]["high_risk_amount"]
        == "7194400.00"
    )

    assert (
        overview["cashflow"][
            "projected_ending_balance"
        ]
        == "3674900.00"
    )

    assert (
        overview["liquidity_risk"][
            "maximum_temporary_cash_gap"
        ]
        == "4018225.00"
    )

    assert len(
        overview["priorities"]
    ) == 3
