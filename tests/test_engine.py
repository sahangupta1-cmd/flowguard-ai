from pathlib import Path

import pandas as pd
import pytest

from backend.app.reconciliation.engine import (
    ReconciliationEngine,
)
from backend.app.reconciliation.models import (
    RootCause,
)


# ============================================================
# TEST DATASET
# ============================================================


def write_dataset(
    raw_dir: Path,
    *,
    leak_label: bool = False,
) -> None:

    raw_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    invoices = pd.DataFrame(
        [
            {
                "invoice_id": "INV002",
                "customer_id": "C002",
                "customer_name": "Beta Ltd",
                "invoice_amount": 200000,
                "issue_date": "2026-08-01",
                "due_date": "2026-08-15",
                "payment_policy": "FULL_ONLY",
            },
            {
                "invoice_id": "INV001",
                "customer_id": "C001",
                "customer_name": "Nova Ltd",
                "invoice_amount": 100000,
                "issue_date": "2026-08-01",
                "due_date": "2026-08-10",
                "payment_policy": "FULL_ONLY",
            },
        ]
    )

    if leak_label:

        invoices["scenario"] = [
            "MISSING_PAYMENT",
            "CLEAN",
        ]

    payments = pd.DataFrame(
        [
            {
                "payment_id": "PAY001",
                "invoice_id": "INV001",
                "customer_id": "C001",
                "amount": 100000,
                "payment_date": "2026-08-10",
                "payment_method": "UPI",
                "payment_status": "SUCCESS",
                "reference": "REF-INV001-PAY001",
            }
        ]
    )

    settlements = pd.DataFrame(
        [
            {
                "settlement_id": "SET001",
                "payment_id": "PAY001",
                "gross_amount": 100000,
                "gateway_fee": 0,
                "gst_on_fee": 0,
                "refund_adjustment": 0,
                "chargeback_adjustment": 0,
                "other_adjustment": 0,
                "expected_net": 100000,
                "settlement_date": "2026-08-12",
                "reference": "STL-PAY001",
            }
        ]
    )

    banks = pd.DataFrame(
        [
            {
                "bank_txn_id": "BNK001",
                "settlement_id": "SET001",
                "reference": "BANK-SET001",
                "amount": 100000,
                "transaction_date": "2026-08-12",
                "description":
                    "Settlement credit Nova",
            }
        ]
    )

    refunds = pd.DataFrame(
        columns=[
            "refund_id",
            "payment_id",
            "invoice_id",
            "amount",
            "refund_date",
            "refund_status",
        ]
    )

    chargebacks = pd.DataFrame(
        columns=[
            "chargeback_id",
            "payment_id",
            "amount",
            "chargeback_date",
            "status",
            "reason",
        ]
    )

    datasets = {
        "invoices.csv":
            invoices,

        "payments.csv":
            payments,

        "settlements.csv":
            settlements,

        "bank_transactions.csv":
            banks,

        "refunds.csv":
            refunds,

        "chargebacks.csv":
            chargebacks,
    }

    for filename, dataframe in (
        datasets.items()
    ):

        dataframe.to_csv(
            raw_dir / filename,
            index=False,
        )


# ============================================================
# FULL BATCH
# ============================================================


def test_engine_processes_batch(
    tmp_path,
):

    raw_dir = (
        tmp_path
        / "raw"
    )

    write_dataset(
        raw_dir
    )

    engine = ReconciliationEngine(
        raw_dir=raw_dir,
        output_dir=(
            tmp_path
            / "output"
        ),
    )

    run = engine.run(
        write_outputs=False
    )

    assert len(
        run.results
    ) == 2

    assert (
        run.summary[
            "cases_processed"
        ]
        == 2
    )

    by_invoice = {
        result.invoice_id:
            result
        for result in run.results
    }

    assert (
        by_invoice[
            "INV001"
        ].root_cause
        == RootCause.CLEAN
    )

    assert (
        by_invoice[
            "INV002"
        ].root_cause
        == RootCause.MISSING_PAYMENT
    )


# ============================================================
# NO GROUND TRUTH DEPENDENCY
# ============================================================


def test_engine_runs_without_ground_truth(
    tmp_path,
):

    raw_dir = (
        tmp_path
        / "raw"
    )

    write_dataset(
        raw_dir
    )

    # Deliberately do NOT create any evaluation folder
    # or ground_truth.csv.

    engine = ReconciliationEngine(
        raw_dir=raw_dir,
        output_dir=(
            tmp_path
            / "output"
        ),
    )

    run = engine.run(
        write_outputs=False
    )

    assert (
        run.summary[
            "cases_processed"
        ]
        == 2
    )


# ============================================================
# BENCHMARK LEAKAGE DEFENSE
# ============================================================


def test_engine_rejects_benchmark_labels(
    tmp_path,
):

    raw_dir = (
        tmp_path
        / "raw"
    )

    write_dataset(
        raw_dir,
        leak_label=True,
    )

    engine = ReconciliationEngine(
        raw_dir=raw_dir,
        output_dir=(
            tmp_path
            / "output"
        ),
    )

    with pytest.raises(
        ValueError,
        match=(
            "forbidden benchmark/evaluation"
        ),
    ):

        engine.run(
            write_outputs=False
        )


# ============================================================
# OUTPUT FILES
# ============================================================


def test_engine_writes_auditable_outputs(
    tmp_path,
):

    raw_dir = (
        tmp_path
        / "raw"
    )

    output_dir = (
        tmp_path
        / "output"
    )

    write_dataset(
        raw_dir
    )

    engine = ReconciliationEngine(
        raw_dir=raw_dir,
        output_dir=output_dir,
    )

    engine.run(
        write_outputs=True
    )

    results_path = (
        output_dir
        / "reconciliation_results.csv"
    )

    summary_path = (
        output_dir
        / "run_summary.json"
    )

    assert results_path.exists()

    assert summary_path.exists()

    results = pd.read_csv(
        results_path
    )

    assert len(results) == 2

    assert "evidence" in results.columns

    # Operational output must not contain hidden answers.
    assert (
        "scenario"
        not in results.columns
    )

    assert (
        "true_root_cause"
        not in results.columns
    )