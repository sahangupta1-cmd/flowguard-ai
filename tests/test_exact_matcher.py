import pandas as pd
import pytest

from backend.app.reconciliation.exact_matcher import (
    canonical_exact_identifier,
    exact_matches,
    extract_record_ids,
    match_invoice_to_payments,
    match_payment_to_settlements,
    match_settlement_to_bank_transactions,
)


# ============================================================
# FIXTURES
# ============================================================


@pytest.fixture
def payments():
    return pd.DataFrame(
        [
            {
                "payment_id": "PAY-001",
                "invoice_id": "INV-001",
                "amount": 10000,
            },
            {
                "payment_id": "PAY-002",
                "invoice_id": "INV-002",
                "amount": 20000,
            },
        ]
    )


@pytest.fixture
def settlements():
    return pd.DataFrame(
        [
            {
                "settlement_id": "SET-001",
                "payment_id": "PAY-001",
                "expected_net": 9764,
            }
        ]
    )


@pytest.fixture
def banks():
    return pd.DataFrame(
        [
            {
                "bank_txn_id": "BNK-001",
                "settlement_id": "SET-001",
                "amount": 9764,
            }
        ]
    )


# ============================================================
# TESTS
# ============================================================


def test_identifier_cleanup_is_conservative():

    assert (
        canonical_exact_identifier(" pay-001 ")
        == "PAY-001"
    )

    assert (
        canonical_exact_identifier("PAY001")
        != canonical_exact_identifier("PAY-001")
    )


def test_invoice_matches_exact_payment(
    payments,
):

    invoice = {
        "invoice_id": "INV-001",
    }

    matches = match_invoice_to_payments(
        invoice,
        payments,
    )

    assert len(matches) == 1

    assert (
        matches.iloc[0]["payment_id"]
        == "PAY-001"
    )


def test_multiple_exact_payments_are_preserved():

    payments = pd.DataFrame(
        [
            {
                "payment_id": "PAY-001",
                "invoice_id": "INV-001",
                "amount": 10000,
            },
            {
                "payment_id": "PAY-002",
                "invoice_id": "INV-001",
                "amount": 10000,
            },
        ]
    )

    invoice = {
        "invoice_id": "INV-001",
    }

    matches = match_invoice_to_payments(
        invoice,
        payments,
    )

    assert len(matches) == 2

    assert extract_record_ids(
        matches,
        id_field="payment_id",
    ) == [
        "PAY-001",
        "PAY-002",
    ]


def test_blank_identifier_does_not_match(
    payments,
):

    invoice = {
        "invoice_id": "",
    }

    matches = match_invoice_to_payments(
        invoice,
        payments,
    )

    assert matches.empty


def test_payment_matches_settlement(
    settlements,
):

    payment = {
        "payment_id": "PAY-001",
    }

    matches = match_payment_to_settlements(
        payment,
        settlements,
    )

    assert len(matches) == 1

    assert (
        matches.iloc[0]["settlement_id"]
        == "SET-001"
    )


def test_settlement_matches_bank(
    banks,
):

    settlement = {
        "settlement_id": "SET-001",
    }

    matches = (
        match_settlement_to_bank_transactions(
            settlement,
            banks,
        )
    )

    assert len(matches) == 1

    assert (
        matches.iloc[0]["bank_txn_id"]
        == "BNK-001"
    )


def test_exact_match_does_not_perform_fuzzy_matching():

    payments = pd.DataFrame(
        [
            {
                "payment_id": "PAY-001",
                "invoice_id": "INV001",
                "amount": 10000,
            }
        ]
    )

    invoice = {
        "invoice_id": "INV-001",
    }

    matches = match_invoice_to_payments(
        invoice,
        payments,
    )

    assert matches.empty


def test_missing_schema_raises_error():

    broken_payments = pd.DataFrame(
        [
            {
                "amount": 10000,
            }
        ]
    )

    invoice = {
        "invoice_id": "INV-001",
    }

    with pytest.raises(
        ValueError,
        match="missing required column",
    ):
        match_invoice_to_payments(
            invoice,
            broken_payments,
        )