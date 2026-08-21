import pandas as pd

from backend.app.stress_data_generator import generate


FORBIDDEN_COLUMNS = {
    "stress_id",
    "benchmark_id",
    "case_id",
    "scenario",
    "true_status",
    "true_root_cause",
    "expected_payment_ids",
    "expected_settlement_ids",
    "expected_bank_txn_ids",
    "expected_match_method",
    "should_auto_resolve",
}


def test_stress_generator_creates_64_cases(
    tmp_path,
):

    stress_dir = (
        tmp_path
        / "stress"
    )

    generate(
        stress_dir
    )

    invoices = pd.read_csv(
        stress_dir
        / "raw"
        / "invoices.csv"
    )

    truth = pd.read_csv(
        stress_dir
        / "evaluation"
        / "ground_truth.csv"
    )

    assert len(invoices) == 64
    assert len(truth) == 64

    assert (
        invoices["invoice_id"]
        .is_unique
    )

    assert (
        truth["invoice_id"]
        .is_unique
    )


def test_every_stress_scenario_has_four_cases(
    tmp_path,
):

    stress_dir = (
        tmp_path
        / "stress"
    )

    generate(
        stress_dir
    )

    truth = pd.read_csv(
        stress_dir
        / "evaluation"
        / "ground_truth.csv"
    )

    counts = (
        truth["scenario"]
        .value_counts()
    )

    assert len(counts) == 16

    assert (
        counts == 4
    ).all()


def test_no_ground_truth_leaks_into_raw_data(
    tmp_path,
):

    stress_dir = (
        tmp_path
        / "stress"
    )

    generate(
        stress_dir
    )

    raw_dir = (
        stress_dir
        / "raw"
    )

    for path in (
        raw_dir.glob(
            "*.csv"
        )
    ):

        dataframe = pd.read_csv(
            path
        )

        leaked = (
            set(
                dataframe.columns
            )
            & FORBIDDEN_COLUMNS
        )

        assert not leaked, (
            f"{path.name} leaked "
            f"benchmark columns: "
            f"{sorted(leaked)}"
        )


def test_stress_suite_contains_safe_failure_cases(
    tmp_path,
):

    stress_dir = (
        tmp_path
        / "stress"
    )

    generate(
        stress_dir
    )

    truth = pd.read_csv(
        stress_dir
        / "evaluation"
        / "ground_truth.csv"
    )

    assert (
        truth[
            "true_status"
        ]
        == "HUMAN_REVIEW"
    ).any()

    assert (
        truth[
            "true_status"
        ]
        == "UNRESOLVED"
    ).any()

    assert (
        truth[
            "expected_match_method"
        ]
        == "FUZZY"
    ).any()

    assert (
        truth[
            "should_auto_resolve"
        ]
        == False
    ).any()