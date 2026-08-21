import pandas as pd

from backend.app.evaluation.evaluator import (
    BenchmarkEvaluator,
    expected_root_cause,
    parse_id_set,
)


def test_fuzzy_reference_is_not_financial_root_cause():

    assert (
        expected_root_cause(
            "FUZZY_REFERENCE"
        )
        == "CLEAN"
    )


def test_unresolved_maps_to_unexplained():

    assert (
        expected_root_cause(
            "UNRESOLVED"
        )
        == "UNEXPLAINED"
    )


def test_id_parser():

    assert parse_id_set(
        "PAY001|PAY002"
    ) == {
        "PAY001",
        "PAY002",
    }


def test_perfect_evaluation(
    tmp_path,
):

    truth = pd.DataFrame(
        [
            {
                "invoice_id": "INV001",
                "scenario": "CLEAN",
                "true_status": "RECONCILED",
                "true_root_cause": "CLEAN",
                "expected_payment_ids": "PAY001",
                "expected_settlement_ids": "SET001",
                "expected_bank_txn_ids": "BNK001",
            },
            {
                "invoice_id": "INV002",
                "scenario": "FUZZY_REFERENCE",
                "true_status": "RECONCILED",
                "true_root_cause": "FUZZY_REFERENCE",
                "expected_payment_ids": "PAY002",
                "expected_settlement_ids": "SET002",
                "expected_bank_txn_ids": "BNK002",
            },
        ]
    )

    predictions = pd.DataFrame(
        [
            {
                "invoice_id": "INV001",
                "payment_ids": "PAY001",
                "settlement_ids": "SET001",
                "bank_transaction_ids": "BNK001",
                "status": "RECONCILED",
                "root_cause": "CLEAN",
                "match_method": "EXACT_ID",
                "requires_review": False,
            },
            {
                "invoice_id": "INV002",
                "payment_ids": "PAY002",
                "settlement_ids": "SET002",
                "bank_transaction_ids": "BNK002",
                "status": "RECONCILED",
                "root_cause": "CLEAN",
                "match_method": "FUZZY",
                "requires_review": False,
            },
        ]
    )

    truth_path = (
        tmp_path
        / "truth.csv"
    )

    result_path = (
        tmp_path
        / "results.csv"
    )

    truth.to_csv(
        truth_path,
        index=False,
    )

    predictions.to_csv(
        result_path,
        index=False,
    )

    evaluator = BenchmarkEvaluator(
        truth_path=truth_path,
        results_path=result_path,
        report_dir=(
            tmp_path
            / "reports"
        ),
    )

    report = evaluator.evaluate(
        write_reports=False
    )

    assert (
        report[
            "status_accuracy_pct"
        ]
        == 100.0
    )

    assert (
        report[
            "root_cause_accuracy_pct"
        ]
        == 100.0
    )

    assert (
        report[
            "end_to_end_case_accuracy_pct"
        ]
        == 100.0
    )

    assert (
        report[
            "fuzzy_recovery"
        ][
            "precision_pct"
        ]
        == 100.0
    )

    assert (
        report[
            "fuzzy_recovery"
        ][
            "recall_pct"
        ]
        == 100.0
    )
def test_wrong_match_method_breaks_end_to_end_accuracy(
    tmp_path,
):
    truth = pd.DataFrame(
        [
            {
                "invoice_id": "INV001",
                "scenario": "CLEAN",
                "true_status": "RECONCILED",
                "true_root_cause": "CLEAN",
                "expected_payment_ids": "PAY001",
                "expected_settlement_ids": "SET001",
                "expected_bank_txn_ids": "BNK001",
                "expected_match_method": "EXACT_ID",
                "should_auto_resolve": True,
            }
        ]
    )

    predictions = pd.DataFrame(
        [
            {
                "invoice_id": "INV001",
                "payment_ids": "PAY001",
                "settlement_ids": "SET001",
                "bank_transaction_ids": "BNK001",
                "status": "RECONCILED",
                "root_cause": "CLEAN",
                "match_method": "FUZZY",
                "requires_review": False,
            }
        ]
    )

    truth_path = tmp_path / "truth.csv"
    result_path = tmp_path / "results.csv"

    truth.to_csv(
        truth_path,
        index=False,
    )

    predictions.to_csv(
        result_path,
        index=False,
    )

    evaluator = BenchmarkEvaluator(
        truth_path=truth_path,
        results_path=result_path,
        report_dir=tmp_path / "reports",
    )

    report = evaluator.evaluate(
        write_reports=False
    )

    assert (
        report[
            "end_to_end_case_accuracy_pct"
        ]
        == 0.0
    )

def test_unsafe_auto_resolution_is_detected(
    tmp_path,
):
    truth = pd.DataFrame(
        [
            {
                "invoice_id": "INV001",
                "scenario": "DUPLICATE_PAYMENT",
                "true_status": "EXPLAINED_EXCEPTION",
                "true_root_cause": "DUPLICATE_PAYMENT",
                "expected_payment_ids": "PAY001|PAY002",
                "expected_settlement_ids": "SET001|SET002",
                "expected_bank_txn_ids": "BNK001|BNK002",
                "expected_match_method": "EXACT_ID",
                "should_auto_resolve": False,
            }
        ]
    )

    predictions = pd.DataFrame(
        [
            {
                "invoice_id": "INV001",
                "payment_ids": "PAY001|PAY002",
                "settlement_ids": "SET001|SET002",
                "bank_transaction_ids": "BNK001|BNK002",
                "status": "EXPLAINED_EXCEPTION",
                "root_cause": "DUPLICATE_PAYMENT",
                "match_method": "EXACT_ID",
                "requires_review": False,
            }
        ]
    )

    truth_path = tmp_path / "truth.csv"
    result_path = tmp_path / "results.csv"

    truth.to_csv(
        truth_path,
        index=False,
    )

    predictions.to_csv(
        result_path,
        index=False,
    )

    evaluator = BenchmarkEvaluator(
        truth_path=truth_path,
        results_path=result_path,
        report_dir=tmp_path / "reports",
    )

    report = evaluator.evaluate(
        write_reports=False
    )

    safety = report[
        "auto_resolution_safety"
    ]

    assert (
        safety[
            "unsafe_auto_resolutions"
        ]
        == 1
    )

    assert (
        report[
            "end_to_end_case_accuracy_pct"
        ]
        == 0.0
    )