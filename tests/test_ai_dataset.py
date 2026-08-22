from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.ai.dataset import (
    build_ai_finance_context,
    resolve_ai_dataset,
)
from backend.app.ai.models import AskFlowGuardRequest
from backend.app.ingestion.service import CSVImportService


REQUIRED_DATASETS = (
    "customers",
    "invoices",
    "payments",
    "settlements",
    "bank_transactions",
    "expenses",
)

OPTIONAL_DATASETS = (
    "refunds",
    "chargebacks",
)


def _source_files(
    raw_dir: Path,
) -> dict[str, Path]:
    """
    Build the source-file mapping expected by CSVImportService.

    Required operational datasets must exist. Optional datasets are
    included only when present.
    """

    files: dict[str, Path] = {}

    for dataset_type in REQUIRED_DATASETS:
        path = raw_dir / f"{dataset_type}.csv"

        assert path.is_file(), (
            f"Missing required test dataset: {path}"
        )

        files[dataset_type] = path

    for dataset_type in OPTIONAL_DATASETS:
        path = raw_dir / f"{dataset_type}.csv"

        if path.is_file():
            files[dataset_type] = path

    return files


@pytest.fixture()
def isolated_import(
    tmp_path: Path,
):
    """
    Create a genuine validated FlowGuard import in a temporary folder.

    Nothing is written to the project's real data/imports directory.
    """

    raw_dir = Path("data/raw")

    import_root = (
        tmp_path
        / "imports"
    )

    service = CSVImportService(
        import_root=import_root
    )

    result = service.create_import(
        _source_files(raw_dir)
    )

    return (
        import_root,
        result,
    )


def test_demo_dataset_resolution() -> None:
    request = AskFlowGuardRequest(
        question="What should I prioritize today?",
        import_id=None,
        as_of_date=date(2026, 8, 1),
        opening_cash_balance=Decimal("500000.00"),
        horizon_days=90,
    )

    resolved = resolve_ai_dataset(
        request
    )

    assert resolved.provenance.source_type == "demo"
    assert resolved.provenance.import_id is None
    assert resolved.provenance.fingerprint is None

    assert resolved.raw_dir.name == "raw"


def test_uploaded_import_resolves_normalized_dataset(
    isolated_import,
) -> None:
    import_root, result = isolated_import

    request = AskFlowGuardRequest(
        question="Summarize this company's financial position.",
        import_id=result.import_id,
        as_of_date=date(2026, 8, 1),
        opening_cash_balance=Decimal("500000.00"),
        horizon_days=90,
    )

    resolved = resolve_ai_dataset(
        request,
        import_root=import_root,
    )

    expected_normalized = Path(
        result.normalized_path
    ).resolve()

    assert (
        resolved.provenance.source_type
        == "uploaded_import"
    )

    assert (
        resolved.provenance.import_id
        == result.import_id
    )

    assert (
        resolved.provenance.fingerprint
        == result.fingerprint
    )

    assert (
        resolved.raw_dir
        == expected_normalized
    )

    assert resolved.raw_dir.name == "normalized"

    # Critical proof: uploaded AI does not resolve to data/raw.
    assert resolved.raw_dir != Path(
        "data/raw"
    ).resolve()


def test_uploaded_import_builds_trusted_ai_context(
    isolated_import,
) -> None:
    import_root, result = isolated_import

    request = AskFlowGuardRequest(
        question="Why are my receivables high risk?",
        import_id=result.import_id,
        as_of_date=date(2026, 8, 1),
        opening_cash_balance=Decimal("500000.00"),
        horizon_days=90,
    )

    context = build_ai_finance_context(
        request,
        import_root=import_root,
    )

    assert (
        context.provenance.source_type
        == "uploaded_import"
    )

    assert (
        context.provenance.import_id
        == result.import_id
    )

    assert (
        context.provenance.fingerprint
        == result.fingerprint
    )

    assert len(context.evidence) >= 40

    assert (
        "receivables.high_risk_amount"
        in context.evidence_index
    )

    assert (
        "reconciliation.requires_review_count"
        in context.evidence_index
    )

    assert (
        "cashflow.projected_ending_balance"
        in context.evidence_index
    )

    assert (
        "liquidity.maximum_temporary_cash_gap"
        in context.evidence_index
    )


def test_uploaded_provider_payload_contains_provenance_not_paths(
    isolated_import,
) -> None:
    import_root, result = isolated_import

    request = AskFlowGuardRequest(
        question="What should the CFO focus on?",
        import_id=result.import_id,
        as_of_date=date(2026, 8, 1),
        opening_cash_balance=Decimal("500000.00"),
        horizon_days=90,
    )

    context = build_ai_finance_context(
        request,
        import_root=import_root,
    )

    provenance = context.llm_payload[
        "provenance"
    ]

    assert provenance[
        "source_type"
    ] == "uploaded_import"

    assert provenance[
        "import_id"
    ] == result.import_id

    assert provenance[
        "fingerprint"
    ] == result.fingerprint

    serialized = str(
        context.llm_payload
    ).lower()

    assert "normalized_path" not in serialized
    assert "manifest_path" not in serialized
    assert str(import_root).lower() not in serialized


def test_unknown_import_fails_closed(
    tmp_path: Path,
) -> None:
    request = AskFlowGuardRequest(
        question="What should I prioritize?",
        import_id="imp_aaaaaaaaaaaa",
        as_of_date=date(2026, 8, 1),
        opening_cash_balance=Decimal("500000.00"),
        horizon_days=90,
    )

    with pytest.raises(
        FileNotFoundError,
        match="Operational import was not found",
    ):
        resolve_ai_dataset(
            request,
            import_root=tmp_path,
        )
