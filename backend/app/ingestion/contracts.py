from __future__ import annotations

from dataclasses import dataclass


# ============================================================
# Benchmark / evaluation fields forbidden in operational input
# ============================================================

FORBIDDEN_OPERATIONAL_COLUMNS = {
    "benchmark_id",
    "case_id",
    "stress_id",
    "scenario",
    "true_status",
    "true_root_cause",
    "expected_status",
    "expected_root_cause",
    "expected_match_method",
    "expected_payment_ids",
    "expected_settlement_ids",
    "expected_bank_transaction_ids",
    "should_auto_resolve",
}


# ============================================================
# Dataset contract
# ============================================================

@dataclass(frozen=True)
class CSVContract:
    filename: str
    required_columns: tuple[str, ...]
    optional: bool = False


CONTRACTS: dict[str, CSVContract] = {
    "customers": CSVContract(
        filename="customers.csv",
        required_columns=(
            "customer_id",
            "customer_name",
            "industry",
            "payment_terms_days",
        ),
    ),

    "invoices": CSVContract(
        filename="invoices.csv",
        required_columns=(
            "invoice_id",
            "customer_id",
            "customer_name",
            "invoice_amount",
            "issue_date",
            "due_date",
            "payment_policy",
            "currency",
        ),
    ),

    "payments": CSVContract(
        filename="payments.csv",
        required_columns=(
            "payment_id",
            "invoice_id",
            "customer_id",
            "amount",
            "payment_date",
            "payment_method",
            "payment_status",
            "reference",
        ),
    ),

    "settlements": CSVContract(
        filename="settlements.csv",
        required_columns=(
            "settlement_id",
            "payment_id",
            "gross_amount",
            "gateway_fee",
            "gst_on_fee",
            "refund_adjustment",
            "chargeback_adjustment",
            "other_adjustment",
            "expected_net",
            "settlement_date",
            "reference",
        ),
    ),

    "bank_transactions": CSVContract(
        filename="bank_transactions.csv",
        required_columns=(
            "bank_txn_id",
            "settlement_id",
            "reference",
            "amount",
            "transaction_date",
            "description",
        ),
    ),

    "expenses": CSVContract(
        filename="expenses.csv",
        required_columns=(
            "expense_id",
            "category",
            "vendor",
            "amount",
            "due_date",
            "priority",
            "status",
        ),
    ),

    "refunds": CSVContract(
        filename="refunds.csv",
        required_columns=(
            "refund_id",
            "payment_id",
            "invoice_id",
            "amount",
            "refund_date",
            "refund_status",
        ),
        optional=True,
    ),

    "chargebacks": CSVContract(
        filename="chargebacks.csv",
        required_columns=(
            "chargeback_id",
            "payment_id",
            "amount",
            "chargeback_date",
            "status",
            "reason",
        ),
        optional=True,
    ),
}


# ============================================================
# Common external aliases
# ============================================================

COLUMN_ALIASES: dict[str, str] = {
    # IDs
    "invoice_no": "invoice_id",
    "invoice_number": "invoice_id",
    "inv_id": "invoice_id",

    "client_id": "customer_id",
    "customer_code": "customer_id",
    "client_code": "customer_id",

    "payment_no": "payment_id",
    "payment_reference_id": "payment_id",

    "settlement_no": "settlement_id",
    "settlement_reference_id": "settlement_id",

    "bank_transaction_id": "bank_txn_id",
    "transaction_id": "bank_txn_id",
    "txn_id": "bank_txn_id",

    # Names
    "client_name": "customer_name",
    "customer": "customer_name",

    # Invoice amount
    "total_amount": "invoice_amount",
    "invoice_value": "invoice_amount",
    "invoice_total": "invoice_amount",

    # Generic payment / bank amount
    "paid_amount": "amount",
    "payment_amount": "amount",
    "transaction_amount": "amount",
    "txn_amount": "amount",

    # Dates
    "invoice_date": "issue_date",
    "issued_date": "issue_date",

    "payment_due_date": "due_date",
    "invoice_due_date": "due_date",

    "paid_date": "payment_date",
    "txn_date": "transaction_date",
    "bank_date": "transaction_date",

    # References
    "bank_reference": "reference",
    "payment_reference": "reference",
    "txn_reference": "reference",

    # Other common fields
    "method": "payment_method",
    "payment_type": "payment_method",

    "payment_state": "payment_status",

    "expense_type": "category",
    "supplier": "vendor",

    "expense_due_date": "due_date",
}


# ============================================================
# Field categories used during normalization
# ============================================================

MONEY_COLUMNS = {
    "invoice_amount",
    "amount",
    "gross_amount",
    "gateway_fee",
    "gst_on_fee",
    "refund_adjustment",
    "chargeback_adjustment",
    "other_adjustment",
    "expected_net",
}


DATE_COLUMNS = {
    "issue_date",
    "due_date",
    "payment_date",
    "settlement_date",
    "transaction_date",
    "refund_date",
    "chargeback_date",
}


IDENTIFIER_COLUMNS = {
    "customer_id",
    "invoice_id",
    "payment_id",
    "settlement_id",
    "bank_txn_id",
    "refund_id",
    "chargeback_id",
}


# ============================================================
# Legitimately missing linkage fields
# ============================================================
#
# These are relationship/linking identifiers that may be absent
# in operational finance data. Their absence is information for
# the reconciliation engine to recover or send for review.
#
# Primary record identifiers remain mandatory.
#
ALLOW_BLANK_FIELDS: dict[str, frozenset[str]] = {
    "payments": frozenset({
        "invoice_id",
    }),
    "settlements": frozenset({
        "payment_id",
    }),
    "bank_transactions": frozenset({
        "settlement_id",
    }),
}
