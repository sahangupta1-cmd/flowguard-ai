from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from .normalizers import is_blank


# ============================================================
# SCHEMA VALIDATION
# ============================================================


def require_columns(
    dataframe: pd.DataFrame,
    required_columns: set[str],
    *,
    dataset_name: str,
) -> None:
    """
    Ensure that an operational dataset contains the fields
    required by a reconciliation step.

    Missing schema is treated as a data-quality failure rather
    than silently producing an empty reconciliation result.
    """

    missing = required_columns - set(dataframe.columns)

    if missing:
        missing_text = ", ".join(sorted(missing))

        raise ValueError(
            f"{dataset_name} is missing required "
            f"column(s): {missing_text}"
        )


# ============================================================
# IDENTIFIER NORMALIZATION
# ============================================================


def canonical_exact_identifier(
    value: Any,
) -> str:
    """
    Canonicalize an identifier for exact matching.

    IMPORTANT:
    This intentionally performs only conservative cleanup:

        - trim whitespace
        - convert to uppercase

    It does NOT remove punctuation or rewrite the identifier.

    Example:
        " pay-001 " -> "PAY-001"

    But:
        "PAY-001" != "PAY001"

    More aggressive recovery belongs in the fuzzy/recovery
    layer, not the exact matcher.
    """

    if is_blank(value):
        return ""

    return str(value).strip().upper()


# ============================================================
# GENERIC EXACT MATCH
# ============================================================


def exact_matches(
    records: pd.DataFrame,
    *,
    target_field: str,
    source_value: Any,
    id_field: str,
    dataset_name: str,
) -> pd.DataFrame:
    """
    Return every operational record whose target field exactly
    matches the supplied source identifier.

    Multiple matches are intentionally preserved.

    Why?
    An invoice might legitimately have:
        - multiple installments
        - a duplicate payment
        - multiple financial events

    Classification of those situations belongs to the
    root-cause layer, not the matcher.
    """

    require_columns(
        records,
        {
            target_field,
            id_field,
        },
        dataset_name=dataset_name,
    )

    source_identifier = canonical_exact_identifier(
        source_value
    )

    if not source_identifier:
        return records.iloc[0:0].copy()

    normalized_targets = (
        records[target_field]
        .astype("string")
        .fillna("")
        .str.strip()
        .str.upper()
    )

    matches = records.loc[
        normalized_targets == source_identifier
    ].copy()

    return matches.reset_index(
        drop=True
    )


# ============================================================
# INVOICE -> PAYMENT
# ============================================================


def match_invoice_to_payments(
    invoice: Mapping[str, Any] | pd.Series,
    payments: pd.DataFrame,
) -> pd.DataFrame:
    """
    Find payments directly linked to an invoice through
    invoice_id.

    No amount/date guessing occurs here.
    """

    if "invoice_id" not in invoice:
        raise ValueError(
            "Invoice record is missing invoice_id."
        )

    return exact_matches(
        payments,
        target_field="invoice_id",
        source_value=invoice["invoice_id"],
        id_field="payment_id",
        dataset_name="payments",
    )


# ============================================================
# PAYMENT -> SETTLEMENT
# ============================================================


def match_payment_to_settlements(
    payment: Mapping[str, Any] | pd.Series,
    settlements: pd.DataFrame,
) -> pd.DataFrame:
    """
    Find settlements directly linked to a payment through
    payment_id.
    """

    if "payment_id" not in payment:
        raise ValueError(
            "Payment record is missing payment_id."
        )

    return exact_matches(
        settlements,
        target_field="payment_id",
        source_value=payment["payment_id"],
        id_field="settlement_id",
        dataset_name="settlements",
    )


# ============================================================
# SETTLEMENT -> BANK TRANSACTION
# ============================================================


def match_settlement_to_bank_transactions(
    settlement: Mapping[str, Any] | pd.Series,
    bank_transactions: pd.DataFrame,
) -> pd.DataFrame:
    """
    Find bank credits directly linked to a settlement through
    settlement_id.
    """

    if "settlement_id" not in settlement:
        raise ValueError(
            "Settlement record is missing settlement_id."
        )

    return exact_matches(
        bank_transactions,
        target_field="settlement_id",
        source_value=settlement["settlement_id"],
        id_field="bank_txn_id",
        dataset_name="bank_transactions",
    )


# ============================================================
# RESULT HELPERS
# ============================================================


def extract_record_ids(
    records: pd.DataFrame,
    *,
    id_field: str,
) -> list[str]:
    """
    Safely extract matched operational identifiers.
    """

    if id_field not in records.columns:
        raise ValueError(
            f"Cannot extract IDs: missing {id_field}."
        )

    result: list[str] = []

    for value in records[id_field]:

        identifier = canonical_exact_identifier(
            value
        )

        if identifier:
            result.append(identifier)

    return result