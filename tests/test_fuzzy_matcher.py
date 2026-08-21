import pandas as pd

from backend.app.reconciliation.confidence import (
    ConfidenceBand,
)
from backend.app.reconciliation.fuzzy_matcher import (
    fuzzy_match_invoice_to_payment,
    fuzzy_match_payment_to_settlement,
    fuzzy_match_settlement_to_bank,
)


def test_recovers_invoice_payment_with_missing_invoice_id():

    invoice = {
        "invoice_id": "INV-001",
        "customer_id": "C001",
        "customer_name":
            "Nova Technologies Pvt Ltd",
        "invoice_amount": 100000,
        "due_date": "2026-08-10",
    }

    payments = pd.DataFrame(
        [
            {
                "payment_id": "PAY-001",
                "invoice_id": "",
                "customer_id": "C001",
                "amount": 100000,
                "payment_date": "2026-08-12",
                "reference":
                    "NOVA TECH PVT LTD 100000",
            }
        ]
    )

    decision, row = (
        fuzzy_match_invoice_to_payment(
            invoice,
            payments,
        )
    )

    assert decision.matched is True

    assert (
        decision.record_id
        == "PAY-001"
    )

    assert row is not None

    assert (
        decision.evidence[
            "confidence_band"
        ]
        == ConfidenceBand.AUTO_MATCH.value
    )


def test_conflicting_customer_is_not_matched():

    invoice = {
        "invoice_id": "INV-001",
        "customer_id": "C001",
        "customer_name":
            "Nova Technologies Pvt Ltd",
        "invoice_amount": 100000,
        "due_date": "2026-08-10",
    }

    payments = pd.DataFrame(
        [
            {
                "payment_id": "PAY-001",
                "invoice_id": "",
                "customer_id": "C999",
                "amount": 100000,
                "payment_date": "2026-08-10",
                "reference":
                    "NOVA TECH PVT LTD",
            }
        ]
    )

    decision, row = (
        fuzzy_match_invoice_to_payment(
            invoice,
            payments,
        )
    )

    assert decision.matched is False

    assert row is None


def test_material_amount_difference_is_rejected():

    invoice = {
        "invoice_id": "INV-001",
        "customer_id": "C001",
        "customer_name":
            "Nova Technologies Pvt Ltd",
        "invoice_amount": 100000,
        "due_date": "2026-08-10",
    }

    payments = pd.DataFrame(
        [
            {
                "payment_id": "PAY-001",
                "invoice_id": "",
                "customer_id": "C001",
                "amount": 95000,
                "payment_date": "2026-08-10",
                "reference":
                    "NOVA TECH PVT LTD",
            }
        ]
    )

    decision, row = (
        fuzzy_match_invoice_to_payment(
            invoice,
            payments,
        )
    )

    assert decision.matched is False

    assert row is None


def test_ambiguous_candidates_are_not_auto_matched():

    invoice = {
        "invoice_id": "INV-001",
        "customer_id": "C001",
        "customer_name":
            "Nova Technologies Pvt Ltd",
        "invoice_amount": 100000,
        "due_date": "2026-08-10",
    }

    payments = pd.DataFrame(
        [
            {
                "payment_id": "PAY-001",
                "invoice_id": "",
                "customer_id": "C001",
                "amount": 100000,
                "payment_date": "2026-08-10",
                "reference":
                    "NOVA TECH PVT LTD",
            },
            {
                "payment_id": "PAY-002",
                "invoice_id": "",
                "customer_id": "C001",
                "amount": 100000,
                "payment_date": "2026-08-10",
                "reference":
                    "NOVA TECH PVT LTD",
            },
        ]
    )

    decision, row = (
        fuzzy_match_invoice_to_payment(
            invoice,
            payments,
        )
    )

    assert decision.matched is False

    assert decision.requires_review is True

    assert row is not None


def test_recovers_payment_settlement():

    payment = {
        "payment_id": "PAY-001",
        "amount": 100000,
        "payment_date": "2026-08-10",
    }

    settlements = pd.DataFrame(
        [
            {
                "settlement_id": "SET-001",
                "payment_id": "",
                "gross_amount": 100000,
                "settlement_date": "2026-08-12",
                "reference":
                    "NOVA TECH PVT LTD 100000",
            }
        ]
    )

    decision, row = (
        fuzzy_match_payment_to_settlement(
            payment,
            settlements,
            customer_name=
                "Nova Technologies Pvt Ltd",
        )
    )

    assert decision.matched is True

    assert (
        decision.record_id
        == "SET-001"
    )

    assert row is not None


def test_recovers_settlement_bank_transaction():

    settlement = {
        "settlement_id": "SET-001",
        "expected_net": 97640,
        "settlement_date": "2026-08-12",
    }

    banks = pd.DataFrame(
        [
            {
                "bank_txn_id": "BNK-001",
                "settlement_id": "",
                "reference":
                    "NOVA TECH SETTLEMENT",
                "amount": 97640,
                "transaction_date":
                    "2026-08-12",
                "description":
                    "Settlement credit Nova Tech",
            }
        ]
    )

    decision, row = (
        fuzzy_match_settlement_to_bank(
            settlement,
            banks,
            customer_name=
                "Nova Technologies Pvt Ltd",
        )
    )

    assert decision.matched is True

    assert (
        decision.record_id
        == "BNK-001"
    )

    assert row is not None