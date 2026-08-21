from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from typing import Any

import pandas as pd


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_TRUTH_PATH = (
    PROJECT_ROOT
    / "data"
    / "evaluation"
    / "ground_truth.csv"
)

DEFAULT_RESULTS_PATH = (
    PROJECT_ROOT
    / "data"
    / "output"
    / "reconciliation_results.csv"
)

DEFAULT_REPORT_DIR = (
    PROJECT_ROOT
    / "reports"
    / "evaluation"
)


# ============================================================
# EXPECTED OPERATIONAL SEMANTICS
# ============================================================

ROOT_CAUSE_MAPPING = {
    # FUZZY_REFERENCE is a matching challenge,
    # not a financial root cause.
    "FUZZY_REFERENCE": "CLEAN",

    # The benchmark's UNRESOLVED scenario represents
    # an unexplained financial discrepancy.
    "UNRESOLVED": "UNEXPLAINED",
}


# ============================================================
# HELPERS
# ============================================================


def percentage(
    numerator: int,
    denominator: int,
) -> float:

    if denominator == 0:
        return 0.0

    return round(
        numerator / denominator * 100,
        2,
    )


def normalize_id(
    value: Any,
) -> str:

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip().upper()

def parse_bool(
    value: Any,
) -> bool:
    """
    Convert CSV-style boolean values safely.

    Accepted true values:
        True, TRUE, 1, YES

    Accepted false values:
        False, FALSE, 0, NO

    Invalid values raise an error instead of being
    silently interpreted.
    """

    if isinstance(value, bool):
        return value

    text = normalize_id(value)

    if text in {
        "TRUE",
        "1",
        "YES",
    }:
        return True

    if text in {
        "FALSE",
        "0",
        "NO",
    }:
        return False

    raise ValueError(
        f"Invalid boolean value: {value!r}"
    )


def parse_id_set(
    value: Any,
) -> set[str]:
    """
    Convert pipe-separated operational IDs into a set.

    Example:
        PAY001|PAY002
            ->
        {"PAY001", "PAY002"}
    """

    if value is None:
        return set()

    try:
        if pd.isna(value):
            return set()
    except (TypeError, ValueError):
        pass

    text = str(value).strip()

    if not text:
        return set()

    return {
        normalize_id(item)
        for item in text.split("|")
        if normalize_id(item)
    }


def expected_root_cause(
    benchmark_root_cause: Any,
) -> str:

    raw = normalize_id(
        benchmark_root_cause
    )

    return ROOT_CAUSE_MAPPING.get(
        raw,
        raw,
    )


# ============================================================
# LINKAGE METRICS
# ============================================================


def linkage_metrics(
    expected_by_invoice: dict[str, set[str]],
    predicted_by_invoice: dict[str, set[str]],
) -> dict[str, Any]:
    """
    Micro precision/recall/F1 for record linkage.

    Invoice ID is included in each pair so assigning the
    correct payment to the wrong invoice still counts as an
    error.
    """

    expected_pairs = {
        (invoice_id, record_id)
        for invoice_id, record_ids
        in expected_by_invoice.items()
        for record_id in record_ids
    }

    predicted_pairs = {
        (invoice_id, record_id)
        for invoice_id, record_ids
        in predicted_by_invoice.items()
        for record_id in record_ids
    }

    true_positive = len(
        expected_pairs
        & predicted_pairs
    )

    false_positive = len(
        predicted_pairs
        - expected_pairs
    )

    false_negative = len(
        expected_pairs
        - predicted_pairs
    )

    precision = (
        true_positive
        / (
            true_positive
            + false_positive
        )
        if (
            true_positive
            + false_positive
        )
        else 1.0
    )

    recall = (
        true_positive
        / (
            true_positive
            + false_negative
        )
        if (
            true_positive
            + false_negative
        )
        else 1.0
    )

    f1 = (
        2 * precision * recall
        / (precision + recall)
        if (
            precision
            + recall
        )
        else 0.0
    )

    return {
        "true_positive":
            true_positive,

        "false_positive":
            false_positive,

        "false_negative":
            false_negative,

        "precision_pct":
            round(
                precision * 100,
                2,
            ),

        "recall_pct":
            round(
                recall * 100,
                2,
            ),

        "f1_pct":
            round(
                f1 * 100,
                2,
            ),
    }


# ============================================================
# EVALUATOR
# ============================================================


class BenchmarkEvaluator:
    """
    Isolated benchmark evaluator.

    This class is the ONLY layer allowed to compare
    operational FlowGuard output with hidden ground truth.

    Nothing from this module is imported by the production
    reconciliation pipeline.
    """

    def __init__(
        self,
        *,
        truth_path: Path = DEFAULT_TRUTH_PATH,
        results_path: Path = DEFAULT_RESULTS_PATH,
        report_dir: Path = DEFAULT_REPORT_DIR,
    ) -> None:

        self.truth_path = Path(
            truth_path
        )

        self.results_path = Path(
            results_path
        )

        self.report_dir = Path(
            report_dir
        )

    # ========================================================
    # LOAD
    # ========================================================

    def _load(self):

        if not self.truth_path.exists():

            raise FileNotFoundError(
                f"Ground truth not found: "
                f"{self.truth_path}"
            )

        if not self.results_path.exists():

            raise FileNotFoundError(
                f"Reconciliation results not found: "
                f"{self.results_path}"
            )

        truth = pd.read_csv(
            self.truth_path
        )

        predictions = pd.read_csv(
            self.results_path
        )

        self._validate(
            truth,
            predictions,
        )

        return truth, predictions

    # ========================================================
    # VALIDATION
    # ========================================================

    @staticmethod
    def _validate(
        truth: pd.DataFrame,
        predictions: pd.DataFrame,
    ) -> None:

        truth_required = {
            "invoice_id",
            "scenario",
            "true_status",
            "true_root_cause",
            "expected_payment_ids",
            "expected_settlement_ids",
            "expected_bank_txn_ids",
        }

        prediction_required = {
            "invoice_id",
            "payment_ids",
            "settlement_ids",
            "bank_transaction_ids",
            "status",
            "root_cause",
            "match_method",
            "requires_review",
        }

        truth_missing = (
            truth_required
            - set(truth.columns)
        )

        prediction_missing = (
            prediction_required
            - set(predictions.columns)
        )

        if truth_missing:

            raise ValueError(
                "Ground truth is missing required columns: "
                + ", ".join(
                    sorted(truth_missing)
                )
            )

        if prediction_missing:

            raise ValueError(
                "Results are missing required columns: "
                + ", ".join(
                    sorted(prediction_missing)
                )
            )

        if truth["invoice_id"].duplicated().any():

            raise ValueError(
                "Ground truth contains duplicate invoice IDs."
            )

        if predictions[
            "invoice_id"
        ].duplicated().any():

            raise ValueError(
                "Predictions contain duplicate invoice IDs."
            )

    # ========================================================
    # EVALUATION
    # ========================================================

    def evaluate(
        self,
        *,
        write_reports: bool = True,
    ) -> dict[str, Any]:

        truth, predictions = (
            self._load()
        )

        truth = truth.copy()
        predictions = predictions.copy()

        truth["invoice_id"] = (
            truth["invoice_id"]
            .apply(normalize_id)
        )

        predictions["invoice_id"] = (
            predictions["invoice_id"]
            .apply(normalize_id)
        )

        prediction_lookup = {
            row["invoice_id"]: row
            for _, row
            in predictions.iterrows()
        }

        truth_invoice_ids = set(
            truth["invoice_id"]
        )

        prediction_invoice_ids = set(
            predictions["invoice_id"]
        )

        missing_predictions = sorted(
            truth_invoice_ids
            - prediction_invoice_ids
        )

        unexpected_predictions = sorted(
            prediction_invoice_ids
            - truth_invoice_ids
        )

        case_rows: list[
            dict[str, Any]
        ] = []

        payment_expected = {}
        payment_predicted = {}

        settlement_expected = {}
        settlement_predicted = {}

        bank_expected = {}
        bank_predicted = {}

        status_correct_count = 0
        root_correct_count = 0
        end_to_end_correct_count = 0

        expected_fuzzy_count = 0
        predicted_fuzzy_count = 0
        successful_fuzzy_count = 0
        auto_resolution_cases_evaluated = 0
        expected_auto_resolve_count = 0
        predicted_auto_resolve_count = 0
        auto_resolution_correct_count = 0
        unsafe_auto_resolve_count = 0
        missed_auto_resolve_count = 0

        scenario_stats = defaultdict(
            lambda: {
                "total": 0,
                "correct": 0,
            }
        )

        for _, truth_row in truth.iterrows():

            invoice_id = truth_row[
                "invoice_id"
            ]

            scenario = normalize_id(
                truth_row["scenario"]
            )

            scenario_stats[
                scenario
            ]["total"] += 1

            expected_status = normalize_id(
                truth_row["true_status"]
            )

            expected_cause = (
                expected_root_cause(
                    truth_row[
                        "true_root_cause"
                    ]
                )
            )
                        # =================================================
            # EXPECTED MATCH METHOD
            # =================================================

            if "expected_match_method" in truth.columns:
                expected_method = normalize_id(
                    truth_row[
                        "expected_match_method"
                    ]
                )

            else:
                # Backward compatibility with frozen V1.
                expected_method = (
                    "FUZZY"
                    if scenario == "FUZZY_REFERENCE"
                    else ""
                )

            expected_fuzzy = (
                expected_method == "FUZZY"
            )
            if "should_auto_resolve" in truth.columns:
                expected_auto_resolve = parse_bool(
                    truth_row[
                        "should_auto_resolve"
                    ]
                )

                auto_resolution_cases_evaluated += 1

                expected_auto_resolve_count += int(
                    expected_auto_resolve
                )

            else:
                expected_auto_resolve = None
            expected_payments = parse_id_set(
                truth_row[
                    "expected_payment_ids"
                ]
            )

            expected_settlements = parse_id_set(
                truth_row[
                    "expected_settlement_ids"
                ]
            )

            expected_banks = parse_id_set(
                truth_row[
                    "expected_bank_txn_ids"
                ]
            )

            payment_expected[
                invoice_id
            ] = expected_payments

            settlement_expected[
                invoice_id
            ] = expected_settlements

            bank_expected[
                invoice_id
            ] = expected_banks

            prediction = (
                prediction_lookup.get(
                    invoice_id
                )
            )

            if prediction is None:

                payment_predicted[
                    invoice_id
                ] = set()

                settlement_predicted[
                    invoice_id
                ] = set()

                bank_predicted[
                    invoice_id
                ] = set()

                case_rows.append(
                    {
                        "invoice_id":
                            invoice_id,

                        "scenario":
                            scenario,

                        "prediction_present":
                            False,

                        "status_correct":
                            False,

                        "root_cause_correct":
                            False,

                        "payment_links_correct":
                            False,

                        "settlement_links_correct":
                            False,

                        "bank_links_correct":
                            False,

                        "end_to_end_correct":
                            False,

                        "expected_status":
                            expected_status,

                        "predicted_status":
                            "",

                        "expected_root_cause":
                            expected_cause,

                        "predicted_root_cause":
                            "",

                        "predicted_match_method":
                            "",
                    }
                )

                continue

            predicted_status = normalize_id(
                prediction["status"]
            )

            predicted_cause = normalize_id(
                prediction["root_cause"]
            )

            predicted_method = normalize_id(
                prediction["match_method"]
            )
            method_correct = (
                True
                if not expected_method
                else predicted_method == expected_method
            )
            predicted_requires_review = parse_bool(
                prediction[
                    "requires_review"
                ]
            )

            predicted_auto_resolve = (
                not predicted_requires_review
                and predicted_status
                in {
                    "RECONCILED",
                    "EXPLAINED_EXCEPTION",
                }
            )

            if expected_auto_resolve is not None:

                predicted_auto_resolve_count += int(
                    predicted_auto_resolve
                )

                auto_resolution_correct = (
                    predicted_auto_resolve
                    == expected_auto_resolve
                )

                auto_resolution_correct_count += int(
                    auto_resolution_correct
                )

                if (
                    predicted_auto_resolve
                    and not expected_auto_resolve
                ):
                    unsafe_auto_resolve_count += 1

                if (
                    expected_auto_resolve
                    and not predicted_auto_resolve
                ):
                    missed_auto_resolve_count += 1

            else:
                auto_resolution_correct = True

            predicted_payments = parse_id_set(
                prediction["payment_ids"]
            )

            predicted_settlements = parse_id_set(
                prediction["settlement_ids"]
            )

            predicted_banks = parse_id_set(
                prediction[
                    "bank_transaction_ids"
                ]
            )

            payment_predicted[
                invoice_id
            ] = predicted_payments

            settlement_predicted[
                invoice_id
            ] = predicted_settlements

            bank_predicted[
                invoice_id
            ] = predicted_banks

            status_correct = (
                predicted_status
                == expected_status
            )

            root_correct = (
                predicted_cause
                == expected_cause
            )

            payment_correct = (
                predicted_payments
                == expected_payments
            )

            settlement_correct = (
                predicted_settlements
                == expected_settlements
            )

            bank_correct = (
                predicted_banks
                == expected_banks
            )

            end_to_end_correct = all(
                [
                    status_correct,
                    root_correct,
                    payment_correct,
                    settlement_correct,
                    bank_correct,
                    method_correct,
                    auto_resolution_correct,
                ]
            )

            status_correct_count += int(
                status_correct
            )

            root_correct_count += int(
                root_correct
            )

            end_to_end_correct_count += int(
                end_to_end_correct
            )

            if end_to_end_correct:

                scenario_stats[
                    scenario
                ]["correct"] += 1



            predicted_fuzzy = (
                predicted_method == "FUZZY"
            )

            method_correct = (
                True
                if not expected_method
                else predicted_method == expected_method
            )

            if expected_fuzzy:
                expected_fuzzy_count += 1

            if predicted_fuzzy:
                predicted_fuzzy_count += 1

            fuzzy_success = (
                expected_fuzzy
                and predicted_fuzzy
                and payment_correct
                and settlement_correct
                and bank_correct
            )

            if fuzzy_success:
                successful_fuzzy_count += 1
            case_rows.append(
                {
                    "invoice_id":
                        invoice_id,

                    "scenario":
                        scenario,

                    "prediction_present":
                        True,

                    "status_correct":
                        status_correct,

                    "root_cause_correct":
                        root_correct,

                    "payment_links_correct":
                        payment_correct,

                    "settlement_links_correct":
                        settlement_correct,

                    "bank_links_correct":
                        bank_correct,

                    "end_to_end_correct":
                        end_to_end_correct,

                    "expected_status":
                        expected_status,

                    "predicted_status":
                        predicted_status,

                    "expected_root_cause":
                        expected_cause,

                    "predicted_root_cause":
                        predicted_cause,

                    "predicted_match_method":
                        predicted_method,
                }
            )

        total_cases = len(
            truth
        )

        payment_metrics = linkage_metrics(
            payment_expected,
            payment_predicted,
        )

        settlement_metrics = linkage_metrics(
            settlement_expected,
            settlement_predicted,
        )

        bank_metrics = linkage_metrics(
            bank_expected,
            bank_predicted,
        )

        fuzzy_precision = (
            successful_fuzzy_count
            / predicted_fuzzy_count
            if predicted_fuzzy_count
            else 1.0
        )

        fuzzy_recall = (
            successful_fuzzy_count
            / expected_fuzzy_count
            if expected_fuzzy_count
            else 1.0
        )

        fuzzy_f1 = (
            2
            * fuzzy_precision
            * fuzzy_recall
            / (
                fuzzy_precision
                + fuzzy_recall
            )
            if (
                fuzzy_precision
                + fuzzy_recall
            )
            else 0.0
        )

        per_scenario = {}

        for scenario in sorted(
            scenario_stats
        ):

            total = scenario_stats[
                scenario
            ]["total"]

            correct = scenario_stats[
                scenario
            ]["correct"]

            per_scenario[
                scenario
            ] = {
                "cases":
                    total,

                "end_to_end_correct":
                    correct,

                "accuracy_pct":
                    percentage(
                        correct,
                        total,
                    ),
            }

        case_dataframe = pd.DataFrame(
            case_rows
        )

        failures = case_dataframe[
            ~case_dataframe[
                "end_to_end_correct"
            ]
        ].copy()

        summary = {
            "cases_evaluated":
                total_cases,

            "predictions_present":
                total_cases
                - len(missing_predictions),

            "missing_predictions_count":
                len(missing_predictions),

            "unexpected_predictions_count":
                len(unexpected_predictions),

            "status_accuracy_pct":
                percentage(
                    status_correct_count,
                    total_cases,
                ),

            "root_cause_accuracy_pct":
                percentage(
                    root_correct_count,
                    total_cases,
                ),

            "end_to_end_case_accuracy_pct":
                percentage(
                    end_to_end_correct_count,
                    total_cases,
                ),

            "end_to_end_correct_cases":
                end_to_end_correct_count,

            "payment_linkage":
                payment_metrics,

            "settlement_linkage":
                settlement_metrics,

            "bank_linkage":
                bank_metrics,

            "fuzzy_recovery": {
                "expected_fuzzy_cases":
                    expected_fuzzy_count,

                "predicted_fuzzy_cases":
                    predicted_fuzzy_count,

                "successful_fuzzy_cases":
                    successful_fuzzy_count,

                "false_or_incorrect_fuzzy_cases":
                    predicted_fuzzy_count
                    - successful_fuzzy_count,

                "precision_pct":
                    round(
                        fuzzy_precision
                        * 100,
                        2,
                    ),

                "recall_pct":
                    round(
                        fuzzy_recall
                        * 100,
                        2,
                    ),

                "f1_pct":
                    round(
                        fuzzy_f1
                        * 100,
                        2,
                    ),
            },

            # =================================================
            # AUTO-RESOLUTION SAFETY
            # =================================================

            "auto_resolution_safety": {
                "cases_evaluated":
                    auto_resolution_cases_evaluated,

                "expected_auto_resolve":
                    expected_auto_resolve_count,

                "predicted_auto_resolve":
                    predicted_auto_resolve_count,

                "correct_policy_decisions":
                    auto_resolution_correct_count,

                "unsafe_auto_resolutions":
                    unsafe_auto_resolve_count,

                "missed_safe_automations":
                    missed_auto_resolve_count,

                "policy_accuracy_pct":
                    percentage(
                        auto_resolution_correct_count,
                        auto_resolution_cases_evaluated,
                    ),
            },

            "failure_count":
                len(failures),

            "missing_prediction_ids":
                missing_predictions,

            "unexpected_prediction_ids":
                unexpected_predictions,

            "per_scenario":
                per_scenario,

            "methodology_note": (
                "Operational predictions are produced "
                "without access to ground truth. "
                "FUZZY_REFERENCE is evaluated as a "
                "matching challenge rather than a "
                "financial root cause."
            ),
        }

        if write_reports:

            self._write_reports(
                summary,
                case_dataframe,
                failures,
            )

        return summary

    # ========================================================
    # REPORT OUTPUT
    # ========================================================

    def _write_reports(
        self,
        summary,
        cases,
        failures,
    ):

        self.report_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        (
            self.report_dir
            / "benchmark_metrics.json"
        ).write_text(
            json.dumps(
                summary,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        cases.to_csv(
            self.report_dir
            / "benchmark_cases.csv",
            index=False,
        )

        failures.to_csv(
            self.report_dir
            / "benchmark_failures.csv",
            index=False,
        )


# ============================================================
# TERMINAL REPORT
# ============================================================


def print_report(
    report: dict[str, Any],
) -> None:

    print()
    print(
        "=============================================="
    )
    print(
        " FLOWGUARD BENCHMARK EVALUATION"
    )
    print(
        "=============================================="
    )
    print()

    print(
        f"Cases evaluated:          "
        f"{report['cases_evaluated']}"
    )

    print(
        f"Status accuracy:          "
        f"{report['status_accuracy_pct']}%"
    )

    print(
        f"Root-cause accuracy:      "
        f"{report['root_cause_accuracy_pct']}%"
    )

    print(
        f"End-to-end accuracy:      "
        f"{report['end_to_end_case_accuracy_pct']}%"
    )

    print()
    print("--- RECORD LINKAGE ---")
    print()

    for label, key in [
        (
            "Payment",
            "payment_linkage",
        ),
        (
            "Settlement",
            "settlement_linkage",
        ),
        (
            "Bank",
            "bank_linkage",
        ),
    ]:

        metrics = report[key]

        print(
            f"{label:<12}"
            f"P={metrics['precision_pct']:>6.2f}%  "
            f"R={metrics['recall_pct']:>6.2f}%  "
            f"F1={metrics['f1_pct']:>6.2f}%"
        )

    fuzzy = report[
        "fuzzy_recovery"
    ]

    print()
    print("--- FUZZY RECOVERY ---")
    print()

    print(
        f"Expected fuzzy cases:     "
        f"{fuzzy['expected_fuzzy_cases']}"
    )

    print(
        f"Recovered correctly:      "
        f"{fuzzy['successful_fuzzy_cases']}"
    )

    print(
        f"False/incorrect fuzzy:    "
        f"{fuzzy['false_or_incorrect_fuzzy_cases']}"
    )

    print(
        f"Fuzzy precision:          "
        f"{fuzzy['precision_pct']}%"
    )

    print(
        f"Fuzzy recall:             "
        f"{fuzzy['recall_pct']}%"
    )

    print()
    print(
        f"Benchmark failures:       "
        f"{report['failure_count']}"
    )

    print()
    print(
        "=============================================="
    )


def main():

    evaluator = (
        BenchmarkEvaluator()
    )

    report = evaluator.evaluate(
        write_reports=True
    )

    print_report(
        report
    )

    print()
    print(
        "Reports saved to:"
    )
    print(
        DEFAULT_REPORT_DIR
    )
    print()


if __name__ == "__main__":
    main()