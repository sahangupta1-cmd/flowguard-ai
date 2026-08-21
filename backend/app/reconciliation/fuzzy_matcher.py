from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

import pandas as pd
from rapidfuzz import fuzz

from .confidence import (
    ConfidenceBand,
    assess_confidence,
    weighted_score,
)
from .exact_matcher import (
    canonical_exact_identifier,
    require_columns,
)
from .models import (
    MatchDecision,
    MatchMethod,
)
from .normalizers import (
    date_distance_days,
    is_blank,
    normalize_company_name,
    normalize_reference,
    to_decimal,
)


# ============================================================
# HARD SAFETY LIMITS
# ============================================================

INVOICE_PAYMENT_MAX_DATE_DISTANCE = 45

PAYMENT_SETTLEMENT_MAX_DATE_DISTANCE = 10

SETTLEMENT_BANK_MAX_DATE_DISTANCE = 14

STRICT_AMOUNT_TOLERANCE = Decimal("1.00")


# ============================================================
# INTERNAL HELPERS
# ============================================================


def _amount_is_close(
    first: Any,
    second: Any,
    *,
    tolerance: Decimal = STRICT_AMOUNT_TOLERANCE,
) -> bool:
    """
    Conservative amount gate used before fuzzy scoring.

    Fuzzy text similarity is never allowed to compensate for
    a materially different financial amount.
    """

    first_amount = to_decimal(first)
    second_amount = to_decimal(second)

    return (
        abs(first_amount - second_amount)
        <= tolerance
    )


def _date_score(
    distance: int | None,
    *,
    excellent: int,
    good: int,
    acceptable: int,
) -> float:
    """
    Convert date distance into a transparent 0-100 score.
    """

    if distance is None:
        return 0.0

    if distance <= excellent:
        return 100.0

    if distance <= good:
        return 85.0

    if distance <= acceptable:
        return 60.0

    return 0.0


def _reference_similarity(
    company_name: Any,
    reference_text: Any,
) -> float:
    """
    Compare normalized company identity with free-text
    payment/settlement/bank references.
    """

    company = normalize_company_name(
        company_name
    )

    reference = normalize_company_name(
        normalize_reference(reference_text)
    )

    if not company or not reference:
        return 0.0

    return float(
        fuzz.partial_ratio(
            company,
            reference,
        )
    )


def _customer_score(
    expected_customer_id: Any,
    candidate_customer_id: Any,
    *,
    company_name: Any,
    candidate_reference: Any,
) -> float:
    """
    Prefer exact customer identity when available.

    If one side lacks a customer ID, use company/reference
    evidence instead.
    """

    expected = canonical_exact_identifier(
        expected_customer_id
    )

    candidate = canonical_exact_identifier(
        candidate_customer_id
    )

    if expected and candidate:

        if expected == candidate:
            return 100.0

        return 0.0

    return _reference_similarity(
        company_name,
        candidate_reference,
    )


def _decision_from_ranked_candidates(
    ranked: list[
        tuple[
            float,
            str,
            dict[str, Any],
            pd.Series,
        ]
    ],
) -> tuple[
    MatchDecision,
    pd.Series | None,
]:
    """
    Apply ambiguity-aware confidence policy to ranked fuzzy
    candidates.
    """

    if not ranked:

        return (
            MatchDecision(
                matched=False,
                record_id=None,
                confidence=0.0,
                method=MatchMethod.NONE,
                requires_review=True,
                evidence={
                    "confidence_band":
                        ConfidenceBand.REJECT.value,

                    "reason":
                        "No safe fuzzy candidate found.",
                },
            ),
            None,
        )

    ranked.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    best_score, best_id, best_evidence, best_row = (
        ranked[0]
    )

    second_best_score = (
        ranked[1][0]
        if len(ranked) > 1
        else None
    )

    assessment = assess_confidence(
        best_score,
        second_best_score,
    )

    evidence = dict(
        best_evidence
    )

    evidence.update(
        {
            "confidence_band":
                assessment.band.value,

            "second_best_score":
                assessment.second_best_score,

            "margin":
                assessment.margin,

            "candidate_count":
                len(ranked),

            "decision_reason":
                assessment.reason,
        }
    )

    decision = MatchDecision(
        matched=assessment.accepted,
        record_id=best_id,
        confidence=assessment.score,
        method=MatchMethod.FUZZY,
        requires_review=assessment.requires_review,
        evidence=evidence,
    )

    return (
        decision,
        best_row.copy(),
    )


# ============================================================
# INVOICE -> PAYMENT FUZZY RECOVERY
# ============================================================


def fuzzy_match_invoice_to_payment(
    invoice: Mapping[str, Any] | pd.Series,
    payments: pd.DataFrame,
) -> tuple[
    MatchDecision,
    pd.Series | None,
]:
    """
    Recover an invoice-to-payment relationship when the
    direct invoice identifier is unavailable.

    Evidence:
        40% amount
        30% customer
        10% date
        20% reference

    Fuzzy matching is used only to identify a candidate.
    Financial reconciliation happens later.
    """

    require_columns(
        payments,
        {
            "payment_id",
            "invoice_id",
            "customer_id",
            "amount",
            "payment_date",
            "reference",
        },
        dataset_name="payments",
    )

    required_invoice_fields = {
        "invoice_id",
        "customer_id",
        "customer_name",
        "invoice_amount",
        "due_date",
    }

    missing = (
        required_invoice_fields
        - set(invoice.index)
        if isinstance(invoice, pd.Series)
        else required_invoice_fields
        - set(invoice.keys())
    )

    if missing:
        raise ValueError(
            "Invoice is missing required field(s): "
            + ", ".join(sorted(missing))
        )

    ranked = []

    for _, candidate in payments.iterrows():

        # -----------------------------------------------
        # HARD AMOUNT GATE
        # -----------------------------------------------

        if not _amount_is_close(
            invoice["invoice_amount"],
            candidate["amount"],
        ):
            continue

        # -----------------------------------------------
        # CUSTOMER EVIDENCE
        # -----------------------------------------------

        customer_score = _customer_score(
            invoice["customer_id"],
            candidate["customer_id"],
            company_name=invoice["customer_name"],
            candidate_reference=candidate["reference"],
        )

        # A known conflicting customer is unsafe.
        if customer_score == 0:
            continue

        # -----------------------------------------------
        # DATE EVIDENCE
        # -----------------------------------------------

        distance = date_distance_days(
            invoice["due_date"],
            candidate["payment_date"],
        )

        if (
            distance is not None
            and distance
            > INVOICE_PAYMENT_MAX_DATE_DISTANCE
        ):
            continue

        date_score = _date_score(
            distance,
            excellent=7,
            good=20,
            acceptable=45,
        )

        # -----------------------------------------------
        # REFERENCE EVIDENCE
        # -----------------------------------------------

        reference_score = (
            _reference_similarity(
                invoice["customer_name"],
                candidate["reference"],
            )
        )

        # -----------------------------------------------
        # WEIGHTED CONFIDENCE
        # -----------------------------------------------

        score = weighted_score(
            amount=100.0,
            customer=customer_score,
            date=date_score,
            reference=reference_score,
            amount_weight=0.40,
            customer_weight=0.30,
            date_weight=0.10,
            reference_weight=0.20,
        )

        payment_id = (
            canonical_exact_identifier(
                candidate["payment_id"]
            )
        )

        ranked.append(
            (
                score,
                payment_id,
                {
                    "amount_score": 100.0,
                    "customer_score":
                        round(customer_score, 2),

                    "date_score":
                        round(date_score, 2),

                    "reference_score":
                        round(reference_score, 2),

                    "date_distance_days":
                        distance,
                },
                candidate,
            )
        )

    return _decision_from_ranked_candidates(
        ranked
    )


# ============================================================
# PAYMENT -> SETTLEMENT FUZZY RECOVERY
# ============================================================


def fuzzy_match_payment_to_settlement(
    payment: Mapping[str, Any] | pd.Series,
    settlements: pd.DataFrame,
    *,
    customer_name: str,
) -> tuple[
    MatchDecision,
    pd.Series | None,
]:
    """
    Recover payment-to-settlement relationships when
    payment_id is missing from the settlement record.

    Evidence:
        45% gross amount
        25% date
        30% reference/customer
    """

    require_columns(
        settlements,
        {
            "settlement_id",
            "payment_id",
            "gross_amount",
            "settlement_date",
            "reference",
        },
        dataset_name="settlements",
    )

    required_payment_fields = {
        "payment_id",
        "amount",
        "payment_date",
    }

    keys = (
        set(payment.index)
        if isinstance(payment, pd.Series)
        else set(payment.keys())
    )

    missing = (
        required_payment_fields
        - keys
    )

    if missing:
        raise ValueError(
            "Payment is missing required field(s): "
            + ", ".join(sorted(missing))
        )

    ranked = []

    for _, candidate in settlements.iterrows():

        if not _amount_is_close(
            payment["amount"],
            candidate["gross_amount"],
        ):
            continue

        distance = date_distance_days(
            payment["payment_date"],
            candidate["settlement_date"],
        )

        if (
            distance is not None
            and distance
            > PAYMENT_SETTLEMENT_MAX_DATE_DISTANCE
        ):
            continue

        date_score = _date_score(
            distance,
            excellent=3,
            good=7,
            acceptable=10,
        )

        reference_score = (
            _reference_similarity(
                customer_name,
                candidate["reference"],
            )
        )

        score = weighted_score(
            amount=100.0,
            customer=reference_score,
            date=date_score,
            reference=reference_score,
            amount_weight=0.45,
            customer_weight=0.15,
            date_weight=0.25,
            reference_weight=0.15,
        )

        settlement_id = (
            canonical_exact_identifier(
                candidate["settlement_id"]
            )
        )

        ranked.append(
            (
                score,
                settlement_id,
                {
                    "amount_score": 100.0,
                    "date_score":
                        round(date_score, 2),

                    "reference_score":
                        round(reference_score, 2),

                    "date_distance_days":
                        distance,
                },
                candidate,
            )
        )

    return _decision_from_ranked_candidates(
        ranked
    )


# ============================================================
# SETTLEMENT -> BANK FUZZY RECOVERY
# ============================================================


def fuzzy_match_settlement_to_bank(
    settlement: Mapping[str, Any] | pd.Series,
    bank_transactions: pd.DataFrame,
    *,
    customer_name: str,
) -> tuple[
    MatchDecision,
    pd.Series | None,
]:
    """
    Recover settlement-to-bank relationships when the bank
    record does not expose settlement_id.

    Evidence:
        50% amount
        20% date
        30% bank reference/description
    """

    require_columns(
        bank_transactions,
        {
            "bank_txn_id",
            "settlement_id",
            "reference",
            "amount",
            "transaction_date",
            "description",
        },
        dataset_name="bank_transactions",
    )

    required_settlement_fields = {
        "settlement_id",
        "expected_net",
        "settlement_date",
    }

    keys = (
        set(settlement.index)
        if isinstance(settlement, pd.Series)
        else set(settlement.keys())
    )

    missing = (
        required_settlement_fields
        - keys
    )

    if missing:
        raise ValueError(
            "Settlement is missing required field(s): "
            + ", ".join(sorted(missing))
        )

    ranked = []

    for _, candidate in bank_transactions.iterrows():

        if not _amount_is_close(
            settlement["expected_net"],
            candidate["amount"],
        ):
            continue

        distance = date_distance_days(
            settlement["settlement_date"],
            candidate["transaction_date"],
        )

        if (
            distance is not None
            and distance
            > SETTLEMENT_BANK_MAX_DATE_DISTANCE
        ):
            continue

        date_score = _date_score(
            distance,
            excellent=3,
            good=7,
            acceptable=14,
        )

        combined_reference = (
            f"{candidate['reference']} "
            f"{candidate['description']}"
        )

        reference_score = (
            _reference_similarity(
                customer_name,
                combined_reference,
            )
        )

        score = weighted_score(
            amount=100.0,
            customer=reference_score,
            date=date_score,
            reference=reference_score,
            amount_weight=0.50,
            customer_weight=0.15,
            date_weight=0.20,
            reference_weight=0.15,
        )

        bank_txn_id = (
            canonical_exact_identifier(
                candidate["bank_txn_id"]
            )
        )

        ranked.append(
            (
                score,
                bank_txn_id,
                {
                    "amount_score": 100.0,
                    "date_score":
                        round(date_score, 2),

                    "reference_score":
                        round(reference_score, 2),

                    "date_distance_days":
                        distance,
                },
                candidate,
            )
        )

    return _decision_from_ranked_candidates(
        ranked
    )