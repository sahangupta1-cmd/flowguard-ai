from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.app.cashflow.impact_analyzer import (
    CashDelayImpactAnalyzer,
)


def test_liquidity_gap_metrics():
    result = (
        CashDelayImpactAnalyzer
        ._liquidity_gap_metrics(
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 5),
            baseline_inflows={
                date(2026, 8, 1):
                    Decimal("100000.00"),
            },
            predicted_inflows={
                date(2026, 8, 4):
                    Decimal("100000.00"),
            },
        )
    )

    assert (
        result["maximum_temporary_cash_gap"]
        == Decimal("100000.00")
    )

    assert (
        result["maximum_gap_date"]
        == date(2026, 8, 1)
    )

    assert (
        result["days_with_reduced_liquidity"]
        == 3
    )


def test_delay_impact_analysis(monkeypatch):
    analyzer = CashDelayImpactAnalyzer(
        as_of_date=date(2026, 8, 1)
    )

    predictions = [
        SimpleNamespace(
            invoice_id="INV001",
            expected_payment_date=date(
                2026,
                8,
                10,
            ),
        )
    ]

    open_invoices = pd.DataFrame(
        [
            {
                "invoice_id": "INV001",
                "customer_id": "C001",
                "invoice_amount": 100000,
                "due_date": "2026-08-03",
                "total_paid": 0,
            }
        ]
    )

    expenses = pd.DataFrame(
        [
            {
                "expense_id": "EXP001",
                "category": "RENT",
                "vendor": "Vendor 1",
                "amount": 50000,
                "due_date": pd.Timestamp(
                    "2026-08-05"
                ),
                "priority": "HIGH",
                "status": "SCHEDULED",
                "_amount_decimal":
                    Decimal("50000.00"),
            }
        ]
    )

    monkeypatch.setattr(
        analyzer.predictor,
        "predict_open_invoices",
        lambda **kwargs: predictions,
    )

    monkeypatch.setattr(
        analyzer.predictor,
        "open_invoices",
        lambda **kwargs: open_invoices,
    )

    monkeypatch.setattr(
        analyzer,
        "_load_expenses",
        lambda: expenses,
    )

    result = analyzer.analyze(
        opening_cash_balance="20000.00",
        horizon_days=20,
    )

    impact = result["delay_impact"]

    assert (
        impact["maximum_temporary_cash_gap"]
        == "100000.00"
    )

    assert (
        impact["maximum_gap_date"]
        == "2026-08-03"
    )

    assert (
        impact["cash_delayed_by_first_expense"]
        == "100000.00"
    )

    assert (
        impact["incremental_shortfall"]
        == "30000.00"
    )


def test_real_dataset_cash_impact():
    analyzer = CashDelayImpactAnalyzer()

    result = analyzer.analyze(
        opening_cash_balance="500000.00",
        horizon_days=90,
    )

    assert (
        result["delay_impact"][
            "maximum_temporary_cash_gap"
        ]
        == "4018225.00"
    )

    assert (
        result["delay_impact"][
            "maximum_gap_date"
        ]
        == "2026-08-04"
    )

    assert (
        result["delay_impact"][
            "days_with_reduced_liquidity"
        ]
        == 39
    )

    assert (
        result["delay_impact"][
            "cash_delayed_by_first_expense"
        ]
        == "973600.00"
    )


def test_invalid_horizon_rejected():
    analyzer = CashDelayImpactAnalyzer()

    with pytest.raises(ValueError):
        analyzer.analyze(
            opening_cash_balance="100000.00",
            horizon_days=0,
        )


def test_negative_opening_cash_rejected():
    analyzer = CashDelayImpactAnalyzer()

    with pytest.raises(ValueError):
        analyzer.analyze(
            opening_cash_balance="-500.00"
        )