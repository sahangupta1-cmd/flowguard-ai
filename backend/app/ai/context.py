from __future__ import annotations

from datetime import date
from typing import Any

from backend.app.ai.models import (
    AIDataProvenance,
    TrustedEvidence,
)
from backend.app.api.schemas import CFOIntelligenceOverviewResponse


def _parse_as_of_date(value: str) -> date:
    """
    Parse the trusted CFO snapshot date.

    The intelligence API already emits an ISO date string.
    Invalid dates fail closed rather than being silently replaced.
    """

    return date.fromisoformat(value)


def _add_evidence(
    catalogue: list[TrustedEvidence],
    *,
    evidence_id: str,
    domain: str,
    metric: str,
    value: Any,
    unit: str,
    source_field: str,
    as_of_date: date,
) -> None:
    """
    Add one deterministic fact to the evidence catalogue.

    None is intentionally excluded. Zero, False and empty numeric values
    remain valid evidence and must not be silently dropped.
    """

    if value is None:
        return

    if isinstance(value, bool):
        canonical_value = "true" if value else "false"
    else:
        canonical_value = str(value)

    catalogue.append(
        TrustedEvidence(
            evidence_id=evidence_id,
            domain=domain,
            metric=metric,
            value=canonical_value,
            unit=unit,
            source_field=source_field,
            as_of_date=as_of_date,
        )
    )


def build_trusted_evidence(
    overview: CFOIntelligenceOverviewResponse,
) -> list[TrustedEvidence]:
    """
    Convert one deterministic CFO intelligence snapshot into the exact
    evidence catalogue Ask FlowGuard is allowed to reason over.

    This function performs no prediction, reconciliation or financial
    calculation. It only exposes already-computed operational facts.

    Benchmark labels, expected outcomes and evaluation datasets are
    intentionally absent from this contract.
    """

    as_of_date = _parse_as_of_date(overview.as_of_date)

    evidence: list[TrustedEvidence] = []

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------

    reconciliation = overview.reconciliation

    reconciliation_fields = (
        (
            "reconciliation.cases_processed",
            "Cases processed",
            reconciliation.cases_processed,
            "count",
            "reconciliation.cases_processed",
        ),
        (
            "reconciliation.complete_chain_count",
            "Complete reconciliation chains",
            reconciliation.complete_chain_count,
            "count",
            "reconciliation.complete_chain_count",
        ),
        (
            "reconciliation.complete_chain_rate_pct",
            "Complete-chain rate",
            reconciliation.complete_chain_rate_pct,
            "percent",
            "reconciliation.complete_chain_rate_pct",
        ),
        (
            "reconciliation.auto_closed_count",
            "Auto-closed reconciliation cases",
            reconciliation.auto_closed_count,
            "count",
            "reconciliation.auto_closed_count",
        ),
        (
            "reconciliation.auto_closure_rate_pct",
            "Auto-closure rate",
            reconciliation.auto_closure_rate_pct,
            "percent",
            "reconciliation.auto_closure_rate_pct",
        ),
        (
            "reconciliation.requires_review_count",
            "Reconciliation cases requiring human review",
            reconciliation.requires_review_count,
            "count",
            "reconciliation.requires_review_count",
        ),
        (
            "reconciliation.requires_review_rate_pct",
            "Human-review rate",
            reconciliation.requires_review_rate_pct,
            "percent",
            "reconciliation.requires_review_rate_pct",
        ),
        (
            "reconciliation.exact_match_cases",
            "Exact-match reconciliation cases",
            reconciliation.exact_match_cases,
            "count",
            "reconciliation.exact_match_cases",
        ),
        (
            "reconciliation.fuzzy_recovery_cases",
            "Fuzzy-recovered reconciliation cases",
            reconciliation.fuzzy_recovery_cases,
            "count",
            "reconciliation.fuzzy_recovery_cases",
        ),
        (
            "reconciliation.unresolved_or_review_count",
            "Unresolved or review reconciliation cases",
            reconciliation.unresolved_or_review_count,
            "count",
            "reconciliation.unresolved_or_review_count",
        ),
    )

    for evidence_id, metric, value, unit, source_field in reconciliation_fields:
        _add_evidence(
            evidence,
            evidence_id=evidence_id,
            domain="reconciliation",
            metric=metric,
            value=value,
            unit=unit,
            source_field=source_field,
            as_of_date=as_of_date,
        )

    # ------------------------------------------------------------------
    # Receivables / payment-delay intelligence
    # ------------------------------------------------------------------

    receivables = overview.receivables

    receivables_fields = (
        (
            "receivables.open_invoices",
            "Open invoices",
            receivables.open_invoices,
            "count",
            "receivables.open_invoices",
        ),
        (
            "receivables.amount_at_risk",
            "Total receivables amount at risk",
            receivables.amount_at_risk,
            "INR",
            "receivables.amount_at_risk",
        ),
        (
            "receivables.high_risk_threshold_pct",
            "High-risk late-payment threshold",
            receivables.high_risk_threshold_pct,
            "percent",
            "receivables.high_risk_threshold_pct",
        ),
        (
            "receivables.high_risk_invoices",
            "High-risk open invoices",
            receivables.high_risk_invoices,
            "count",
            "receivables.high_risk_invoices",
        ),
        (
            "receivables.high_risk_amount",
            "High-risk receivables amount",
            receivables.high_risk_amount,
            "INR",
            "receivables.high_risk_amount",
        ),
        (
            "receivables.average_late_probability_pct",
            "Average predicted late-payment probability",
            receivables.average_late_probability_pct,
            "percent",
            "receivables.average_late_probability_pct",
        ),
        (
            "receivables.average_prediction_confidence_pct",
            "Average payment prediction confidence",
            receivables.average_prediction_confidence_pct,
            "percent",
            "receivables.average_prediction_confidence_pct",
        ),
    )

    for evidence_id, metric, value, unit, source_field in receivables_fields:
        _add_evidence(
            evidence,
            evidence_id=evidence_id,
            domain="receivables",
            metric=metric,
            value=value,
            unit=unit,
            source_field=source_field,
            as_of_date=as_of_date,
        )

    # ------------------------------------------------------------------
    # Cashflow
    # ------------------------------------------------------------------

    cashflow = overview.cashflow

    cashflow_fields = (
        (
            "cashflow.opening_cash_balance",
            "Opening cash balance",
            cashflow.opening_cash_balance,
            "INR",
            "cashflow.opening_cash_balance",
        ),
        (
            "cashflow.horizon_end",
            "Cashflow forecast horizon end",
            cashflow.horizon_end,
            "date",
            "cashflow.horizon_end",
        ),
        (
            "cashflow.total_expected_inflows",
            "Expected cash inflows",
            cashflow.total_expected_inflows,
            "INR",
            "cashflow.total_expected_inflows",
        ),
        (
            "cashflow.total_scheduled_outflows",
            "Scheduled cash outflows",
            cashflow.total_scheduled_outflows,
            "INR",
            "cashflow.total_scheduled_outflows",
        ),
        (
            "cashflow.projected_ending_balance",
            "Projected ending cash balance",
            cashflow.projected_ending_balance,
            "INR",
            "cashflow.projected_ending_balance",
        ),
        (
            "cashflow.shortfall_detected",
            "Cash shortfall detected",
            cashflow.shortfall_detected,
            "boolean",
            "cashflow.shortfall_detected",
        ),
        (
            "cashflow.first_shortfall_date",
            "First projected cash shortfall date",
            cashflow.first_shortfall_date,
            "date",
            "cashflow.first_shortfall_date",
        ),
        (
            "cashflow.maximum_shortfall",
            "Maximum projected cash shortfall",
            cashflow.maximum_shortfall,
            "INR",
            "cashflow.maximum_shortfall",
        ),
        (
            "cashflow.minimum_projected_balance",
            "Minimum projected cash balance",
            cashflow.minimum_projected_balance,
            "INR",
            "cashflow.minimum_projected_balance",
        ),
        (
            "cashflow.severity",
            "Cashflow severity",
            cashflow.severity,
            "severity",
            "cashflow.severity",
        ),
        (
            "cashflow.recommended_action",
            "Deterministic cashflow recommendation",
            cashflow.recommended_action,
            "text",
            "cashflow.recommended_action",
        ),
    )

    for evidence_id, metric, value, unit, source_field in cashflow_fields:
        _add_evidence(
            evidence,
            evidence_id=evidence_id,
            domain="cashflow",
            metric=metric,
            value=value,
            unit=unit,
            source_field=source_field,
            as_of_date=as_of_date,
        )

    # ------------------------------------------------------------------
    # Payment-delay liquidity impact
    # ------------------------------------------------------------------

    liquidity = overview.liquidity_risk

    liquidity_fields = (
        (
            "liquidity.total_delayed_receivables",
            "Predicted delayed receivables",
            liquidity.total_delayed_receivables,
            "INR",
            "liquidity_risk.total_delayed_receivables",
        ),
        (
            "liquidity.weighted_average_delay_days",
            "Weighted average predicted payment delay",
            liquidity.weighted_average_delay_days,
            "days",
            "liquidity_risk.weighted_average_delay_days",
        ),
        (
            "liquidity.maximum_temporary_cash_gap",
            "Maximum temporary cash gap from payment delay",
            liquidity.maximum_temporary_cash_gap,
            "INR",
            "liquidity_risk.maximum_temporary_cash_gap",
        ),
        (
            "liquidity.maximum_gap_date",
            "Date of maximum temporary cash gap",
            liquidity.maximum_gap_date,
            "date",
            "liquidity_risk.maximum_gap_date",
        ),
        (
            "liquidity.days_with_reduced_liquidity",
            "Days with reduced liquidity",
            liquidity.days_with_reduced_liquidity,
            "days",
            "liquidity_risk.days_with_reduced_liquidity",
        ),
        (
            "liquidity.cash_delayed_by_first_expense",
            "Cash delayed by first scheduled expense",
            liquidity.cash_delayed_by_first_expense,
            "INR",
            "liquidity_risk.cash_delayed_by_first_expense",
        ),
        (
            "liquidity.incremental_shortfall",
            "Incremental shortfall caused by payment delay",
            liquidity.incremental_shortfall,
            "INR",
            "liquidity_risk.incremental_shortfall",
        ),
        (
            "liquidity.severity",
            "Payment-delay liquidity severity",
            liquidity.severity,
            "severity",
            "liquidity_risk.severity",
        ),
    )

    for evidence_id, metric, value, unit, source_field in liquidity_fields:
        _add_evidence(
            evidence,
            evidence_id=evidence_id,
            domain="liquidity",
            metric=metric,
            value=value,
            unit=unit,
            source_field=source_field,
            as_of_date=as_of_date,
        )

    # ------------------------------------------------------------------
    # Deterministic CFO priorities
    # ------------------------------------------------------------------

    for index, priority in enumerate(overview.priorities, start=1):
        prefix = f"priority.{index}"

        _add_evidence(
            evidence,
            evidence_id=f"{prefix}.code",
            domain="priority",
            metric=f"Priority {index} code",
            value=priority.code,
            unit="text",
            source_field=f"priorities[{index - 1}].code",
            as_of_date=as_of_date,
        )

        _add_evidence(
            evidence,
            evidence_id=f"{prefix}.severity",
            domain="priority",
            metric=f"Priority {index} severity",
            value=priority.severity,
            unit="severity",
            source_field=f"priorities[{index - 1}].severity",
            as_of_date=as_of_date,
        )

        _add_evidence(
            evidence,
            evidence_id=f"{prefix}.title",
            domain="priority",
            metric=f"Priority {index} title",
            value=priority.title,
            unit="text",
            source_field=f"priorities[{index - 1}].title",
            as_of_date=as_of_date,
        )

        _add_evidence(
            evidence,
            evidence_id=f"{prefix}.detail",
            domain="priority",
            metric=f"Priority {index} detail",
            value=priority.detail,
            unit="text",
            source_field=f"priorities[{index - 1}].detail",
            as_of_date=as_of_date,
        )

    return evidence


def build_evidence_index(
    evidence: list[TrustedEvidence],
) -> dict[str, TrustedEvidence]:
    """
    Build a unique evidence lookup used after LLM generation.

    Duplicate IDs are treated as a programming error because ambiguity in
    financial evidence must never be silently accepted.
    """

    index: dict[str, TrustedEvidence] = {}

    for item in evidence:
        if item.evidence_id in index:
            raise RuntimeError(
                f"Duplicate trusted evidence ID: {item.evidence_id}"
            )

        index[item.evidence_id] = item

    return index


def resolve_evidence_ids(
    evidence_ids: list[str],
    evidence_index: dict[str, TrustedEvidence],
) -> list[TrustedEvidence]:
    """
    Resolve provider-selected evidence IDs against trusted application data.

    Unknown evidence IDs fail closed instead of being ignored.
    """

    resolved: list[TrustedEvidence] = []
    seen: set[str] = set()

    for evidence_id in evidence_ids:
        if evidence_id in seen:
            continue

        item = evidence_index.get(evidence_id)

        if item is None:
            raise ValueError(
                f"Untrusted or unknown evidence ID: {evidence_id}"
            )

        resolved.append(item)
        seen.add(evidence_id)

    return resolved


def build_llm_context_payload(
    *,
    provenance: AIDataProvenance,
    evidence: list[TrustedEvidence],
) -> dict[str, Any]:
    """
    Produce the controlled context payload supplied to the reasoning model.

    Only provenance and deterministic evidence are exposed.
    Filesystem paths, raw CSV content, benchmark data and evaluation labels
    are deliberately absent.
    """

    return {
        "provenance": provenance.model_dump(
            mode="json",
            exclude_none=True,
        ),
        "trusted_evidence": [
            item.model_dump(mode="json")
            for item in evidence
        ],
    }
