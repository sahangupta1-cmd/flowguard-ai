import pandas as pd

from backend.app.reconciliation.settlement_matcher import (
    ReconciliationLinker,
)


# ============================================================
# HELPERS
# ============================================================


def make_invoice(
    *,
    invoice_id="INV001",
    customer_id="C001",
    customer_name="Nova Technologies Pvt Ltd",
    amount=100000,
):

    return pd.Series(
        {
            "invoice_id": invoice_id,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "invoice_amount": amount,
            "issue_date": "2026-08-01",
            "due_date": "2026-08-10",
            "payment_policy": "FULL_ONLY",
            "currency": "INR",
        }
    )


def make_linker():

    payments = pd.DataFrame(
        [
            {
                "payment_id": "PAY001",
                "invoice_id": "INV001",
                "customer_id": "C001",
                "amount": 100000,
                "payment_date": "2026-08-10",
                "payment_method": "UPI",
                "payment_status": "SUCCESS",
                "reference": "REF-INV001-PAY001",
            }
        ]
    )

    settlements = pd.DataFrame(
        [
            {
                "settlement_id": "SET001",
                "payment_id": "PAY001",
                "gross_amount": 100000,
                "gateway_fee": 0,
                "gst_on_fee": 0,
                "refund_adjustment": 0,
                "chargeback_adjustment": 0,
                "other_adjustment": 0,
                "expected_net": 100000,
                "settlement_date": "2026-08-12",
                "reference": "STL-PAY001",
            }
        ]
    )

    banks = pd.DataFrame(
        [
            {
                "bank_txn_id": "BNK001",
                "settlement_id": "SET001",
                "reference": "BANK-SET001",
                "amount": 100000,
                "transaction_date": "2026-08-12",
                "description":
                    "Settlement credit Nova Tech",
            }
        ]
    )

    return ReconciliationLinker(
        payments=payments,
        settlements=settlements,
        bank_transactions=banks,
    )


# ============================================================
# EXACT CHAIN
# ============================================================


def test_complete_exact_chain():

    linker = make_linker()

    chain = linker.resolve_invoice(
        make_invoice()
    )

    assert len(chain.payments) == 1
    assert len(chain.settlements) == 1
    assert len(chain.bank_transactions) == 1

    assert chain.requires_review is False

    assert (
        chain.payments.iloc[0][
            "payment_id"
        ]
        == "PAY001"
    )

    assert (
        chain.settlements.iloc[0][
            "settlement_id"
        ]
        == "SET001"
    )

    assert (
        chain.bank_transactions.iloc[0][
            "bank_txn_id"
        ]
        == "BNK001"
    )

    assert len(chain.trace) == 3


# ============================================================
# FUZZY CHAIN
# ============================================================


def test_complete_fuzzy_recovery_chain():

    payments = pd.DataFrame(
        [
            {
                "payment_id": "PAY001",
                "invoice_id": "",
                "customer_id": "C001",
                "amount": 100000,
                "payment_date": "2026-08-10",
                "payment_method": "UPI",
                "payment_status": "SUCCESS",
                "reference":
                    "NOVA TECH PVT LTD 100000",
            }
        ]
    )

    settlements = pd.DataFrame(
        [
            {
                "settlement_id": "SET001",
                "payment_id": "",
                "gross_amount": 100000,
                "gateway_fee": 0,
                "gst_on_fee": 0,
                "refund_adjustment": 0,
                "chargeback_adjustment": 0,
                "other_adjustment": 0,
                "expected_net": 100000,
                "settlement_date": "2026-08-12",
                "reference":
                    "NOVA TECH PVT LTD 100000",
            }
        ]
    )

    banks = pd.DataFrame(
        [
            {
                "bank_txn_id": "BNK001",
                "settlement_id": "",
                "reference":
                    "NOVA TECH SETTLEMENT",
                "amount": 100000,
                "transaction_date": "2026-08-12",
                "description":
                    "Settlement credit Nova Tech",
            }
        ]
    )

    linker = ReconciliationLinker(
        payments=payments,
        settlements=settlements,
        bank_transactions=banks,
    )

    chain = linker.resolve_invoice(
        make_invoice()
    )

    assert len(chain.payments) == 1
    assert len(chain.settlements) == 1
    assert len(chain.bank_transactions) == 1

    assert chain.requires_review is False

    assert (
        chain.trace[0]["method"]
        == "FUZZY"
    )

    assert (
        chain.trace[1]["method"]
        == "FUZZY"
    )

    assert (
        chain.trace[2]["method"]
        == "FUZZY"
    )


# ============================================================
# AMBIGUITY SAFETY
# ============================================================


def test_ambiguous_payment_is_not_admitted():

    payments = pd.DataFrame(
        [
            {
                "payment_id": "PAY001",
                "invoice_id": "",
                "customer_id": "C001",
                "amount": 100000,
                "payment_date": "2026-08-10",
                "payment_method": "UPI",
                "payment_status": "SUCCESS",
                "reference":
                    "NOVA TECH PVT LTD",
            },
            {
                "payment_id": "PAY002",
                "invoice_id": "",
                "customer_id": "C001",
                "amount": 100000,
                "payment_date": "2026-08-10",
                "payment_method": "UPI",
                "payment_status": "SUCCESS",
                "reference":
                    "NOVA TECH PVT LTD",
            },
        ]
    )

    settlements = pd.DataFrame(
        columns=[
            "settlement_id",
            "payment_id",
            "gross_amount",
            "expected_net",
            "settlement_date",
            "reference",
        ]
    )

    banks = pd.DataFrame(
        columns=[
            "bank_txn_id",
            "settlement_id",
            "reference",
            "amount",
            "transaction_date",
            "description",
        ]
    )

    linker = ReconciliationLinker(
        payments=payments,
        settlements=settlements,
        bank_transactions=banks,
    )

    chain = linker.resolve_invoice(
        make_invoice()
    )

    assert chain.payments.empty

    assert chain.requires_review is True

    assert (
        "PAYMENT_MATCH_REQUIRES_REVIEW"
        in chain.issues
    )


# ============================================================
# DUPLICATE PAYMENT PRESERVATION
# ============================================================


def test_multiple_exact_payments_are_preserved():

    payments = pd.DataFrame(
        [
            {
                "payment_id": "PAY001",
                "invoice_id": "INV001",
                "customer_id": "C001",
                "amount": 100000,
                "payment_date": "2026-08-10",
                "payment_method": "UPI",
                "payment_status": "SUCCESS",
                "reference": "A",
            },
            {
                "payment_id": "PAY002",
                "invoice_id": "INV001",
                "customer_id": "C001",
                "amount": 100000,
                "payment_date": "2026-08-11",
                "payment_method": "UPI",
                "payment_status": "SUCCESS",
                "reference": "B",
            },
        ]
    )

    settlements = pd.DataFrame(
        [
            {
                "settlement_id": "SET001",
                "payment_id": "PAY001",
                "gross_amount": 100000,
                "expected_net": 100000,
                "settlement_date": "2026-08-12",
                "reference": "A",
            },
            {
                "settlement_id": "SET002",
                "payment_id": "PAY002",
                "gross_amount": 100000,
                "expected_net": 100000,
                "settlement_date": "2026-08-13",
                "reference": "B",
            },
        ]
    )

    banks = pd.DataFrame(
        [
            {
                "bank_txn_id": "BNK001",
                "settlement_id": "SET001",
                "reference": "A",
                "amount": 100000,
                "transaction_date": "2026-08-12",
                "description": "A",
            },
            {
                "bank_txn_id": "BNK002",
                "settlement_id": "SET002",
                "reference": "B",
                "amount": 100000,
                "transaction_date": "2026-08-13",
                "description": "B",
            },
        ]
    )

    linker = ReconciliationLinker(
        payments=payments,
        settlements=settlements,
        bank_transactions=banks,
    )

    chain = linker.resolve_invoice(
        make_invoice()
    )

    assert len(chain.payments) == 2
    assert len(chain.settlements) == 2
    assert len(chain.bank_transactions) == 2


# ============================================================
# MISSING BANK RECORD
# ============================================================


def test_missing_bank_is_exposed():

    payments = pd.DataFrame(
        [
            {
                "payment_id": "PAY001",
                "invoice_id": "INV001",
                "customer_id": "C001",
                "amount": 100000,
                "payment_date": "2026-08-10",
                "payment_method": "UPI",
                "payment_status": "SUCCESS",
                "reference": "A",
            }
        ]
    )

    settlements = pd.DataFrame(
        [
            {
                "settlement_id": "SET001",
                "payment_id": "PAY001",
                "gross_amount": 100000,
                "expected_net": 100000,
                "settlement_date": "2026-08-12",
                "reference": "A",
            }
        ]
    )

    banks = pd.DataFrame(
        columns=[
            "bank_txn_id",
            "settlement_id",
            "reference",
            "amount",
            "transaction_date",
            "description",
        ]
    )

    linker = ReconciliationLinker(
        payments=payments,
        settlements=settlements,
        bank_transactions=banks,
    )

    chain = linker.resolve_invoice(
        make_invoice()
    )

    assert len(chain.payments) == 1
    assert len(chain.settlements) == 1

    assert chain.bank_transactions.empty

    assert chain.requires_review is True

    assert (
        "NO_CONFIRMED_BANK_TRANSACTION"
        in chain.issues
    )


# ============================================================
# RECORD REUSE SAFETY
# ============================================================


def test_financial_record_cannot_be_consumed_twice():

    linker = make_linker()

    first = linker.resolve_invoice(
        make_invoice()
    )

    assert len(first.payments) == 1

    second = linker.resolve_invoice(
        make_invoice()
    )

    assert second.payments.empty

    assert second.requires_review is True

    assert any(
        issue.startswith(
            "PAYMENT_ALREADY_CONSUMED"
        )
        for issue in second.issues
    )


# ============================================================
# BATCH OPERATION
# ============================================================


def test_batch_resolution_processes_multiple_invoices():

    payments = pd.DataFrame(
        [
            {
                "payment_id": "PAY001",
                "invoice_id": "INV001",
                "customer_id": "C001",
                "amount": 100000,
                "payment_date": "2026-08-10",
                "reference": "A",
            },
            {
                "payment_id": "PAY002",
                "invoice_id": "INV002",
                "customer_id": "C002",
                "amount": 200000,
                "payment_date": "2026-08-11",
                "reference": "B",
            },
        ]
    )

    settlements = pd.DataFrame(
        [
            {
                "settlement_id": "SET001",
                "payment_id": "PAY001",
                "gross_amount": 100000,
                "expected_net": 100000,
                "settlement_date": "2026-08-12",
                "reference": "A",
            },
            {
                "settlement_id": "SET002",
                "payment_id": "PAY002",
                "gross_amount": 200000,
                "expected_net": 200000,
                "settlement_date": "2026-08-13",
                "reference": "B",
            },
        ]
    )

    banks = pd.DataFrame(
        [
            {
                "bank_txn_id": "BNK001",
                "settlement_id": "SET001",
                "reference": "A",
                "amount": 100000,
                "transaction_date": "2026-08-12",
                "description": "A",
            },
            {
                "bank_txn_id": "BNK002",
                "settlement_id": "SET002",
                "reference": "B",
                "amount": 200000,
                "transaction_date": "2026-08-13",
                "description": "B",
            },
        ]
    )

    invoices = pd.DataFrame(
        [
            {
                "invoice_id": "INV002",
                "customer_id": "C002",
                "customer_name": "Beta Ltd",
                "invoice_amount": 200000,
                "issue_date": "2026-08-01",
                "due_date": "2026-08-11",
                "payment_policy": "FULL_ONLY",
            },
            {
                "invoice_id": "INV001",
                "customer_id": "C001",
                "customer_name": "Nova Ltd",
                "invoice_amount": 100000,
                "issue_date": "2026-08-01",
                "due_date": "2026-08-10",
                "payment_policy": "FULL_ONLY",
            },
        ]
    )

    linker = ReconciliationLinker(
        payments=payments,
        settlements=settlements,
        bank_transactions=banks,
    )

    results = linker.resolve_batch(
        invoices
    )

    assert len(results) == 2

    # Deterministic invoice ordering.
    assert results[0].invoice_id == "INV001"
    assert results[1].invoice_id == "INV002"