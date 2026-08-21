from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd

from backend.app.cashflow.models import (
    CashImpactResult,
    DailyCashPosition,
)
from backend.app.prediction.delay_predictor import (
    DEFAULT_AS_OF_DATE,
    DEFAULT_RAW_DIR,
    DelayPredictor,
)
from backend.app.reconciliation.normalizers import (
    to_decimal,
)


DEFAULT_HORIZON_DAYS = 90


class CashImpactEngine:
    """
    Deterministic cash-impact forecasting engine.

    Uses:
    - Payment-delay predictions as expected receivable inflows.
    - Scheduled operating expenses as cash outflows.
    - Explicit opening cash balance supplied by the caller.

    Does NOT:
    - Read benchmark labels.
    - Read ground-truth files.
    - Pretend reconciliation bank transactions represent the
      company's complete cash balance.
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

        required = {
            "expense_id",
            "category",
            "vendor",
            "amount",
            "due_date",
            "priority",
            "status",
        }

        missing = required - set(
            expenses.columns
        )

        if missing:
            raise ValueError(
                "Expenses dataset is missing columns: "
                f"{sorted(missing)}"
            )

        forbidden = {
            "benchmark_id",
            "case_id",
            "stress_id",
            "scenario",
            "true_status",
            "true_root_cause",
            "expected_status",
            "should_auto_resolve",
        }

        leaked = forbidden.intersection(
            {
                str(column).strip().lower()
                for column in expenses.columns
            }
        )

        if leaked:
            raise ValueError(
                "Benchmark-labelled columns detected "
                f"in expenses.csv: {sorted(leaked)}"
            )

        expenses = expenses.copy()

        expenses["due_date"] = pd.to_datetime(
            expenses["due_date"],
            errors="raise",
        )

        expenses["_amount_decimal"] = (
            expenses["amount"].map(
                to_decimal
            )
        )

        return expenses

    @staticmethod
    def _severity(
        *,
        maximum_shortfall: Decimal,
        opening_cash_balance: Decimal,
    ) -> str:
        if maximum_shortfall <= 0:
            return "LOW"

        denominator = max(
            opening_cash_balance,
            Decimal("1.00"),
        )

        ratio = (
            maximum_shortfall
            / denominator
        )

        if ratio >= Decimal("0.50"):
            return "CRITICAL"

        if ratio >= Decimal("0.25"):
            return "HIGH"

        if ratio >= Decimal("0.10"):
            return "MEDIUM"

        return "LOW"

    @staticmethod
    def _recommended_action(
        severity: str,
    ) -> str:
        actions = {
            "LOW": (
                "Maintain normal collections monitoring "
                "and continue scheduled payments."
            ),
            "MEDIUM": (
                "Prioritize collection of delayed "
                "receivables and review discretionary "
                "LOW-priority expenses."
            ),
            "HIGH": (
                "Escalate high-risk receivables, preserve "
                "cash, and consider deferring non-critical "
                "expenses where operationally appropriate."
            ),
            "CRITICAL": (
                "Immediate treasury review required. "
                "Accelerate collections, protect CRITICAL "
                "obligations, and secure additional "
                "liquidity if necessary."
            ),
        }

        return actions[severity]

    def forecast(
        self,
        *,
        opening_cash_balance: Decimal | str | int | float,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
    ) -> CashImpactResult:
        if horizon_days <= 0:
            raise ValueError(
                "horizon_days must be greater than zero."
            )

        opening_balance = to_decimal(
            opening_cash_balance
        )

        if opening_balance < Decimal("0.00"):
            raise ValueError(
                "opening_cash_balance cannot be negative."
            )

        horizon_end = (
            self.as_of_date
            + timedelta(
                days=horizon_days,
            )
        )

        predictions = (
            self.predictor.predict_open_invoices(
                as_of_date=self.as_of_date
            )
        )

        expenses = self._load_expenses()

        expenses = expenses[
            (
                expenses["due_date"]
                >= pd.Timestamp(self.as_of_date)
            )
            & (
                expenses["due_date"]
                <= pd.Timestamp(horizon_end)
            )
            & (
                expenses["status"]
                .astype(str)
                .str.strip()
                .str.upper()
                == "SCHEDULED"
            )
        ].copy()

        inflows_by_date: dict[
            date,
            Decimal,
        ] = {}

        for prediction in predictions:
            payment_date = (
                prediction.expected_payment_date
            )

            if not (
                self.as_of_date
                <= payment_date
                <= horizon_end
            ):
                continue

            outstanding = (
                prediction.amount_at_risk
            )

            if outstanding <= 0:
                continue

            inflows_by_date[payment_date] = (
                inflows_by_date.get(
                    payment_date,
                    Decimal("0.00"),
                )
                + outstanding
            )

        outflows_by_date: dict[
            date,
            Decimal,
        ] = {}

        for _, expense in expenses.iterrows():
            due_date = pd.Timestamp(
                expense["due_date"]
            ).date()

            amount = expense[
                "_amount_decimal"
            ]

            outflows_by_date[due_date] = (
                outflows_by_date.get(
                    due_date,
                    Decimal("0.00"),
                )
                + amount
            )

        daily_positions: list[
            DailyCashPosition
        ] = []

        running_balance = (
            opening_balance
        )

        current_date = self.as_of_date

        first_shortfall_date: (
            date | None
        ) = None

        minimum_balance = opening_balance

        total_inflows = Decimal("0.00")
        total_outflows = Decimal("0.00")

        while current_date <= horizon_end:
            day_opening = running_balance

            inflow = inflows_by_date.get(
                current_date,
                Decimal("0.00"),
            )

            outflow = outflows_by_date.get(
                current_date,
                Decimal("0.00"),
            )

            running_balance = (
                running_balance
                + inflow
                - outflow
            )

            total_inflows += inflow
            total_outflows += outflow

            if running_balance < minimum_balance:
                minimum_balance = (
                    running_balance
                )

            if (
                running_balance < 0
                and first_shortfall_date is None
            ):
                first_shortfall_date = (
                    current_date
                )

            daily_positions.append(
                DailyCashPosition(
                    date=current_date,
                    opening_balance=(
                        day_opening
                    ),
                    expected_inflows=inflow,
                    scheduled_outflows=(
                        outflow
                    ),
                    closing_balance=(
                        running_balance
                    ),
                )
            )

            current_date += timedelta(
                days=1
            )

        maximum_shortfall = max(
            Decimal("0.00"),
            -minimum_balance,
        )

        shortfall_detected = (
            maximum_shortfall
            > Decimal("0.00")
        )

        severity = self._severity(
            maximum_shortfall=(
                maximum_shortfall
            ),
            opening_cash_balance=(
                opening_balance
            ),
        )

        recommended_action = (
            self._recommended_action(
                severity
            )
        )

        return CashImpactResult(
            as_of_date=self.as_of_date,
            horizon_end=horizon_end,
            opening_cash_balance=(
                opening_balance
            ),
            total_expected_inflows=(
                total_inflows
            ),
            total_scheduled_outflows=(
                total_outflows
            ),
            projected_ending_balance=(
                running_balance
            ),
            shortfall_detected=(
                shortfall_detected
            ),
            first_shortfall_date=(
                first_shortfall_date
            ),
            maximum_shortfall=(
                maximum_shortfall
            ),
            minimum_projected_balance=(
                minimum_balance
            ),
            severity=severity,
            recommended_action=(
                recommended_action
            ),
            daily_positions=(
                daily_positions
            ),
        )


def main() -> None:
    engine = CashImpactEngine()

    result = engine.forecast(
        opening_cash_balance="500000.00",
        horizon_days=90,
    )

    summary = result.to_dict()

    summary.pop(
        "daily_positions"
    )

    print("FlowGuard cash-impact forecast")

    for key, value in summary.items():
        print(
            f"{key}: {value}"
        )


if __name__ == "__main__":
    main()