from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.app.cashflow.engine import CashImpactEngine


def test_cashflow_forecast_basic(monkeypatch):
    engine = CashImpactEngine(
        as_of_date=date(2026, 8, 1)
    )

    predictions = [
        SimpleNamespace(
            expected_payment_date=date(2026, 8, 5),
            amount_at_risk=Decimal("100000.00"),
        ),
        SimpleNamespace(
            expected_payment_date=date(2026, 8, 10),
            amount_at_risk=Decimal("50000.00"),
        ),
    ]

    monkeypatch.setattr(
        engine.predictor,
        "predict_open_invoices",
        lambda **kwargs: predictions,
    )

    expenses = pd.DataFrame(
        [
            {
                "expense_id": "EXP001",
                "category": "RENT",
                "vendor": "Vendor 1",
                "amount": 30000,
                "due_date": pd.Timestamp("2026-08-06"),
                "priority": "HIGH",
                "status": "SCHEDULED",
                "_amount_decimal": Decimal("30000.00"),
            }
        ]
    )

    monkeypatch.setattr(
        engine,
        "_load_expenses",
        lambda: expenses,
    )

    result = engine.forecast(
        opening_cash_balance="20000.00",
        horizon_days=15,
    )

    assert (
        result.total_expected_inflows
        == Decimal("150000.00")
    )

    assert (
        result.total_scheduled_outflows
        == Decimal("30000.00")
    )

    assert (
        result.projected_ending_balance
        == Decimal("140000.00")
    )

    assert result.shortfall_detected is False


def test_cashflow_detects_shortfall(monkeypatch):
    engine = CashImpactEngine(
        as_of_date=date(2026, 8, 1)
    )

    predictions = [
        SimpleNamespace(
            expected_payment_date=date(2026, 8, 20),
            amount_at_risk=Decimal("100000.00"),
        )
    ]

    monkeypatch.setattr(
        engine.predictor,
        "predict_open_invoices",
        lambda **kwargs: predictions,
    )

    expenses = pd.DataFrame(
        [
            {
                "expense_id": "EXP001",
                "category": "RENT",
                "vendor": "Vendor 1",
                "amount": 80000,
                "due_date": pd.Timestamp("2026-08-05"),
                "priority": "CRITICAL",
                "status": "SCHEDULED",
                "_amount_decimal": Decimal("80000.00"),
            }
        ]
    )

    monkeypatch.setattr(
        engine,
        "_load_expenses",
        lambda: expenses,
    )

    result = engine.forecast(
        opening_cash_balance="10000.00",
        horizon_days=30,
    )

    assert result.shortfall_detected is True

    assert (
        result.first_shortfall_date
        == date(2026, 8, 5)
    )

    assert (
        result.maximum_shortfall
        == Decimal("70000.00")
    )


def test_negative_opening_balance_rejected():
    engine = CashImpactEngine()

    with pytest.raises(ValueError):
        engine.forecast(
            opening_cash_balance="-1.00"
        )


def test_invalid_horizon_rejected():
    engine = CashImpactEngine()

    with pytest.raises(ValueError):
        engine.forecast(
            opening_cash_balance="1000.00",
            horizon_days=0,
        )