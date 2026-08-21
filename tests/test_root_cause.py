import pandas as pd

from backend.app.reconciliation.models import (
    ReconciliationStatus,
    RootCause,
)
from backend.app.reconciliation.root_cause import (
    RootCauseAnalyzer,
)
from backend.app.reconciliation.settlement_matcher import (
    ReconciliationChain,
)


def invoice(
    *,
    amount=100000,
    policy="FULL_ONLY",
):

    return pd.Series(
        {
            "invoice_id": "INV001",
            "invoice_amount": amount,
            "payment_policy": policy,
        }
    )


def empty_refunds():

    return pd.DataFrame(
        columns=[
            "refund_id",
            "payment_id",
            "amount",
            "refund_status",
        ]
    )


def empty_chargebacks():

    return pd.DataFrame(
        columns=[
            "chargeback_id",
            "payment_id",
            "amount",
            "status",
        ]
    )


def analyzer(
    *,
    refunds=None,
    chargebacks=None,
):

    return RootCauseAnalyzer(
        refunds=(
            empty_refunds()
            if refunds is None
            else refunds
        ),
        chargebacks=(
            empty_chargebacks()
            if chargebacks is None
            else chargebacks
        ),
    )


def chain(
    *,
    payments=None,
    settlements=None,
    banks=None,
):

    return ReconciliationChain(
        invoice_id="INV001",

        payments=pd.DataFrame(
            payments or []
        ),

        settlements=pd.DataFrame(
            settlements or []
        ),

        bank_transactions=pd.DataFrame(
            banks or []
        ),
    )


def payment(
    payment_id="PAY001",
    amount=100000,
    payment_date="2026-08-10",
):

    return {
        "payment_id": payment_id,
        "amount": amount,
        "payment_date": payment_date,
    }


def settlement(
    *,
    settlement_id="SET001",
    payment_id="PAY001",
    gross=100000,
    fee=0,
    gst=0,
    refund=0,
    chargeback=0,
    other=0,
    expected=100000,
    date="2026-08-12",
):

    return {
        "settlement_id": settlement_id,
        "payment_id": payment_id,
        "gross_amount": gross,
        "gateway_fee": fee,
        "gst_on_fee": gst,
        "refund_adjustment": refund,
        "chargeback_adjustment": chargeback,
        "other_adjustment": other,
        "expected_net": expected,
        "settlement_date": date,
    }


def bank(
    *,
    bank_id="BNK001",
    settlement_id="SET001",
    amount=100000,
    date="2026-08-12",
):

    return {
        "bank_txn_id": bank_id,
        "settlement_id": settlement_id,
        "amount": amount,
        "transaction_date": date,
    }


def test_clean_reconciliation():

    result = analyzer().analyze(
        invoice(),
        chain(
            payments=[payment()],
            settlements=[settlement()],
            banks=[bank()],
        ),
    )

    assert result.root_cause == RootCause.CLEAN
    assert (
        result.status
        == ReconciliationStatus.RECONCILED
    )


def test_gateway_fee_and_gst():

    result = analyzer().analyze(
        invoice(),
        chain(
            payments=[payment()],
            settlements=[
                settlement(
                    fee=2000,
                    gst=360,
                    expected=97640,
                )
            ],
            banks=[
                bank(
                    amount=97640
                )
            ],
        ),
    )

    assert (
        result.root_cause
        == RootCause.GATEWAY_FEE_GST
    )


def test_full_refund():

    refunds = pd.DataFrame(
        [
            {
                "refund_id": "RF001",
                "payment_id": "PAY001",
                "amount": 100000,
                "refund_status": "PROCESSED",
            }
        ]
    )

    result = analyzer(
        refunds=refunds
    ).analyze(
        invoice(),
        chain(
            payments=[payment()],
            settlements=[
                settlement(
                    refund=100000,
                    expected=0,
                )
            ],
            banks=[
                bank(
                    amount=0
                )
            ],
        ),
    )

    assert (
        result.root_cause
        == RootCause.FULL_REFUND
    )


def test_partial_refund():

    refunds = pd.DataFrame(
        [
            {
                "refund_id": "RF001",
                "payment_id": "PAY001",
                "amount": 20000,
                "refund_status": "PROCESSED",
            }
        ]
    )

    result = analyzer(
        refunds=refunds
    ).analyze(
        invoice(),
        chain(
            payments=[payment()],
            settlements=[
                settlement(
                    refund=20000,
                    expected=80000,
                )
            ],
            banks=[
                bank(
                    amount=80000
                )
            ],
        ),
    )

    assert (
        result.root_cause
        == RootCause.PARTIAL_REFUND
    )


def test_chargeback():

    chargebacks = pd.DataFrame(
        [
            {
                "chargeback_id": "CB001",
                "payment_id": "PAY001",
                "amount": 100000,
                "status": "ACCEPTED",
            }
        ]
    )

    result = analyzer(
        chargebacks=chargebacks
    ).analyze(
        invoice(),
        chain(
            payments=[payment()],
            settlements=[
                settlement(
                    chargeback=100000,
                    expected=0,
                )
            ],
            banks=[
                bank(
                    amount=0
                )
            ],
        ),
    )

    assert (
        result.root_cause
        == RootCause.CHARGEBACK
    )


def test_legitimate_partial_payment():

    result = analyzer().analyze(
        invoice(
            policy="INSTALLMENTS_ALLOWED"
        ),
        chain(
            payments=[
                payment(
                    amount=50000
                )
            ],
            settlements=[
                settlement(
                    gross=50000,
                    expected=50000,
                )
            ],
            banks=[
                bank(
                    amount=50000
                )
            ],
        ),
    )

    assert (
        result.root_cause
        == RootCause.PARTIAL_PAYMENT
    )


def test_amount_mismatch():

    result = analyzer().analyze(
        invoice(
            policy="FULL_ONLY"
        ),
        chain(
            payments=[
                payment(
                    amount=95000
                )
            ],
            settlements=[
                settlement(
                    gross=95000,
                    expected=95000,
                )
            ],
            banks=[
                bank(
                    amount=95000
                )
            ],
        ),
    )

    assert (
        result.root_cause
        == RootCause.AMOUNT_MISMATCH
    )


def test_duplicate_payment():

    result = analyzer().analyze(
        invoice(),
        chain(
            payments=[
                payment(
                    "PAY001",
                    100000,
                    "2026-08-10",
                ),
                payment(
                    "PAY002",
                    100000,
                    "2026-08-11",
                ),
            ],
            settlements=[
                settlement(),
                settlement(
                    settlement_id="SET002",
                    payment_id="PAY002",
                ),
            ],
            banks=[
                bank(),
                bank(
                    bank_id="BNK002",
                    settlement_id="SET002",
                ),
            ],
        ),
    )

    assert (
        result.root_cause
        == RootCause.DUPLICATE_PAYMENT
    )

    assert result.requires_review is True


def test_settlement_delay():

    result = analyzer().analyze(
        invoice(),
        chain(
            payments=[payment()],
            settlements=[settlement()],
            banks=[
                bank(
                    date="2026-08-18"
                )
            ],
        ),
    )

    assert (
        result.root_cause
        == RootCause.SETTLEMENT_DELAY
    )


def test_missing_payment():

    result = analyzer().analyze(
        invoice(),
        chain(),
    )

    assert (
        result.root_cause
        == RootCause.MISSING_PAYMENT
    )


def test_missing_bank_entry():

    result = analyzer().analyze(
        invoice(),
        chain(
            payments=[payment()],
            settlements=[settlement()],
        ),
    )

    assert (
        result.root_cause
        == RootCause.MISSING_BANK_ENTRY
    )


def test_unexplained_bank_difference():

    result = analyzer().analyze(
        invoice(),
        chain(
            payments=[payment()],
            settlements=[settlement()],
            banks=[
                bank(
                    amount=95000
                )
            ],
        ),
    )

    assert (
        result.root_cause
        == RootCause.UNEXPLAINED
    )

    assert (
        result.status
        == ReconciliationStatus.UNRESOLVED
    )


def test_refund_adjustment_without_evidence_requires_review():

    result = analyzer().analyze(
        invoice(),
        chain(
            payments=[payment()],
            settlements=[
                settlement(
                    refund=20000,
                    expected=80000,
                )
            ],
            banks=[
                bank(
                    amount=80000
                )
            ],
        ),
    )

    assert (
        result.root_cause
        == RootCause.UNEXPLAINED
    )

    assert (
        result.status
        == ReconciliationStatus.HUMAN_REVIEW
    )

    assert result.requires_review is True