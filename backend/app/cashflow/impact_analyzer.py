from __future__ import annotations

import json

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd

from backend.app.prediction.delay_predictor import (
    DEFAULT_AS_OF_DATE,
    DEFAULT_RAW_DIR,
    DelayPredictor,
)
from backend.app.reconciliation.normalizers import (
    to_decimal,
)


class CashDelayImpactAnalyzer:
    """
    Compare cash position under two scenarios:

    1. BASELINE:
       outstanding invoices arrive on their contractual due date.
       If already overdue at the as-of date, receipt is assumed
       immediately on the as-of date.

    2. PREDICTED:
       outstanding invoices arrive on FlowGuard's predicted
       payment date.

    This isolates the financial effect caused specifically by
    predicted payment delays.
    """

    def __init__(
        self,
        *,
        raw_dir: Path = DEFAULT_RAW_DIR,
        as_of_date: date = DEFAULT_AS_OF_DATE,
    ) -> None:
        self.raw_dir = Path(raw_dir)
        self.as_of_date = as_of_date

        self.predictor = DelayPredictor(
            raw_dir=self.raw_dir,
            as_of_date=self.as_of_date,
        )

    def _load_expenses(
        self,
    ) -> pd.DataFrame:
        path = self.raw_dir / "expenses.csv"

        if not path.exists():
            raise FileNotFoundError(
                f"Expense dataset not found: {path}"
            )

        expenses = pd.read_csv(path)

        expenses["due_date"] = pd.to_datetime(
            expenses["due_date"],
            errors="raise",
        )

        expenses["_amount_decimal"] = (
            expenses["amount"].map(to_decimal)
        )

        return expenses

    @staticmethod
    def _add_amount(
        ledger: dict[date, Decimal],
        target_date: date,
        amount: Decimal,
    ) -> None:
        ledger[target_date] = (
            ledger.get(
                target_date,
                Decimal("0.00"),
            )
            + amount
        )

    @staticmethod
    def _simulate(
        *,
        opening_cash: Decimal,
        start_date: date,
        end_date: date,
        inflows: dict[date, Decimal],
        outflows: dict[date, Decimal],
    ) -> dict[str, object]:
        balance = opening_cash

        minimum_balance = opening_cash
        minimum_balance_date = start_date

        first_shortfall_date: date | None = None

        current_date = start_date

        while current_date <= end_date:
            balance += inflows.get(
                current_date,
                Decimal("0.00"),
            )

            balance -= outflows.get(
                current_date,
                Decimal("0.00"),
            )

            if balance < minimum_balance:
                minimum_balance = balance
                minimum_balance_date = current_date

            if (
                balance < Decimal("0.00")
                and first_shortfall_date is None
            ):
                first_shortfall_date = current_date

            current_date += timedelta(days=1)

        maximum_shortfall = max(
            Decimal("0.00"),
            -minimum_balance,
        )

        return {
            "ending_balance": balance,
            "minimum_balance": minimum_balance,
            "minimum_balance_date": (
                minimum_balance_date
            ),
            "first_shortfall_date": (
                first_shortfall_date
            ),
            "maximum_shortfall": (
                maximum_shortfall
            ),
        }

    @staticmethod
    def _severity(
        *,
        incremental_shortfall: Decimal,
        minimum_predicted_balance: Decimal,
    ) -> str:
        if (
            incremental_shortfall <= Decimal("0.00")
            and minimum_predicted_balance
            >= Decimal("0.00")
        ):
            return "LOW"

        if minimum_predicted_balance >= Decimal("0.00"):
            return "MEDIUM"

        if incremental_shortfall >= Decimal("250000.00"):
            return "CRITICAL"

        if incremental_shortfall >= Decimal("100000.00"):
            return "HIGH"

        return "MEDIUM"
    @staticmethod
    def _liquidity_gap_metrics(
        *,
        start_date: date,
        end_date: date,
        baseline_inflows: dict[date, Decimal],
        predicted_inflows: dict[date, Decimal],
    ) -> dict[str, object]:
        """
        Measure temporary liquidity displaced by predicted
        payment delays relative to contractual timing.
        """

        baseline_cumulative = Decimal("0.00")
        predicted_cumulative = Decimal("0.00")

        maximum_gap = Decimal("0.00")
        maximum_gap_date: date | None = None

        days_reduced = 0

        current_date = start_date

        while current_date <= end_date:
            baseline_cumulative += (
                baseline_inflows.get(
                    current_date,
                    Decimal("0.00"),
                )
            )

            predicted_cumulative += (
                predicted_inflows.get(
                    current_date,
                    Decimal("0.00"),
                )
            )

            gap = max(
                Decimal("0.00"),
                baseline_cumulative
                - predicted_cumulative,
            )

            if gap > Decimal("0.00"):
                days_reduced += 1

            if gap > maximum_gap:
                maximum_gap = gap
                maximum_gap_date = current_date

            current_date += timedelta(days=1)

        return {
            "maximum_temporary_cash_gap": maximum_gap,
            "maximum_gap_date": maximum_gap_date,
            "days_with_reduced_liquidity": days_reduced,
        }

    def analyze(
        self,
        *,
        opening_cash_balance: Decimal | str | int | float,
        horizon_days: int = 90,
    ) -> dict[str, object]:
        if horizon_days <= 0:
            raise ValueError(
                "horizon_days must be greater than zero."
            )

        opening_cash = to_decimal(
            opening_cash_balance
        )

        if opening_cash < Decimal("0.00"):
            raise ValueError(
                "opening_cash_balance cannot be negative."
            )

        horizon_end = (
            self.as_of_date
            + timedelta(days=horizon_days)
        )

        predictions = (
            self.predictor.predict_open_invoices(
                as_of_date=self.as_of_date
            )
        )

        open_invoices = (
            self.predictor.open_invoices(
                as_of_date=self.as_of_date
            )
        )

        prediction_lookup = {
            prediction.invoice_id: prediction
            for prediction in predictions
        }

        baseline_inflows: dict[
            date,
            Decimal,
        ] = {}

        predicted_inflows: dict[
            date,
            Decimal,
        ] = {}

        total_delayed_receivables = (
            Decimal("0.00")
        )

        delay_days_weighted_amount = (
            Decimal("0.00")
        )

        for _, row in open_invoices.iterrows():
            invoice_id = str(
                row["invoice_id"]
            ).strip()

            prediction = prediction_lookup.get(
                invoice_id
            )

            if prediction is None:
                continue

            invoice_amount = to_decimal(
                row["invoice_amount"]
            )

            total_paid = row.get(
                "total_paid"
            )

            if (
                total_paid is None
                or pd.isna(total_paid)
            ):
                paid = Decimal("0.00")
            else:
                paid = to_decimal(
                    total_paid
                )

            outstanding = max(
                invoice_amount - paid,
                Decimal("0.00"),
            )

            if outstanding <= Decimal("0.00"):
                continue

            due_date = pd.Timestamp(
                row["due_date"]
            ).date()

            baseline_date = max(
                due_date,
                self.as_of_date,
            )

            predicted_date = (
                prediction.expected_payment_date
            )

            if (
                self.as_of_date
                <= baseline_date
                <= horizon_end
            ):
                self._add_amount(
                    baseline_inflows,
                    baseline_date,
                    outstanding,
                )

            if (
                self.as_of_date
                <= predicted_date
                <= horizon_end
            ):
                self._add_amount(
                    predicted_inflows,
                    predicted_date,
                    outstanding,
                )

            delay_days = max(
                0,
                (
                    predicted_date
                    - baseline_date
                ).days,
            )

            if delay_days > 0:
                total_delayed_receivables += (
                    outstanding
                )

                delay_days_weighted_amount += (
                    outstanding
                    * Decimal(delay_days)
                )

        expenses = self._load_expenses()

        expenses = expenses[
            (
                expenses["due_date"]
                >= pd.Timestamp(
                    self.as_of_date
                )
            )
            & (
                expenses["due_date"]
                <= pd.Timestamp(
                    horizon_end
                )
            )
            & (
                expenses["status"]
                .astype(str)
                .str.strip()
                .str.upper()
                == "SCHEDULED"
            )
        ].copy()

        outflows: dict[
            date,
            Decimal,
        ] = {}

        for _, expense in expenses.iterrows():
            expense_date = pd.Timestamp(
                expense["due_date"]
            ).date()

            self._add_amount(
                outflows,
                expense_date,
                expense[
                    "_amount_decimal"
                ],
            )

        baseline = self._simulate(
            opening_cash=opening_cash,
            start_date=self.as_of_date,
            end_date=horizon_end,
            inflows=baseline_inflows,
            outflows=outflows,
        )

        predicted = self._simulate(
            opening_cash=opening_cash,
            start_date=self.as_of_date,
            end_date=horizon_end,
            inflows=predicted_inflows,
            outflows=outflows,
        )
        liquidity_gap = (
            self._liquidity_gap_metrics(
                start_date=self.as_of_date,
                end_date=horizon_end,
                baseline_inflows=baseline_inflows,
                predicted_inflows=predicted_inflows,
            )
        )

        if not expenses.empty:
            first_expense_date = pd.Timestamp(
                expenses["due_date"].min()
            ).date()

            baseline_receipts_by_first_expense = sum(
                (
                    amount
                    for day, amount
                    in baseline_inflows.items()
                    if day <= first_expense_date
                ),
                Decimal("0.00"),
            )

            predicted_receipts_by_first_expense = sum(
                (
                    amount
                    for day, amount
                    in predicted_inflows.items()
                    if day <= first_expense_date
                ),
                Decimal("0.00"),
            )

            cash_delayed_by_first_expense = max(
                Decimal("0.00"),
                baseline_receipts_by_first_expense
                - predicted_receipts_by_first_expense,
            )

        else:
            first_expense_date = None

            cash_delayed_by_first_expense = (
                Decimal("0.00")
            )

        baseline_shortfall = baseline[
            "maximum_shortfall"
        ]

        predicted_shortfall = predicted[
            "maximum_shortfall"
        ]

        incremental_shortfall = max(
            Decimal("0.00"),
            predicted_shortfall
            - baseline_shortfall,
        )

        minimum_balance_deterioration = max(
            Decimal("0.00"),
            baseline["minimum_balance"]
            - predicted["minimum_balance"],
        )

        if total_delayed_receivables > 0:
            weighted_average_delay = (
                delay_days_weighted_amount
                / total_delayed_receivables
            )
        else:
            weighted_average_delay = (
                Decimal("0.00")
            )

        severity = self._severity(
            incremental_shortfall=(
                incremental_shortfall
            ),
            minimum_predicted_balance=(
                predicted[
                    "minimum_balance"
                ]
            ),
        )

        return {
            "as_of_date": self.as_of_date.isoformat(),
            "horizon_end": horizon_end.isoformat(),
            "opening_cash_balance": format(
                opening_cash,
                ".2f",
            ),
            "total_delayed_receivables": format(
                total_delayed_receivables,
                ".2f",
            ),
            "weighted_average_delay_days": round(
                float(weighted_average_delay),
                2,
            ),
            "baseline": {
                "minimum_balance": format(
                    baseline["minimum_balance"],
                    ".2f",
                ),
                "minimum_balance_date": (
                    baseline["minimum_balance_date"].isoformat()
                ),
                "first_shortfall_date": (
                    baseline["first_shortfall_date"].isoformat()
                    if baseline["first_shortfall_date"]
                    else None
                ),
                "maximum_shortfall": format(
                    baseline["maximum_shortfall"],
                    ".2f",
                ),
                "ending_balance": format(
                    baseline["ending_balance"],
                    ".2f",
                ),
            },
            "predicted_delay": {
                "minimum_balance": format(
                    predicted["minimum_balance"],
                    ".2f",
                ),
                "minimum_balance_date": (
                    predicted["minimum_balance_date"].isoformat()
                ),
                "first_shortfall_date": (
                    predicted["first_shortfall_date"].isoformat()
                    if predicted["first_shortfall_date"]
                    else None
                ),
                "maximum_shortfall": format(
                    predicted["maximum_shortfall"],
                    ".2f",
                ),
                "ending_balance": format(
                    predicted["ending_balance"],
                    ".2f",
                ),
            },
            "delay_impact": {
                "maximum_temporary_cash_gap": format(
                    liquidity_gap["maximum_temporary_cash_gap"],
                    ".2f",
                ),
                "maximum_gap_date": (
                    liquidity_gap["maximum_gap_date"].isoformat()
                    if liquidity_gap["maximum_gap_date"]
                    else None
                ),
                "days_with_reduced_liquidity": (
                    liquidity_gap["days_with_reduced_liquidity"]
                ),
                "first_scheduled_expense_date": (
                    first_expense_date.isoformat()
                    if first_expense_date
                    else None
                ),
                "cash_delayed_by_first_expense": format(
                    cash_delayed_by_first_expense,
                    ".2f",
                ),
                "minimum_balance_deterioration": format(
                    minimum_balance_deterioration,
                    ".2f",
                ),
                "incremental_shortfall": format(
                    incremental_shortfall,
                    ".2f",
                ),
                "severity": severity,
            },
        }


def main() -> None:
    analyzer = CashDelayImpactAnalyzer()

    result = analyzer.analyze(
        opening_cash_balance="500000.00",
        horizon_days=90,
    )

    print(
        json.dumps(
            result,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
