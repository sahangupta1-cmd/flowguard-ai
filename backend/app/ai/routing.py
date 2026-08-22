from __future__ import annotations

import re
from dataclasses import dataclass

from backend.app.ai.models import (
    FinanceDomain,
    TrustedEvidence,
)


# ----------------------------------------------------------------------
# Deterministic finance-domain routing
# ----------------------------------------------------------------------

DOMAIN_KEYWORDS: dict[FinanceDomain, tuple[str, ...]] = {
    "reconciliation": (
        "reconcile",
        "reconciliation",
        "match",
        "matched",
        "matching",
        "mismatch",
        "unmatched",
        "exception",
        "settlement",
        "human review",
        "review cases",
        "auto close",
        "auto-close",
        "exact match",
        "fuzzy",
        "chain",
    ),
    "receivables": (
        "receivable",
        "receivables",
        "invoice",
        "invoices",
        "late payment",
        "payment delay",
        "customer payment",
        "collection",
        "collections",
        "overdue",
        "amount at risk",
        "high risk",
        "high-risk",
        "late probability",
        "prediction confidence",
    ),
    "cashflow": (
        "cash flow",
        "cashflow",
        "cash balance",
        "opening cash",
        "ending balance",
        "inflow",
        "inflows",
        "outflow",
        "outflows",
        "shortfall",
        "forecast",
        "forecast horizon",
        "expense",
        "expenses",
    ),
    "liquidity": (
        "liquidity",
        "cash gap",
        "temporary gap",
        "temporary cash gap",
        "delayed receivable",
        "delayed receivables",
        "delay days",
        "reduced liquidity",
        "liquidity risk",
    ),
    "priority": (
        "priority",
        "priorities",
        "prioritize",
        "focus",
        "urgent",
        "attention",
        "recommend",
        "recommendation",
        "recommended",
        "what should",
        "next action",
        "next step",
        "today",
    ),
    "system": (),
}


SUMMARY_PHRASES = (
    "summary",
    "summarize",
    "overall",
    "financial position",
    "financial health",
    "cfo overview",
    "company position",
    "business position",
    "dashboard overview",
    "how are we doing",
)


DOMAIN_EVIDENCE_IDS: dict[
    FinanceDomain,
    tuple[str, ...],
] = {
    "reconciliation": (
        "reconciliation.cases_processed",
        "reconciliation.complete_chain_count",
        "reconciliation.complete_chain_rate_pct",
        "reconciliation.auto_closed_count",
        "reconciliation.auto_closure_rate_pct",
        "reconciliation.requires_review_count",
        "reconciliation.requires_review_rate_pct",
        "reconciliation.exact_match_cases",
        "reconciliation.fuzzy_recovery_cases",
        "reconciliation.unresolved_or_review_count",
    ),
    "receivables": (
        "receivables.open_invoices",
        "receivables.amount_at_risk",
        "receivables.high_risk_threshold_pct",
        "receivables.high_risk_invoices",
        "receivables.high_risk_amount",
        "receivables.average_late_probability_pct",
        "receivables.average_prediction_confidence_pct",
    ),
    "cashflow": (
        "cashflow.opening_cash_balance",
        "cashflow.horizon_end",
        "cashflow.total_expected_inflows",
        "cashflow.total_scheduled_outflows",
        "cashflow.projected_ending_balance",
        "cashflow.shortfall_detected",
        "cashflow.first_shortfall_date",
        "cashflow.maximum_shortfall",
        "cashflow.minimum_projected_balance",
        "cashflow.severity",
        "cashflow.recommended_action",
    ),
    "liquidity": (
        "liquidity.total_delayed_receivables",
        "liquidity.weighted_average_delay_days",
        "liquidity.maximum_temporary_cash_gap",
        "liquidity.maximum_gap_date",
        "liquidity.days_with_reduced_liquidity",
        "liquidity.cash_delayed_by_first_expense",
        "liquidity.incremental_shortfall",
        "liquidity.severity",
    ),
    "priority": (),
    "system": (),
}


SUMMARY_EVIDENCE_IDS = (
    "reconciliation.cases_processed",
    "reconciliation.requires_review_count",
    "reconciliation.auto_closure_rate_pct",
    "receivables.open_invoices",
    "receivables.high_risk_invoices",
    "receivables.high_risk_amount",
    "receivables.average_late_probability_pct",
    "receivables.average_prediction_confidence_pct",
    "cashflow.projected_ending_balance",
    "cashflow.shortfall_detected",
    "cashflow.minimum_projected_balance",
    "cashflow.severity",
    "liquidity.maximum_temporary_cash_gap",
    "liquidity.days_with_reduced_liquidity",
    "liquidity.severity",
)


@dataclass(frozen=True)
class RoutingDecision:
    """
    Deterministic result of routing one Ask FlowGuard question.

    No LLM call is required for classification.
    """

    domains: tuple[FinanceDomain, ...]

    is_summary: bool

    matched_keywords: tuple[str, ...]


def _normalize_question(
    question: str,
) -> str:
    value = str(
        question
    ).lower()

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def route_question(
    question: str,
) -> RoutingDecision:
    """
    Route a finance question using deterministic keyword scoring.

    This avoids spending a separate LLM call merely to classify
    the user's question.
    """

    normalized = _normalize_question(
        question
    )

    summary_matches = tuple(
        phrase
        for phrase in SUMMARY_PHRASES
        if phrase in normalized
    )

    if summary_matches:
        return RoutingDecision(
            domains=(
                "reconciliation",
                "receivables",
                "cashflow",
                "liquidity",
                "priority",
            ),
            is_summary=True,
            matched_keywords=summary_matches,
        )

    scores: dict[
        FinanceDomain,
        int,
    ] = {}

    matched: list[str] = []

    for domain, keywords in (
        DOMAIN_KEYWORDS.items()
    ):
        if domain == "system":
            continue

        score = 0

        for keyword in keywords:
            if keyword in normalized:
                score += 1

                if keyword not in matched:
                    matched.append(
                        keyword
                    )

        if score > 0:
            scores[domain] = score

    if not scores:
        # Unknown/general CFO questions receive deterministic
        # priority context instead of all 47 facts.
        return RoutingDecision(
            domains=("priority",),
            is_summary=False,
            matched_keywords=(),
        )

    highest_score = max(
        scores.values()
    )

    # Keep strongly related domains while avoiding noisy context.
    selected = tuple(
        domain
        for domain, score in scores.items()
        if score >= max(
            1,
            highest_score - 1,
        )
    )

    return RoutingDecision(
        domains=selected,
        is_summary=False,
        matched_keywords=tuple(
            matched
        ),
    )


def _priority_evidence(
    evidence_index: dict[
        str,
        TrustedEvidence,
    ],
) -> list[TrustedEvidence]:
    """
    Return deterministic CFO priority evidence.

    Priority count can vary, so these IDs are discovered from the
    trusted catalogue rather than hard-coded to exactly three items.
    """

    return [
        item
        for evidence_id, item
        in evidence_index.items()
        if evidence_id.startswith(
            "priority."
        )
    ]


def _resolve_known_ids(
    evidence_ids: tuple[str, ...],
    evidence_index: dict[
        str,
        TrustedEvidence,
    ],
) -> list[TrustedEvidence]:
    """
    Resolve known application-controlled evidence IDs.

    Missing optional facts are ignored here because some fields, such
    as first_shortfall_date, legitimately do not exist when no
    shortfall is present.
    """

    return [
        evidence_index[evidence_id]
        for evidence_id in evidence_ids
        if evidence_id in evidence_index
    ]


def select_relevant_evidence(
    *,
    question: str,
    evidence_index: dict[
        str,
        TrustedEvidence,
    ],
    max_facts: int = 18,
) -> tuple[
    RoutingDecision,
    list[TrustedEvidence],
]:
    """
    Select the smallest useful trusted-evidence subset for an AI query.

    The master evidence catalogue remains unchanged. This function only
    controls what is exposed to the provider for the current question.
    """

    if max_facts < 1:
        raise ValueError(
            "max_facts must be at least 1."
        )

    decision = route_question(
        question
    )

    selected: list[
        TrustedEvidence
    ] = []

    seen: set[str] = set()

    def add(
        item: TrustedEvidence,
    ) -> None:
        if item.evidence_id in seen:
            return

        if len(selected) >= max_facts:
            return

        selected.append(
            item
        )

        seen.add(
            item.evidence_id
        )

    if decision.is_summary:
        for item in _resolve_known_ids(
            SUMMARY_EVIDENCE_IDS,
            evidence_index,
        ):
            add(item)

        # Add the highest-level deterministic CFO priorities if space
        # remains after the cross-domain summary metrics.
        for item in _priority_evidence(
            evidence_index
        ):
            add(item)

        return (
            decision,
            selected,
        )

    for domain in decision.domains:
        if domain == "priority":
            domain_items = (
                _priority_evidence(
                    evidence_index
                )
            )

        else:
            domain_items = (
                _resolve_known_ids(
                    DOMAIN_EVIDENCE_IDS[
                        domain
                    ],
                    evidence_index,
                )
            )

        for item in domain_items:
            add(item)

    return (
        decision,
        selected,
    )
