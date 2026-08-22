from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.app.ai.dataset import build_ai_finance_context
from backend.app.ai.models import AskFlowGuardRequest
from backend.app.ai.routing import (
    route_question,
    select_relevant_evidence,
)


@pytest.fixture(scope="module")
def evidence_index():
    request = AskFlowGuardRequest(
        question="Build routing test context.",
        import_id=None,
        as_of_date=date(2026, 8, 1),
        opening_cash_balance=Decimal("500000.00"),
        horizon_days=90,
    )

    context = build_ai_finance_context(
        request
    )

    assert len(context.evidence) == 47

    return context.evidence_index


def test_receivables_question_routes_to_receivables() -> None:
    decision = route_question(
        "Why are my receivables high risk?"
    )

    assert decision.domains == (
        "receivables",
    )

    assert decision.is_summary is False


def test_reconciliation_question_routes_correctly() -> None:
    decision = route_question(
        "How many reconciliation cases require human review?"
    )

    assert decision.domains == (
        "reconciliation",
    )


def test_liquidity_question_routes_correctly() -> None:
    decision = route_question(
        "Explain the temporary cash gap."
    )

    assert decision.domains == (
        "liquidity",
    )


def test_priority_question_routes_correctly() -> None:
    decision = route_question(
        "What should I prioritize today?"
    )

    assert decision.domains == (
        "priority",
    )


def test_summary_routes_across_finance_domains() -> None:
    decision = route_question(
        "Summarize the company's financial position."
    )

    assert decision.is_summary is True

    assert decision.domains == (
        "reconciliation",
        "receivables",
        "cashflow",
        "liquidity",
        "priority",
    )


def test_cross_domain_question_routes_to_relevant_domains() -> None:
    decision = route_question(
        "How do late payments affect liquidity?"
    )

    assert "receivables" in decision.domains
    assert "liquidity" in decision.domains


def test_receivables_selection_does_not_send_all_facts(
    evidence_index,
) -> None:
    decision, selected = select_relevant_evidence(
        question="Why are my receivables high risk?",
        evidence_index=evidence_index,
    )

    assert decision.domains == (
        "receivables",
    )

    assert len(selected) == 7
    assert len(selected) < len(
        evidence_index
    )

    assert all(
        item.domain == "receivables"
        for item in selected
    )


def test_summary_selection_respects_fact_limit(
    evidence_index,
) -> None:
    _, selected = select_relevant_evidence(
        question=(
            "Summarize the company's financial position."
        ),
        evidence_index=evidence_index,
        max_facts=18,
    )

    assert 1 <= len(selected) <= 18


def test_unknown_general_question_uses_priority_fallback(
    evidence_index,
) -> None:
    decision, selected = select_relevant_evidence(
        question="What stands out?",
        evidence_index=evidence_index,
    )

    assert decision.domains == (
        "priority",
    )

    assert selected

    assert all(
        item.domain == "priority"
        for item in selected
    )


def test_custom_fact_limit_is_enforced(
    evidence_index,
) -> None:
    _, selected = select_relevant_evidence(
        question=(
            "Summarize the overall financial position."
        ),
        evidence_index=evidence_index,
        max_facts=5,
    )

    assert len(selected) == 5


def test_invalid_fact_limit_fails_closed(
    evidence_index,
) -> None:
    with pytest.raises(
        ValueError,
        match="max_facts must be at least 1",
    ):
        select_relevant_evidence(
            question="What should I prioritize?",
            evidence_index=evidence_index,
            max_facts=0,
        )
