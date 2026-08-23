from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd

from backend.app.prediction.models import DelayPrediction
from backend.app.reconciliation.normalizers import to_decimal


DEFAULT_RAW_DIR = Path("data/raw")
DEFAULT_AS_OF_DATE = date(2026, 8, 1)

# Controls how strongly global behaviour influences customers
# that have only a small amount of payment history.
PRIOR_STRENGTH = 4.0


FORBIDDEN_BENCHMARK_COLUMNS = {
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


class DelayPredictor:
    """
    Explainable, time-aware payment-delay predictor.

    Safety guarantees:
    - Reads operational finance data only.
    - Never reads data/evaluation/ground_truth.csv.
    - Never uses payments occurring after the prediction date.
    - Uses Decimal-based financial arithmetic.
    - Uses customer history when available.
    - Falls back to global historical behaviour when necessary.
    """

    def __init__(
        self,
        *,
        raw_dir: Path = DEFAULT_RAW_DIR,
        as_of_date: date = DEFAULT_AS_OF_DATE,
    ) -> None:
        self.raw_dir = Path(raw_dir)
        self.as_of_date = as_of_date

    # ------------------------------------------------------------------
    # Data safety
    # ------------------------------------------------------------------

    @staticmethod
    def _assert_no_benchmark_columns(
        frame: pd.DataFrame,
        *,
        source: str,
    ) -> None:
        columns = {
            str(column).strip().lower()
            for column in frame.columns
        }

        leaked = sorted(
            columns.intersection(
                FORBIDDEN_BENCHMARK_COLUMNS
            )
        )

        if leaked:
            raise ValueError(
                "Benchmark-labelled columns detected "
                f"in operational source '{source}': "
                f"{leaked}"
            )

    def _read_csv(
        self,
        filename: str,
    ) -> pd.DataFrame:
        path = self.raw_dir / filename

        if not path.exists():
            raise FileNotFoundError(
                f"Required operational file not found: {path}"
            )

        frame = pd.read_csv(path)

        self._assert_no_benchmark_columns(
            frame,
            source=filename,
        )

        return frame

    def load_data(
        self,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        invoices = self._read_csv(
            "invoices.csv"
        )

        payments = self._read_csv(
            "payments.csv"
        )

        required_invoice_columns = {
            "invoice_id",
            "customer_id",
            "invoice_amount",
            "issue_date",
            "due_date",
        }

        required_payment_columns = {
            "payment_id",
            "invoice_id",
            "amount",
            "payment_date",
        }

        missing_invoice_columns = (
            required_invoice_columns
            - set(invoices.columns)
        )

        missing_payment_columns = (
            required_payment_columns
            - set(payments.columns)
        )

        if missing_invoice_columns:
            raise ValueError(
                "Invoices dataset is missing columns: "
                f"{sorted(missing_invoice_columns)}"
            )

        if missing_payment_columns:
            raise ValueError(
                "Payments dataset is missing columns: "
                f"{sorted(missing_payment_columns)}"
            )

        invoices = invoices.copy()
        payments = payments.copy()

        invoices["issue_date"] = pd.to_datetime(
            invoices["issue_date"],
            errors="raise",
        )

        invoices["due_date"] = pd.to_datetime(
            invoices["due_date"],
            errors="raise",
        )

        payments["payment_date"] = pd.to_datetime(
            payments["payment_date"],
            errors="raise",
        )

        return invoices, payments

    # ------------------------------------------------------------------
    # Payment state as of prediction date
    # ------------------------------------------------------------------

    @staticmethod
    def _payment_summary(
        invoices: pd.DataFrame,
        payments: pd.DataFrame,
        *,
        cutoff: pd.Timestamp,
    ) -> pd.DataFrame:
        """
        Calculate payment state using ONLY payments visible
        on or before the prediction cutoff.

        completion_date is the earliest date on which cumulative
        successful payments reached the full invoice amount.
        """

        visible_payments = payments[
            payments["payment_date"] <= cutoff
        ].copy()

        # Ignore clearly unsuccessful payment records if the
        # operational source contains payment_status.
        if "payment_status" in visible_payments.columns:
            rejected_statuses = {
                "FAILED",
                "FAILURE",
                "PENDING",
                "CANCELLED",
                "CANCELED",
                "REVERSED",
            }

            statuses = (
                visible_payments["payment_status"]
                .astype(str)
                .str.strip()
                .str.upper()
            )

            visible_payments = visible_payments[
                ~statuses.isin(rejected_statuses)
            ].copy()

        if visible_payments.empty:
            return pd.DataFrame(
                columns=[
                    "invoice_id",
                    "total_paid",
                    "completion_date",
                ]
            )

        visible_payments["_amount_decimal"] = (
            visible_payments["amount"].map(
                to_decimal
            )
        )

        invoice_amounts = invoices[
            [
                "invoice_id",
                "invoice_amount",
            ]
        ].copy()

        invoice_amounts[
            "_invoice_amount_decimal"
        ] = invoice_amounts[
            "invoice_amount"
        ].map(
            to_decimal
        )

        work = visible_payments.merge(
            invoice_amounts[
                [
                    "invoice_id",
                    "_invoice_amount_decimal",
                ]
            ],
            on="invoice_id",
            how="inner",
        )

        work = work.sort_values(
            [
                "invoice_id",
                "payment_date",
                "payment_id",
            ]
        ).copy()

        rows: list[dict[str, object]] = []

        for invoice_id, group in work.groupby(
            "invoice_id"
        ):
            cumulative = Decimal("0.00")
            completion_date = pd.NaT

            invoice_amount = group[
                "_invoice_amount_decimal"
            ].iloc[0]

            for _, payment in group.iterrows():
                cumulative += payment[
                    "_amount_decimal"
                ]

                if (
                    pd.isna(completion_date)
                    and cumulative >= invoice_amount
                ):
                    completion_date = payment[
                        "payment_date"
                    ]

            rows.append(
                {
                    "invoice_id": invoice_id,
                    "total_paid": cumulative,
                    "completion_date": completion_date,
                }
            )

        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Historical observations
    # ------------------------------------------------------------------

    def build_history(
        self,
        *,
        as_of_date: date | None = None,
    ) -> pd.DataFrame:
        """
        Build completed-payment history using only information
        available on or before as_of_date.
        """

        cutoff = pd.Timestamp(
            as_of_date or self.as_of_date
        )

        invoices, payments = self.load_data()

        payment_summary = self._payment_summary(
            invoices,
            payments,
            cutoff=cutoff,
        )

        history = invoices.merge(
            payment_summary,
            on="invoice_id",
            how="left",
        )

        history[
            "_invoice_amount_decimal"
        ] = history[
            "invoice_amount"
        ].map(
            to_decimal
        )

        completed = history[
            history["completion_date"].notna()
            & (
                history["completion_date"]
                <= cutoff
            )
        ].copy()

        completed = completed[
            completed.apply(
                lambda row: (
                    row["total_paid"]
                    >= row[
                        "_invoice_amount_decimal"
                    ]
                ),
                axis=1,
            )
        ].copy()

        completed["delay_days"] = (
            completed["completion_date"]
            - completed["due_date"]
        ).dt.days.astype(int)

        return completed

    # ------------------------------------------------------------------
    # Open invoices
    # ------------------------------------------------------------------

    def open_invoices(
        self,
        *,
        as_of_date: date | None = None,
    ) -> pd.DataFrame:
        """
        Return invoices issued by the cutoff that have not been
        fully paid by that cutoff.
        """

        cutoff = pd.Timestamp(
            as_of_date or self.as_of_date
        )

        invoices, payments = self.load_data()

        payment_summary = self._payment_summary(
            invoices,
            payments,
            cutoff=cutoff,
        )

        merged = invoices.merge(
            payment_summary,
            on="invoice_id",
            how="left",
        )

        merged[
            "_invoice_amount_decimal"
        ] = merged[
            "invoice_amount"
        ].map(
            to_decimal
        )

        def paid_by_cutoff(
            row: pd.Series,
        ) -> bool:
            completion_date = row.get(
                "completion_date"
            )

            total_paid = row.get(
                "total_paid"
            )

            if pd.isna(completion_date):
                return False

            if completion_date > cutoff:
                return False

            if total_paid is None:
                return False

            if pd.isna(total_paid):
                return False

            return (
                total_paid
                >= row[
                    "_invoice_amount_decimal"
                ]
            )

        merged["_paid_by_cutoff"] = (
            merged.apply(
                paid_by_cutoff,
                axis=1,
            )
        )

        open_frame = merged[
            (merged["issue_date"] <= cutoff)
            & (~merged["_paid_by_cutoff"])
        ].copy()

        return open_frame

    # ------------------------------------------------------------------
    # Prediction confidence
    # ------------------------------------------------------------------

    @staticmethod
    def _confidence_score(
        *,
        history_count: int,
        delay_std: float,
    ) -> float:
        """
        Data-support confidence score.

        This is NOT a probability that the prediction is correct.
        """

        sample_factor = (
            history_count
            / (
                history_count
                + 4.0
            )
        )

        stability_factor = (
            1.0
            / (
                1.0
                + max(delay_std, 0.0)
                / 15.0
            )
        )

        score = (
            35.0
            + 60.0
            * sample_factor
            * stability_factor
        )

        return round(
            max(
                25.0,
                min(
                    95.0,
                    score,
                ),
            ),
            2,
        )

    # ------------------------------------------------------------------
    # Single-invoice prediction
    # ------------------------------------------------------------------

    def predict_invoice(
        self,
        invoice_row: pd.Series,
        *,
        history: pd.DataFrame,
        as_of_date: date | None = None,
    ) -> DelayPrediction:
        """
        Predict payment delay using only information available
        at the prediction date.

        For already-overdue invoices, predictions are conditioned
        on the fact that the invoice has remained unpaid up to the
        as-of date. Therefore, the expected payment date can never
        fall before the prediction date.
        """

        prediction_date = (
            as_of_date
            or self.as_of_date
        )

        customer_id = str(
            invoice_row["customer_id"]
        ).strip()

        invoice_id = str(
            invoice_row["invoice_id"]
        ).strip()

        invoice_amount = to_decimal(
            invoice_row["invoice_amount"]
        )

        due_date = pd.Timestamp(
            invoice_row["due_date"]
        ).date()

        global_delays = (
            history["delay_days"]
            .astype(float)
        )

        if global_delays.empty:
            raise ValueError(
                "No historical completed payments "
                "are available before the "
                "prediction date."
            )

        global_median = float(
            global_delays.median()
        )

        global_late_rate = float(
            (global_delays > 0).mean()
        )

        global_std = float(
            global_delays.std(ddof=0)
        )

        customer_history = history[
            history["customer_id"].astype(str)
            == customer_id
        ]

        history_count = len(
            customer_history
        )

        # --------------------------------------------------------------
        # Standard customer-history estimate
        # --------------------------------------------------------------

        if history_count > 0:
            customer_delays = (
                customer_history[
                    "delay_days"
                ].astype(float)
            )

            customer_median = float(
                customer_delays.median()
            )

            customer_late_count = int(
                (
                    customer_delays > 0
                ).sum()
            )

            customer_std = float(
                customer_delays.std(
                    ddof=0
                )
            )

            weight = (
                history_count
                / (
                    history_count
                    + PRIOR_STRENGTH
                )
            )

            blended_delay = (
                weight
                * customer_median
                + (
                    1.0 - weight
                )
                * global_median
            )

            late_probability = (
                customer_late_count
                + PRIOR_STRENGTH
                * global_late_rate
            ) / (
                history_count
                + PRIOR_STRENGTH
            )

            confidence = (
                self._confidence_score(
                    history_count=history_count,
                    delay_std=customer_std,
                )
            )

            prediction_basis = (
                "CUSTOMER_HISTORY"
            )

        else:
            blended_delay = global_median
            late_probability = global_late_rate

            confidence = (
                self._confidence_score(
                    history_count=0,
                    delay_std=global_std,
                )
            )

            prediction_basis = (
                "GLOBAL_FALLBACK"
            )

        # --------------------------------------------------------------
        # Overdue-aware conditional prediction
        # --------------------------------------------------------------

        days_overdue = max(
            0,
            (
                prediction_date
                - due_date
            ).days,
        )

        if days_overdue > 0:
            # The invoice is known to still be unpaid after
            # days_overdue days. Historical cases that completed
            # earlier than this are no longer comparable.

            if history_count > 0:
                customer_tail = (
                    customer_history[
                        customer_history[
                            "delay_days"
                        ]
                        > days_overdue
                    ]["delay_days"]
                    .astype(float)
                )
            else:
                customer_tail = pd.Series(
                    dtype=float
                )

            global_tail = (
                global_delays[
                    global_delays
                    > days_overdue
                ]
            )

            if not customer_tail.empty:
                conditional_total_delay = float(
                    customer_tail.median()
                )

                tail_std = float(
                    customer_tail.std(
                        ddof=0
                    )
                )

                comparable_count = len(
                    customer_tail
                )

                confidence = (
                    self._confidence_score(
                        history_count=(
                            comparable_count
                        ),
                        delay_std=tail_std,
                    )
                )

                prediction_basis = (
                    "OVERDUE_CUSTOMER_HISTORY"
                )

            elif not global_tail.empty:
                conditional_total_delay = float(
                    global_tail.median()
                )

                tail_std = float(
                    global_tail.std(
                        ddof=0
                    )
                )

                comparable_count = len(
                    global_tail
                )

                confidence = (
                    self._confidence_score(
                        history_count=(
                            comparable_count
                        ),
                        delay_std=tail_std,
                    )
                )

                prediction_basis = (
                    "OVERDUE_GLOBAL_FALLBACK"
                )

            else:
                # Invoice is overdue beyond anything observed
                # historically. Do not invent additional days.
                conditional_total_delay = float(
                    days_overdue
                )

                confidence = 25.0

                prediction_basis = (
                    "OVERDUE_NO_COMPARABLE_HISTORY"
                )

            expected_delay_days = max(
                days_overdue,
                int(
                    round(
                        conditional_total_delay
                    )
                ),
            )

            # It is already known to be late.
            late_probability_pct = 100.0

        else:
            expected_delay_days = max(
                0,
                int(
                    round(
                        blended_delay
                    )
                ),
            )

            late_probability_pct = round(
                late_probability
                * 100.0,
                2,
            )

        expected_payment_date = (
            due_date
            + timedelta(
                days=expected_delay_days
            )
        )

        # Defensive guarantee: never predict a date in the past
        # for an invoice still open at prediction time.
        if expected_payment_date < prediction_date:
            expected_payment_date = (
                prediction_date
            )

            expected_delay_days = max(
                0,
                (
                    prediction_date
                    - due_date
                ).days,
            )

        # --------------------------------------------------------------
        # Outstanding financial exposure
        # --------------------------------------------------------------

        total_paid_value = invoice_row.get(
            "total_paid"
        )

        if (
            total_paid_value is None
            or pd.isna(total_paid_value)
        ):
            paid_before_cutoff = (
                Decimal("0.00")
            )
        else:
            paid_before_cutoff = (
                to_decimal(
                    total_paid_value
                )
            )

        outstanding_amount = max(
            invoice_amount
            - paid_before_cutoff,
            Decimal("0.00"),
        )

        amount_at_risk = (
            outstanding_amount
            if expected_delay_days > 0
            else Decimal("0.00")
        )

        return DelayPrediction(
            invoice_id=invoice_id,
            customer_id=customer_id,
            invoice_amount=invoice_amount,
            due_date=due_date,
            expected_delay_days=(
                expected_delay_days
            ),
            expected_payment_date=(
                expected_payment_date
            ),
            late_probability=(
                late_probability_pct
            ),
            confidence=confidence,
            history_count=history_count,
            prediction_basis=(
                prediction_basis
            ),
            amount_at_risk=(
                amount_at_risk
            ),
        outstanding_amount=(
            outstanding_amount
        ),
        )

    # ------------------------------------------------------------------
    # Batch prediction
    # ------------------------------------------------------------------

    def predict_open_invoices(
        self,
        *,
        as_of_date: date | None = None,
    ) -> list[DelayPrediction]:
        cutoff = (
            as_of_date
            or self.as_of_date
        )

        history = self.build_history(
            as_of_date=cutoff
        )

        open_frame = self.open_invoices(
            as_of_date=cutoff
        )

        predictions: list[
            DelayPrediction
        ] = []

        for _, row in open_frame.iterrows():
            predictions.append(
                self.predict_invoice(
                    row,
                    history=history,
                    as_of_date=cutoff,
                )
            )

        return predictions


# ----------------------------------------------------------------------
# CLI demo
# ----------------------------------------------------------------------

def main() -> None:
    predictor = DelayPredictor()

    predictions = (
        predictor.predict_open_invoices()
    )

    print(
        "FlowGuard payment-delay predictions"
    )

    print(
        f"As-of date: "
        f"{predictor.as_of_date.isoformat()}"
    )

    print(
        f"Open invoices predicted: "
        f"{len(predictions)}"
    )

    print()

    for prediction in predictions[:10]:
        print(
            prediction.to_dict()
        )


if __name__ == "__main__":
    main()