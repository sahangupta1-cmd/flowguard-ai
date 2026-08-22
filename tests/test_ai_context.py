from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.app.ai.context import (
    build_evidence_index,
    build_llm_context_payload,
    build_trusted_evidence,
    resolve_evidence_ids,
)
from backend.app.ai.models import (
    AIDataProvenance,
    TrustedEvidence,
)
from backend.app.api.schemas import CFOIntelligenceOverviewResponse
from backend.app.intelligence.service import CFOIntelligenceService


@pytest.fixture(scope="module")
def demo_overview() -> CFOIntelligenceOverviewResponse:
    service = CFOIntelligenceService(
        as_of_date=date(2026, 8, 1),
    )

    overview = service.build_overview(
        opening_cash_balance=Decimal("500000.00"),
        horizon_days=90,
    )

    return CFOIntelligenceOverviewResponse(
        **overview
    )


@pytest.fixture(scope="module")
def demo_evidence(
    demo_overview: CFOIntelligenceOverviewResponse,
) -> list[TrustedEvidence]:
    return build_trusted_evidence(
        demo_overview
    )


def test_trusted_evidence_ids_are_unique(
    demo_evidence: list[TrustedEvidence],
) -> None:
    index = build_evidence_index(
        demo_evidence
    )

    assert len(demo_evidence) == len(index)
    assert len(demo_evidence) >= 40


def test_real_operational_metrics_are_grounded(
    demo_evidence: list[TrustedEvidence],
) -> None:
    index = build_evidence_index(
        demo_evidence
    )

    assert (
        index[
            "reconciliation.requires_review_count"
        ].value
        == "23"
    )

    assert (
        index[
            "receivables.high_risk_amount"
        ].value
        == "7194400.00"
    )

    assert (
        index[
            "receivables.average_late_probability_pct"
        ].value
        == "86.95"
    )

    assert (
        index[
            "receivables.average_prediction_confidence_pct"
        ].value
        == "48.31"
    )

    assert (
        index[
            "liquidity.maximum_temporary_cash_gap"
        ].value
        == "4018225.00"
    )


def test_boolean_false_is_preserved_as_evidence(
    demo_evidence: list[TrustedEvidence],
) -> None:
    index = build_evidence_index(
        demo_evidence
    )

    assert (
        index[
            "cashflow.shortfall_detected"
        ].value
        == "false"
    )


def test_unknown_evidence_id_fails_closed(
    demo_evidence: list[TrustedEvidence],
) -> None:
    index = build_evidence_index(
        demo_evidence
    )

    with pytest.raises(
        ValueError,
        match="Untrusted or unknown evidence ID",
    ):
        resolve_evidence_ids(
            [
                "receivables.high_risk_amount",
                "fake.financial.fact",
            ],
            index,
        )


def test_duplicate_requested_evidence_is_deduplicated(
    demo_evidence: list[TrustedEvidence],
) -> None:
    index = build_evidence_index(
        demo_evidence
    )

    resolved = resolve_evidence_ids(
        [
            "receivables.high_risk_amount",
            "receivables.high_risk_amount",
        ],
        index,
    )

    assert len(resolved) == 1

    assert (
        resolved[0].evidence_id
        == "receivables.high_risk_amount"
    )


def test_duplicate_catalogue_id_fails_closed(
    demo_evidence: list[TrustedEvidence],
) -> None:
    duplicated = [
        demo_evidence[0],
        demo_evidence[0],
    ]

    with pytest.raises(
        RuntimeError,
        match="Duplicate trusted evidence ID",
    ):
        build_evidence_index(
            duplicated
        )


def test_llm_payload_excludes_sensitive_internal_metadata(
    demo_evidence: list[TrustedEvidence],
) -> None:
    provenance = AIDataProvenance(
        source_type="demo",
        as_of_date=date(2026, 8, 1),
        import_id=None,
        fingerprint=None,
        opening_cash_balance="500000.00",
        horizon_days=90,
    )

    payload = build_llm_context_payload(
        provenance=provenance,
        evidence=demo_evidence,
    )

    serialized = str(payload).lower()

    forbidden_terms = (
        "benchmark",
        "ground_truth",
        "normalized_path",
        "manifest_path",
        "data/evaluation",
    )

    for forbidden in forbidden_terms:
        assert forbidden not in serialized


def test_demo_provenance_contains_no_filesystem_path(
    demo_evidence: list[TrustedEvidence],
) -> None:
    provenance = AIDataProvenance(
        source_type="demo",
        as_of_date=date(2026, 8, 1),
        import_id=None,
        fingerprint=None,
        opening_cash_balance="500000.00",
        horizon_days=90,
    )

    payload = build_llm_context_payload(
        provenance=provenance,
        evidence=demo_evidence,
    )

    assert payload["provenance"] == {
        "source_type": "demo",
        "as_of_date": "2026-08-01",
        "opening_cash_balance": "500000.00",
        "horizon_days": 90,
    }


def test_selected_evidence_retains_source_provenance(
    demo_evidence: list[TrustedEvidence],
) -> None:
    index = build_evidence_index(
        demo_evidence
    )

    evidence = index[
        "receivables.high_risk_amount"
    ]

    assert (
        evidence.source_field
        == "receivables.high_risk_amount"
    )

    assert evidence.domain == "receivables"
    assert evidence.unit == "INR"
    assert evidence.as_of_date == date(
        2026,
        8,
        1,
    )
