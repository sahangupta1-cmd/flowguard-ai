from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.prediction.delay_predictor import (
    DEFAULT_AS_OF_DATE,
    DEFAULT_RAW_DIR,
    DelayPredictor,
)


DEFAULT_REPORT_DIR = Path("reports/prediction")


def _percentage(
    numerator: int,
    denominator: int,
) -> float:
    if denominator == 0:
        return 0.0

    return round(
        numerator / denominator * 100.0,
        2,
    )


def _safe_ratio(
    numerator: int,
    denominator: int,
) -> float:
    if denominator == 0:
        return 0.0

    return numerator / denominator


class DelayEvaluator:
    """
    Time-aware evaluation of FlowGuard payment-delay predictions.

    The predictor receives only information available on or before
    the cutoff date.

    Payments occurring after the cutoff are used ONLY here for
    offline evaluation and never enter prediction-time features.
    """

    def __init__(
        self,
        *,
        raw_dir: Path = DEFAULT_RAW_DIR,
        as_of_date: date = DEFAULT_AS_OF_DATE,
        report_dir: Path = DEFAULT_REPORT_DIR,
    ) -> None:
        self.raw_dir = Path(raw_dir)
        self.as_of_date = as_of_date
        self.report_dir = Path(report_dir)

        self.predictor = DelayPredictor(
            raw_dir=self.raw_dir,
            as_of_date=self.as_of_date,
        )

    def evaluate(
        self,
        *,
        write_outputs: bool = True,
    ) -> dict[str, Any]:
        cutoff = pd.Timestamp(
            self.as_of_date
        )

        # --------------------------------------------------------------
        # 1. Produce predictions using cutoff-safe information only.
        # --------------------------------------------------------------

        predictions = (
            self.predictor.predict_open_invoices(
                as_of_date=self.as_of_date
            )
        )

        prediction_rows = []

        for prediction in predictions:
            prediction_rows.append(
                {
                    "invoice_id": prediction.invoice_id,
                    "customer_id": prediction.customer_id,
                    "expected_delay_days": (
                        prediction.expected_delay_days
                    ),
                    "expected_payment_date": (
                        pd.Timestamp(
                            prediction.expected_payment_date
                        )
                    ),
                    "late_probability": (
                        prediction.late_probability
                    ),
                    "confidence": prediction.confidence,
                    "history_count": (
                        prediction.history_count
                    ),
                    "prediction_basis": (
                        prediction.prediction_basis
                    ),
                }
            )

        prediction_frame = pd.DataFrame(
            prediction_rows
        )

        if prediction_frame.empty:
            raise ValueError(
                "No open invoices were available "
                "for temporal evaluation."
            )

        # --------------------------------------------------------------
        # 2. Load operational outcomes.
        #
        # Future payment outcomes are used ONLY after predictions have
        # already been generated.
        # --------------------------------------------------------------

        invoices, payments = (
            self.predictor.load_data()
        )

        if payments.empty:
            raise ValueError(
                "No payment outcomes are available "
                "for evaluation."
            )

        observation_end = (
            payments["payment_date"].max()
        )

        actual_payment_summary = (
            self.predictor._payment_summary(
                invoices,
                payments,
                cutoff=observation_end,
            )
        )

        actual = invoices.merge(
            actual_payment_summary,
            on="invoice_id",
            how="left",
        )

        actual = actual[
            actual["completion_date"].notna()
        ].copy()

        actual["actual_delay_days"] = (
            actual["completion_date"]
            - actual["due_date"]
        ).dt.days.astype(int)

        # Only outcomes that completed after the prediction cutoff
        # count as future-held-out observations.
        actual = actual[
            actual["completion_date"]
            > cutoff
        ].copy()

        # --------------------------------------------------------------
        # 3. Evaluate only invoices predicted at cutoff whose eventual
        #    full-payment outcome is observable in the dataset.
        # --------------------------------------------------------------

        evaluation = prediction_frame.merge(
            actual[
                [
                    "invoice_id",
                    "completion_date",
                    "actual_delay_days",
                ]
            ],
            on="invoice_id",
            how="inner",
        )

        if evaluation.empty:
            raise ValueError(
                "No future completed invoices overlap "
                "with the prediction set."
            )

        evaluation["error_days"] = (
            evaluation["expected_delay_days"]
            - evaluation["actual_delay_days"]
        )

        evaluation["absolute_error_days"] = (
            evaluation["error_days"].abs()
        )

        # --------------------------------------------------------------
        # 4. Historical baseline
        #
        # Compare FlowGuard with a simple global median-delay predictor.
        # --------------------------------------------------------------

        historical = (
            self.predictor.build_history(
                as_of_date=self.as_of_date
            )
        )

        if historical.empty:
            raise ValueError(
                "No historical payment observations "
                "are available for baseline evaluation."
            )

        baseline_delay = int(
            round(
                float(
                    historical[
                        "delay_days"
                    ].median()
                )
            )
        )

        evaluation[
            "baseline_delay_days"
        ] = baseline_delay

        evaluation[
            "baseline_absolute_error_days"
        ] = (
            evaluation[
                "baseline_delay_days"
            ]
            - evaluation[
                "actual_delay_days"
            ]
        ).abs()

        # --------------------------------------------------------------
        # 5. Delay-regression metrics
        # --------------------------------------------------------------

        evaluated_cases = len(
            evaluation
        )

        mae = float(
            evaluation[
                "absolute_error_days"
            ].mean()
        )

        median_absolute_error = float(
            evaluation[
                "absolute_error_days"
            ].median()
        )

        rmse = float(
            (
                evaluation[
                    "error_days"
                ].pow(2).mean()
            )
            ** 0.5
        )

        within_3_days = int(
            (
                evaluation[
                    "absolute_error_days"
                ]
                <= 3
            ).sum()
        )

        within_7_days = int(
            (
                evaluation[
                    "absolute_error_days"
                ]
                <= 7
            ).sum()
        )

        baseline_mae = float(
            evaluation[
                "baseline_absolute_error_days"
            ].mean()
        )

        if baseline_mae > 0:
            improvement_over_baseline = (
                baseline_mae - mae
            ) / baseline_mae * 100.0
        else:
            improvement_over_baseline = 0.0

        # --------------------------------------------------------------
        # 6. Late-payment classification
        # --------------------------------------------------------------

        evaluation["actual_late"] = (
            evaluation[
                "actual_delay_days"
            ]
            > 0
        )

        evaluation["predicted_late"] = (
            evaluation[
                "late_probability"
            ]
            >= 50.0
        )

        true_positive = int(
            (
                evaluation["actual_late"]
                & evaluation["predicted_late"]
            ).sum()
        )

        true_negative = int(
            (
                ~evaluation["actual_late"]
                & ~evaluation["predicted_late"]
            ).sum()
        )

        false_positive = int(
            (
                ~evaluation["actual_late"]
                & evaluation["predicted_late"]
            ).sum()
        )

        false_negative = int(
            (
                evaluation["actual_late"]
                & ~evaluation["predicted_late"]
            ).sum()
        )

        classification_accuracy = (
            true_positive
            + true_negative
        ) / evaluated_cases

        precision = _safe_ratio(
            true_positive,
            true_positive
            + false_positive,
        )

        recall = _safe_ratio(
            true_positive,
            true_positive
            + false_negative,
        )

        if precision + recall > 0:
            f1 = (
                2.0
                * precision
                * recall
                / (
                    precision
                    + recall
                )
            )
        else:
            f1 = 0.0

        # --------------------------------------------------------------
        # 7. Final reviewer-facing report
        # --------------------------------------------------------------

        metrics = {
            "as_of_date": (
                self.as_of_date.isoformat()
            ),
            "observation_end_date": (
                observation_end.date().isoformat()
            ),
            "predictions_generated": len(
                prediction_frame
            ),
            "future_completed_cases_evaluated": (
                evaluated_cases
            ),
            "open_cases_without_observed_completion": (
                len(prediction_frame)
                - evaluated_cases
            ),
            "delay_prediction": {
                "mae_days": round(
                    mae,
                    2,
                ),
                "median_absolute_error_days": round(
                    median_absolute_error,
                    2,
                ),
                "rmse_days": round(
                    rmse,
                    2,
                ),
                "within_3_days_pct": (
                    _percentage(
                        within_3_days,
                        evaluated_cases,
                    )
                ),
                "within_7_days_pct": (
                    _percentage(
                        within_7_days,
                        evaluated_cases,
                    )
                ),
            },
            "baseline_comparison": {
                "historical_global_median_delay_days": (
                    baseline_delay
                ),
                "baseline_mae_days": round(
                    baseline_mae,
                    2,
                ),
                "flowguard_mae_days": round(
                    mae,
                    2,
                ),
                "mae_improvement_pct": round(
                    improvement_over_baseline,
                    2,
                ),
            },
            "late_payment_classification": {
                "threshold_pct": 50.0,
                "accuracy_pct": round(
                    classification_accuracy
                    * 100.0,
                    2,
                ),
                "precision_pct": round(
                    precision * 100.0,
                    2,
                ),
                "recall_pct": round(
                    recall * 100.0,
                    2,
                ),
                "f1_pct": round(
                    f1 * 100.0,
                    2,
                ),
                "true_positive": (
                    true_positive
                ),
                "true_negative": (
                    true_negative
                ),
                "false_positive": (
                    false_positive
                ),
                "false_negative": (
                    false_negative
                ),
            },
            "average_prediction_confidence": round(
                float(
                    evaluation[
                        "confidence"
                    ].mean()
                ),
                2,
            ),
        }

        report = {
            "methodology": {
                "prediction_cutoff": (
                    self.as_of_date.isoformat()
                ),
                "future_outcomes_used_only_for_evaluation": (
                    True
                ),
                "ground_truth_file_used": False,
                "benchmark_labels_used": False,
            },
            "metrics": metrics,
        }

        # --------------------------------------------------------------
        # 8. Optional reproducible report outputs
        # --------------------------------------------------------------

        if write_outputs:
            self.report_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            metrics_path = (
                self.report_dir
                / "delay_metrics.json"
            )

            cases_path = (
                self.report_dir
                / "delay_evaluation_cases.csv"
            )

            metrics_path.write_text(
                json.dumps(
                    report,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            export_frame = (
                evaluation.copy()
            )

            export_frame[
                "expected_payment_date"
            ] = export_frame[
                "expected_payment_date"
            ].dt.date.astype(str)

            export_frame[
                "completion_date"
            ] = export_frame[
                "completion_date"
            ].dt.date.astype(str)

            export_frame.to_csv(
                cases_path,
                index=False,
            )

        return report


def main() -> None:
    evaluator = DelayEvaluator()

    report = evaluator.evaluate(
        write_outputs=True
    )

    print(
        json.dumps(
            report["metrics"],
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()