from pathlib import Path
import pandas as pd


DATA_DIR = Path(__file__).resolve().parents[2] / "data"


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


REQUIRED_FILES = [
    "customers.csv",
    "invoices.csv",
    "payments.csv",
    "settlements.csv",
    "bank_transactions.csv",
    "refunds.csv",
    "chargebacks.csv",
    "expenses.csv",
    "ground_truth.csv",
]


def check(condition, message, errors):
    if condition:
        print(f"✅ {message}")
    else:
        print(f"❌ {message}")
        errors.append(message)


def main():

    print("\n========================================")
    print(" FLOWGUARD DATASET VALIDATION")
    print("========================================\n")

    errors = []

    # --------------------------------------------------------
    # 1. Check files
    # --------------------------------------------------------

    for filename in REQUIRED_FILES:
        path = DATA_DIR / filename

        check(
            path.exists(),
            f"{filename} exists",
            errors
        )

    if errors:
        print("\n❌ Missing files detected.")
        return

    # --------------------------------------------------------
    # 2. Load data
    # --------------------------------------------------------

    customers = pd.read_csv(DATA_DIR / "customers.csv")
    invoices = pd.read_csv(DATA_DIR / "invoices.csv")
    payments = pd.read_csv(DATA_DIR / "payments.csv")
    settlements = pd.read_csv(DATA_DIR / "settlements.csv")
    banks = pd.read_csv(DATA_DIR / "bank_transactions.csv")
    refunds = pd.read_csv(DATA_DIR / "refunds.csv")
    chargebacks = pd.read_csv(DATA_DIR / "chargebacks.csv")
    expenses = pd.read_csv(DATA_DIR / "expenses.csv")
    truth = pd.read_csv(DATA_DIR / "ground_truth.csv")

    print("\n--- BASIC ROW COUNTS ---\n")

    check(len(customers) == 20, "20 customers generated", errors)

    check(
        len(invoices) == 100,
        "100 invoice cases generated",
        errors
    )

    check(
        len(truth) == 100,
        "100 ground-truth cases generated",
        errors
    )

    check(
        len(payments) == 100,
        "Payment row count is correct",
        errors
    )

    check(
        len(settlements) == 100,
        "Settlement row count is correct",
        errors
    )

    check(
        len(banks) == 96,
        "Bank transaction row count is correct",
        errors
    )

    check(
        len(refunds) == 8,
        "Refund row count is correct",
        errors
    )

    check(
        len(chargebacks) == 5,
        "Chargeback row count is correct",
        errors
    )

    check(
        len(expenses) == 40,
        "40 future expenses generated",
        errors
    )

    # --------------------------------------------------------
    # 3. Unique IDs
    # --------------------------------------------------------

    print("\n--- UNIQUE ID CHECKS ---\n")

    check(
        customers["customer_id"].is_unique,
        "Customer IDs are unique",
        errors
    )

    check(
        invoices["invoice_id"].is_unique,
        "Invoice IDs are unique",
        errors
    )

    check(
        payments["payment_id"].is_unique,
        "Payment IDs are unique",
        errors
    )

    check(
        settlements["settlement_id"].is_unique,
        "Settlement IDs are unique",
        errors
    )

    check(
        banks["bank_txn_id"].is_unique,
        "Bank transaction IDs are unique",
        errors
    )

    check(
        refunds["refund_id"].is_unique,
        "Refund IDs are unique",
        errors
    )

    check(
        chargebacks["chargeback_id"].is_unique,
        "Chargeback IDs are unique",
        errors
    )

    # --------------------------------------------------------
    # 4. Scenario distribution
    # --------------------------------------------------------

    print("\n--- SCENARIO DISTRIBUTION ---\n")

    actual_counts = truth["scenario"].value_counts().to_dict()

    for scenario, expected_count in EXPECTED_SCENARIOS.items():

        actual = actual_counts.get(scenario, 0)

        check(
            actual == expected_count,
            f"{scenario}: {actual}/{expected_count}",
            errors
        )

    # --------------------------------------------------------
    # 5. Missing-payment cases
    # --------------------------------------------------------

    print("\n--- FAILURE CASE VALIDATION ---\n")

    missing_payment_cases = truth[
        truth["scenario"] == "MISSING_PAYMENT"
    ]["case_id"]

    for case_id in missing_payment_cases:

        count = len(
            payments[
                payments["case_id"] == case_id
            ]
        )

        check(
            count == 0,
            f"{case_id}: missing payment correctly created",
            errors
        )

    # --------------------------------------------------------
    # 6. Duplicate-payment cases
    # --------------------------------------------------------

    duplicate_cases = truth[
        truth["scenario"] == "DUPLICATE_PAYMENT"
    ]["case_id"]

    for case_id in duplicate_cases:

        count = len(
            payments[
                payments["case_id"] == case_id
            ]
        )

        check(
            count == 2,
            f"{case_id}: duplicate payment correctly created",
            errors
        )

    # --------------------------------------------------------
    # 7. Missing bank entries
    # --------------------------------------------------------

    missing_bank_cases = truth[
        truth["scenario"] == "MISSING_BANK_ENTRY"
    ]["case_id"]

    for case_id in missing_bank_cases:

        count = len(
            banks[
                banks["case_id"] == case_id
            ]
        )

        check(
            count == 0,
            f"{case_id}: missing bank entry correctly created",
            errors
        )

    # --------------------------------------------------------
    # 8. Refund validation
    # --------------------------------------------------------

    full_refund_cases = truth[
        truth["scenario"] == "FULL_REFUND"
    ]["case_id"]

    for case_id in full_refund_cases:

        case_refunds = refunds[
            refunds["case_id"] == case_id
        ]

        check(
            len(case_refunds) == 1,
            f"{case_id}: full refund record exists",
            errors
        )

    partial_refund_cases = truth[
        truth["scenario"] == "PARTIAL_REFUND"
    ]["case_id"]

    for case_id in partial_refund_cases:

        case_refunds = refunds[
            refunds["case_id"] == case_id
        ]

        check(
            len(case_refunds) == 1,
            f"{case_id}: partial refund record exists",
            errors
        )

    # --------------------------------------------------------
    # 9. Chargeback validation
    # --------------------------------------------------------

    chargeback_cases = truth[
        truth["scenario"] == "CHARGEBACK"
    ]["case_id"]

    for case_id in chargeback_cases:

        count = len(
            chargebacks[
                chargebacks["case_id"] == case_id
            ]
        )

        check(
            count == 1,
            f"{case_id}: chargeback correctly created",
            errors
        )

    # --------------------------------------------------------
    # 10. Financial sanity checks
    # --------------------------------------------------------

    print("\n--- FINANCIAL SANITY CHECKS ---\n")

    check(
        (invoices["invoice_amount"] > 0).all(),
        "All invoice amounts are positive",
        errors
    )

    check(
        (payments["amount"] > 0).all(),
        "All payment amounts are positive",
        errors
    )

    check(
        (settlements["expected_net"] >= 0).all(),
        "No negative settlement amounts",
        errors
    )

    check(
        (banks["amount"] >= 0).all(),
        "No negative bank transaction amounts",
        errors
    )

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    print("\n========================================")

    if len(errors) == 0:

        print("✅ DATASET VALIDATION PASSED")
        print()
        print("The FlowGuard reconciliation benchmark")
        print("is ready for use.")
        print()
        print("100 controlled finance cases verified.")

    else:

        print("❌ DATASET VALIDATION FAILED")
        print()
        print(f"{len(errors)} issue(s) detected:")
        print()

        for error in errors:
            print(f" - {error}")

    print("========================================\n")


if __name__ == "__main__":
    main()