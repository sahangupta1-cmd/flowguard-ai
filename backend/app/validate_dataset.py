from pathlib import Path
import pandas as pd


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_DIR = PROJECT_ROOT / "data" / "raw"
EVALUATION_DIR = PROJECT_ROOT / "data" / "evaluation"


# ============================================================
# EXPECTED BENCHMARK
# ============================================================

EXPECTED_SCENARIOS = {
    "CLEAN": 35,
    "GATEWAY_FEE_GST": 10,
    "FULL_REFUND": 3,
    "PARTIAL_REFUND": 5,
    "CHARGEBACK": 5,
    "FUZZY_REFERENCE": 8,
    "PARTIAL_PAYMENT": 6,
    "SETTLEMENT_DELAY": 5,
    "DUPLICATE_PAYMENT": 5,
    "MISSING_PAYMENT": 5,
    "MISSING_BANK_ENTRY": 4,
    "AMOUNT_MISMATCH": 4,
    "UNRESOLVED": 5,
}


RAW_FILES = [
    "customers.csv",
    "invoices.csv",
    "payments.csv",
    "settlements.csv",
    "bank_transactions.csv",
    "refunds.csv",
    "chargebacks.csv",
    "expenses.csv",
]


FORBIDDEN_RAW_COLUMNS = {
    "case_id",
    "benchmark_id",
    "scenario",
    "true_status",
    "true_root_cause",
    "should_auto_resolve",
    "expected_payment_ids",
    "expected_settlement_ids",
    "expected_bank_txn_ids",
}


# ============================================================
# TEST HELPER
# ============================================================

def check(condition, message, errors):

    if condition:
        print(f"✅ {message}")

    else:
        print(f"❌ {message}")
        errors.append(message)


# ============================================================
# MAIN VALIDATOR
# ============================================================

def main():

    print()
    print("==============================================")
    print(" FLOWGUARD REVIEWER-SAFE DATASET VALIDATION")
    print("==============================================")
    print()

    errors = []

    # ========================================================
    # 1. DIRECTORY STRUCTURE
    # ========================================================

    print("--- DIRECTORY STRUCTURE ---")
    print()

    check(
        RAW_DIR.exists(),
        "data/raw directory exists",
        errors,
    )

    check(
        EVALUATION_DIR.exists(),
        "data/evaluation directory exists",
        errors,
    )

    # ========================================================
    # 2. FILE EXISTENCE
    # ========================================================

    print()
    print("--- REQUIRED FILES ---")
    print()

    for filename in RAW_FILES:

        check(
            (RAW_DIR / filename).exists(),
            f"raw/{filename} exists",
            errors,
        )

    truth_path = (
        EVALUATION_DIR / "ground_truth.csv"
    )

    check(
        truth_path.exists(),
        "evaluation/ground_truth.csv exists",
        errors,
    )

    if errors:
        print()
        print("❌ Required files are missing.")
        return

    # ========================================================
    # 3. LOAD DATA
    # ========================================================

    customers = pd.read_csv(
        RAW_DIR / "customers.csv"
    )

    invoices = pd.read_csv(
        RAW_DIR / "invoices.csv"
    )

    payments = pd.read_csv(
        RAW_DIR / "payments.csv"
    )

    settlements = pd.read_csv(
        RAW_DIR / "settlements.csv"
    )

    banks = pd.read_csv(
        RAW_DIR / "bank_transactions.csv"
    )

    refunds = pd.read_csv(
        RAW_DIR / "refunds.csv"
    )

    chargebacks = pd.read_csv(
        RAW_DIR / "chargebacks.csv"
    )

    expenses = pd.read_csv(
        RAW_DIR / "expenses.csv"
    )

    truth = pd.read_csv(
        truth_path
    )

    raw_datasets = {
        "customers": customers,
        "invoices": invoices,
        "payments": payments,
        "settlements": settlements,
        "banks": banks,
        "refunds": refunds,
        "chargebacks": chargebacks,
        "expenses": expenses,
    }

    # ========================================================
    # 4. LABEL-LEAKAGE CHECK
    # ========================================================

    print()
    print("--- LABEL LEAKAGE CHECK ---")
    print()

    for dataset_name, dataframe in raw_datasets.items():

        leaked_columns = (
            set(dataframe.columns)
            & FORBIDDEN_RAW_COLUMNS
        )

        check(
            len(leaked_columns) == 0,
            (
                f"{dataset_name}: no benchmark "
                "or answer columns exposed"
            ),
            errors,
        )

        if leaked_columns:

            print(
                "   Leaked columns:",
                sorted(leaked_columns),
            )

    # ========================================================
    # 5. GROUND TRUTH ISOLATION
    # ========================================================

    print()
    print("--- EVALUATION ISOLATION ---")
    print()

    check(
        "benchmark_id" in truth.columns,
        "Ground truth contains benchmark IDs",
        errors,
    )

    check(
        "scenario" in truth.columns,
        "Ground truth contains scenario labels",
        errors,
    )

    check(
        "true_root_cause" in truth.columns,
        "Ground truth contains root-cause answers",
        errors,
    )

    check(
        len(truth) == 100,
        "Ground truth contains 100 benchmark cases",
        errors,
    )

    # ========================================================
    # 6. BASIC ROW COUNTS
    # ========================================================

    print()
    print("--- BASIC ROW COUNTS ---")
    print()

    check(
        len(customers) == 20,
        "20 customers generated",
        errors,
    )

    check(
        len(invoices) == 100,
        "100 invoice cases generated",
        errors,
    )

    check(
        len(payments) == 100,
        "Payment row count is correct",
        errors,
    )

    check(
        len(settlements) == 100,
        "Settlement row count is correct",
        errors,
    )

    check(
        len(banks) == 96,
        "Bank transaction row count is correct",
        errors,
    )

    check(
        len(refunds) == 8,
        "Refund row count is correct",
        errors,
    )

    check(
        len(chargebacks) == 5,
        "Chargeback row count is correct",
        errors,
    )

    check(
        len(expenses) == 40,
        "40 future expenses generated",
        errors,
    )

    # ========================================================
    # 7. UNIQUE NATIVE IDs
    # ========================================================

    print()
    print("--- UNIQUE NATIVE ID CHECKS ---")
    print()

    unique_checks = [
        (
            customers,
            "customer_id",
            "Customer IDs",
        ),
        (
            invoices,
            "invoice_id",
            "Invoice IDs",
        ),
        (
            payments,
            "payment_id",
            "Payment IDs",
        ),
        (
            settlements,
            "settlement_id",
            "Settlement IDs",
        ),
        (
            banks,
            "bank_txn_id",
            "Bank transaction IDs",
        ),
        (
            refunds,
            "refund_id",
            "Refund IDs",
        ),
        (
            chargebacks,
            "chargeback_id",
            "Chargeback IDs",
        ),
        (
            expenses,
            "expense_id",
            "Expense IDs",
        ),
    ]

    for dataframe, column, label in unique_checks:

        check(
            dataframe[column].is_unique,
            f"{label} are unique",
            errors,
        )

    # ========================================================
    # 8. SCENARIO DISTRIBUTION
    # Evaluation file only
    # ========================================================

    print()
    print("--- BENCHMARK DISTRIBUTION ---")
    print()

    actual_counts = (
        truth["scenario"]
        .value_counts()
        .to_dict()
    )

    for scenario, expected in EXPECTED_SCENARIOS.items():

        actual = actual_counts.get(
            scenario,
            0,
        )

        check(
            actual == expected,
            f"{scenario}: {actual}/{expected}",
            errors,
        )

    # ========================================================
    # 9. MISSING PAYMENT TESTS
    # ========================================================

    print()
    print("--- CONTROLLED FAILURE CASES ---")
    print()

    missing_payment_invoices = truth[
        truth["scenario"]
        == "MISSING_PAYMENT"
    ]["invoice_id"]

    for invoice_id in missing_payment_invoices:

        matching_payments = payments[
            payments["invoice_id"]
            == invoice_id
        ]

        check(
            len(matching_payments) == 0,
            (
                f"{invoice_id}: missing payment "
                "correctly generated"
            ),
            errors,
        )

    # ========================================================
    # 10. DUPLICATE PAYMENT TESTS
    # ========================================================

    duplicate_invoices = truth[
        truth["scenario"]
        == "DUPLICATE_PAYMENT"
    ]["invoice_id"]

    for invoice_id in duplicate_invoices:

        matching_payments = payments[
            payments["invoice_id"]
            == invoice_id
        ]

        check(
            len(matching_payments) == 2,
            (
                f"{invoice_id}: duplicate payments "
                "correctly generated"
            ),
            errors,
        )

    # ========================================================
    # 11. MISSING BANK ENTRY TESTS
    # ========================================================

    missing_bank_truth = truth[
        truth["scenario"]
        == "MISSING_BANK_ENTRY"
    ]

    for _, row in missing_bank_truth.iterrows():

        settlement_ids = str(
            row["expected_settlement_ids"]
        ).split("|")

        found = banks[
            banks["settlement_id"]
            .isin(settlement_ids)
        ]

        check(
            len(found) == 0,
            (
                f"{row['invoice_id']}: missing "
                "bank entry correctly generated"
            ),
            errors,
        )

    # ========================================================
    # 12. REFUND VALIDATION
    # ========================================================

    refund_truth = truth[
        truth["scenario"].isin(
            [
                "FULL_REFUND",
                "PARTIAL_REFUND",
            ]
        )
    ]

    for _, row in refund_truth.iterrows():

        found = refunds[
            refunds["invoice_id"]
            == row["invoice_id"]
        ]

        check(
            len(found) == 1,
            (
                f"{row['invoice_id']}: refund "
                "evidence exists"
            ),
            errors,
        )

    # ========================================================
    # 13. CHARGEBACK VALIDATION
    # ========================================================

    chargeback_truth = truth[
        truth["scenario"]
        == "CHARGEBACK"
    ]

    for _, row in chargeback_truth.iterrows():

        payment_ids = str(
            row["expected_payment_ids"]
        ).split("|")

        found = chargebacks[
            chargebacks["payment_id"]
            .isin(payment_ids)
        ]

        check(
            len(found) == 1,
            (
                f"{row['invoice_id']}: chargeback "
                "evidence exists"
            ),
            errors,
        )

        # ========================================================
    # 14. PAYMENT POLICY VALIDATION
    # ========================================================

    print()
    print("--- BUSINESS POLICY VALIDATION ---")
    print()

    allowed_policies = {
        "FULL_ONLY",
        "INSTALLMENTS_ALLOWED",
    }

    check(
        set(
            invoices["payment_policy"].unique()
        ).issubset(allowed_policies),
        "Invoice payment policies are valid",
        errors,
    )

    partial_invoice_ids = set(
        truth[
            truth["scenario"]
            == "PARTIAL_PAYMENT"
        ]["invoice_id"]
    )

    installment_invoice_ids = set(
        invoices[
            invoices["payment_policy"]
            == "INSTALLMENTS_ALLOWED"
        ]["invoice_id"]
    )

    check(
        partial_invoice_ids.issubset(
            installment_invoice_ids
        ),
        (
            "Every legitimate partial-payment case "
            "allows installments"
        ),
        errors,
    )

    non_partial_installment_ids = (
        installment_invoice_ids
        - partial_invoice_ids
    )

    check(
        len(non_partial_installment_ids) > 0,
        (
            "Installment policy also appears on "
            "non-partial cases, preventing label leakage"
        ),
        errors,
    )

    # ========================================================
    # 15. FINANCIAL SANITY
    # ========================================================

    print()
    print("--- FINANCIAL SANITY CHECKS ---")
    print()

    check(
        (
            invoices["invoice_amount"]
            > 0
        ).all(),
        "All invoice amounts are positive",
        errors,
    )

    check(
        (
            payments["amount"]
            > 0
        ).all(),
        "All payment amounts are positive",
        errors,
    )

    check(
        (
            settlements["expected_net"]
            >= 0
        ).all(),
        "No negative expected settlements",
        errors,
    )

    check(
        (
            banks["amount"]
            >= 0
        ).all(),
        "No negative bank credits",
        errors,
    )

    check(
        (
            refunds["amount"]
            > 0
        ).all(),
        "All refund amounts are positive",
        errors,
    )

    # ========================================================
    # FINAL RESULT
    # ========================================================

    print()
    print("==============================================")

    if not errors:

        print("✅ REVIEWER-SAFE DATASET VALIDATION PASSED")
        print()
        print(
            "100 controlled finance cases verified."
        )
        print(
            "No benchmark labels are exposed "
            "to the operational pipeline."
        )
        print()
        print(
            "STEP 1 IS READY TO BE FROZEN."
        )

    else:

        print("❌ DATASET VALIDATION FAILED")
        print()
        print(
            f"{len(errors)} issue(s) detected:"
        )
        print()

        for error in errors:
            print(f" - {error}")

    print("==============================================")
    print()


if __name__ == "__main__":
    main()