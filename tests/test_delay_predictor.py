from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from backend.app.prediction.delay_predictor import DelayPredictor


CUTOFF = date(2026, 8, 1)


def test_history_contains_only_information_available_before_cutoff() -> None:
    predictor = DelayPredictor(
        as_of_date=CUTOFF
    )

    history = predictor.build_history()

    assert not history.empty

    cutoff = pd.Timestamp(CUTOFF)

    assert (
        history["completion_date"]
        <= cutoff
    ).all()


def test_open_invoices_are_valid_at_cutoff() -> None:
    predictor = DelayPredictor(
        as_of_date=CUTOFF
    )

    open_invoices = predictor.open_invoices()

    assert not open_invoices.empty

    cutoff = pd.Timestamp(CUTOFF)

    assert (
        open_invoices["issue_date"]
        <= cutoff
    ).all()

    assert (
        ~open_invoices["_paid_by_cutoff"]
    ).all()


def test_predictions_have_valid_financial_ranges() -> None:
    predictor = DelayPredictor(
        as_of_date=CUTOFF
    )

    predictions = (
        predictor.predict_open_invoices()
    )

    assert predictions

    for prediction in predictions:
        assert (
            prediction.expected_delay_days
            >= 0
        )

        assert (
            0.0
            <= prediction.late_probability
            <= 100.0
        )

        assert (
            0.0
            <= prediction.confidence
            <= 100.0
        )

        assert prediction.history_count >= 0

        assert (
            prediction.amount_at_risk
            >= Decimal("0.00")
        )

        assert (
            prediction.amount_at_risk
            <= prediction.invoice_amount
        )


def test_expected_payment_date_matches_delay() -> None:
    predictor = DelayPredictor(
        as_of_date=CUTOFF
    )

    predictions = (
        predictor.predict_open_invoices()
    )

    assert predictions

    for prediction in predictions:
        expected_date = (
            prediction.due_date
            + timedelta(
                days=(
                    prediction.expected_delay_days
                )
            )
        )

        assert (
            prediction.expected_payment_date
            == expected_date
        )


def test_partial_payment_uses_only_outstanding_amount() -> None:
    predictor = DelayPredictor()

    invoice = pd.Series(
        {
            "invoice_id": "INV-TEST",
            "customer_id": "C-TEST",
            "invoice_amount": "1000.00",
            "due_date": "2026-08-10",
            "total_paid": Decimal("250.00"),
        }
    )

    history = pd.DataFrame(
        {
            "customer_id": [
                "C-TEST",
                "C-TEST",
                "C-TEST",
            ],
            "delay_days": [
                4,
                6,
                8,
            ],
        }
    )

    prediction = predictor.predict_invoice(
        invoice,
        history=history,
    )

    assert prediction.expected_delay_days > 0

    assert (
        prediction.amount_at_risk
        == Decimal("750.00")
    )


def test_future_payment_is_not_visible_at_cutoff(
    tmp_path,
) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    invoices = pd.DataFrame(
        [
            {
                "invoice_id": "INV001",
                "customer_id": "C001",
                "invoice_amount": "1000.00",
                "issue_date": "2026-07-01",
                "due_date": "2026-07-20",
            }
        ]
    )

    payments = pd.DataFrame(
        [
            {
                "payment_id": "PAY001",
                "invoice_id": "INV001",
                "amount": "400.00",
                "payment_date": "2026-07-25",
                "payment_status": "SUCCESS",
            },
            {
                "payment_id": "PAY002",
                "invoice_id": "INV001",
                "amount": "600.00",
                "payment_date": "2026-08-05",
                "payment_status": "SUCCESS",
            },
        ]
    )

    invoices.to_csv(
        raw_dir / "invoices.csv",
        index=False,
    )

    payments.to_csv(
        raw_dir / "payments.csv",
        index=False,
    )

    predictor = DelayPredictor(
        raw_dir=raw_dir,
        as_of_date=CUTOFF,
    )

    open_invoices = predictor.open_invoices()

    assert len(open_invoices) == 1

    invoice = open_invoices.iloc[0]

    assert (
        invoice["total_paid"]
        == Decimal("400.00")
    )

    assert pd.isna(
        invoice["completion_date"]
    )


def test_benchmark_columns_are_rejected(
    tmp_path,
) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    invoices = pd.DataFrame(
        [
            {
                "invoice_id": "INV001",
                "customer_id": "C001",
                "invoice_amount": "1000.00",
                "issue_date": "2026-07-01",
                "due_date": "2026-07-20",
                "scenario": "LEAKED_LABEL",
            }
        ]
    )

    payments = pd.DataFrame(
        [
            {
                "payment_id": "PAY001",
                "invoice_id": "INV001",
                "amount": "1000.00",
                "payment_date": "2026-07-21",
            }
        ]
    )

    invoices.to_csv(
        raw_dir / "invoices.csv",
        index=False,
    )

    payments.to_csv(
        raw_dir / "payments.csv",
        index=False,
    )

    predictor = DelayPredictor(
        raw_dir=raw_dir
    )

    with pytest.raises(
        ValueError,
        match="Benchmark-labelled columns",
    ):
        predictor.load_data()


def test_prediction_requires_historical_evidence() -> None:
    predictor = DelayPredictor()

    invoice = pd.Series(
        {
            "invoice_id": "INV-TEST",
            "customer_id": "C-TEST",
            "invoice_amount": "1000.00",
            "due_date": "2026-08-10",
            "total_paid": Decimal("0.00"),
        }
    )

    empty_history = pd.DataFrame(
        columns=[
            "customer_id",
            "delay_days",
        ]
    )

    with pytest.raises(
        ValueError,
        match=(
            "No historical completed payments"
        ),
    ):
        predictor.predict_invoice(
            invoice,
            history=empty_history,
        )