from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import random
import re

import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

SEED = 42
random.seed(SEED)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_DIR = PROJECT_ROOT / "data" / "raw"
EVALUATION_DIR = PROJECT_ROOT / "data" / "evaluation"

RAW_DIR.mkdir(parents=True, exist_ok=True)
EVALUATION_DIR.mkdir(parents=True, exist_ok=True)


SCENARIO_COUNTS = {
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


CUSTOMER_NAMES = [
    "Alpha Retail Pvt Ltd",
    "Nova Technologies Pvt Ltd",
    "Horizon Foods LLP",
    "BluePeak Logistics Pvt Ltd",
    "Vertex Consulting LLP",
    "GreenCart Commerce Pvt Ltd",
    "Orbit Systems Pvt Ltd",
    "Cedar Healthcare Pvt Ltd",
    "Nimbus Learning Pvt Ltd",
    "UrbanNest Interiors LLP",
    "Silverline Manufacturing Pvt Ltd",
    "Aster Mobility Pvt Ltd",
    "BrightGrid Energy Pvt Ltd",
    "PixelCraft Media LLP",
    "PrimeLeaf Consumer Products Pvt Ltd",
    "CloudArc Solutions Pvt Ltd",
    "MetroMart Retail LLP",
    "NorthStar Components Pvt Ltd",
    "SwiftRoute Services Pvt Ltd",
    "Zenith Business Solutions LLP",
]

INDUSTRIES = [
    "Retail",
    "IT Services",
    "FMCG",
    "Logistics",
    "Consulting",
    "E-commerce",
    "SaaS",
    "Healthcare",
    "EdTech",
    "Manufacturing",
]

PAYMENT_METHODS = [
    "UPI",
    "CARD",
    "NETBANKING",
    "BANK_TRANSFER",
]


# ============================================================
# HELPERS
# ============================================================

def money(value: float) -> int:
    return int(round(value))


def noisy_name(name: str) -> str:
    replacements = {
        "Private Limited": "PVT LTD",
        "Pvt Ltd": "PVT LTD",
        "Technologies": "TECH",
        "Services": "SRVCS",
        "Solutions": "SOLNS",
        "Retail": "RTL",
    }

    result = name

    for original, replacement in replacements.items():
        result = result.replace(original, replacement)

    result = re.sub(r"[^A-Za-z0-9 ]", "", result)
    result = re.sub(r"\s+", " ", result).strip()

    return result.upper()


def build_scenario_list() -> list[str]:
    scenarios = []

    for scenario, count in SCENARIO_COUNTS.items():
        scenarios.extend([scenario] * count)

    random.shuffle(scenarios)

    assert len(scenarios) == 100

    return scenarios


# ============================================================
# CUSTOMERS
# ============================================================

def make_customers() -> pd.DataFrame:
    rows = []

    for i, name in enumerate(CUSTOMER_NAMES, start=1):
        rows.append(
            {
                "customer_id": f"C{i:03d}",
                "customer_name": name,
                "industry": random.choice(INDUSTRIES),
                "payment_terms_days": random.choice([15, 30, 45]),
            }
        )

    return pd.DataFrame(rows)


# ============================================================
# GENERATOR
# ============================================================

def generate():

    customers = make_customers()

    customer_lookup = (
        customers
        .set_index("customer_id")
        .to_dict("index")
    )

    invoices = []
    payments = []
    settlements = []
    bank_transactions = []
    refunds = []
    chargebacks = []
    expenses = []

    # Evaluation-only answer sheet.
    ground_truth = []

    scenarios = build_scenario_list()

    base_date = date(2026, 5, 1)

    payment_counter = 1
    settlement_counter = 1
    bank_counter = 1
    refund_counter = 1
    chargeback_counter = 1

    for idx, scenario in enumerate(scenarios, start=1):

        benchmark_id = f"CASE{idx:03d}"
        invoice_id = f"INV{idx:03d}"

        customer_id = (
            f"C{((idx - 1) % len(customers)) + 1:03d}"
        )

        customer = customer_lookup[customer_id]

        issue_date = (
            base_date
            + timedelta(days=random.randint(0, 90))
        )

        due_date = (
            issue_date
            + timedelta(days=customer["payment_terms_days"])
        )

        invoice_amount = random.randrange(
            10_000,
            500_001,
            500,
        )

                # ----------------------------------------------------
        # Legitimate business payment policy
        #
        # INSTALLMENTS_ALLOWED must not reveal that a case is
        # necessarily a partial-payment scenario.
        #
        # Some fully paid invoices also permit installments,
        # preventing the policy field from acting as a hidden
        # benchmark label.
        # ----------------------------------------------------

        if scenario == "PARTIAL_PAYMENT":
            payment_policy = "INSTALLMENTS_ALLOWED"

        elif scenario == "AMOUNT_MISMATCH":
            # An unexplained amount mismatch must not be
            # mistaken for a legitimate installment payment.
            payment_policy = "FULL_ONLY"

        elif idx % 4 == 0:
            # Some ordinary invoices legitimately permit
            # installments even when paid completely.
            payment_policy = "INSTALLMENTS_ALLOWED"

        else:
            payment_policy = "FULL_ONLY"

        invoices.append(
            {
                "invoice_id": invoice_id,
                "customer_id": customer_id,
                "customer_name": customer["customer_name"],
                "invoice_amount": invoice_amount,
                "issue_date": issue_date.isoformat(),
                "due_date": due_date.isoformat(),
                "payment_policy": payment_policy,
                "currency": "INR",
            }
        )

        truth = {
            "benchmark_id": benchmark_id,
            "invoice_id": invoice_id,
            "scenario": scenario,
            "true_status": "",
            "true_root_cause": scenario,
            "expected_payment_ids": "",
            "expected_settlement_ids": "",
            "expected_bank_txn_ids": "",
            "true_invoice_amount": invoice_amount,
            "true_net_settlement": "",
            "true_payment_delay_days": "",
            "should_auto_resolve": True,
        }

        

        # ====================================================
        # MISSING PAYMENT
        # ====================================================

        if scenario == "MISSING_PAYMENT":

            truth["true_status"] = "UNRESOLVED"
            truth["should_auto_resolve"] = False

            ground_truth.append(truth)
            continue

        # ====================================================
        # PAYMENT AMOUNT
        # ====================================================

        payment_amount = invoice_amount

        if scenario == "PARTIAL_PAYMENT":

            payment_amount = money(
                invoice_amount
                * random.choice([0.40, 0.50, 0.60, 0.75])
            )

        elif scenario == "AMOUNT_MISMATCH":

            difference = random.choice(
                [2500, 5000, 7500, 10000]
            )

            payment_amount = max(
                500,
                invoice_amount - difference,
            )

        # ====================================================
        # PAYMENT TIMING
        # ====================================================

        delay_days = random.choices(
            population=[
                -2,
                0,
                2,
                5,
                10,
                20,
                35,
            ],
            weights=[
                5,
                25,
                20,
                15,
                15,
                12,
                8,
            ],
            k=1,
        )[0]

        payment_date = (
            due_date
            + timedelta(days=delay_days)
        )

        payment_id = f"PAY{payment_counter:04d}"
        payment_counter += 1

        payment_invoice_id = invoice_id
        payment_reference = f"REF-{invoice_id}-{payment_id}"

        # ----------------------------------------------------
        # Fuzzy-reference case deliberately loses invoice ID
        # ----------------------------------------------------

        if scenario == "FUZZY_REFERENCE":

            payment_invoice_id = ""

            payment_reference = (
                f"{noisy_name(customer['customer_name'])} "
                f"{invoice_amount} "
                f"{issue_date.strftime('%d%m')}"
            )

        payments.append(
            {
                "payment_id": payment_id,
                "invoice_id": payment_invoice_id,
                "customer_id": customer_id,
                "amount": payment_amount,
                "payment_date": payment_date.isoformat(),
                "payment_method": random.choice(PAYMENT_METHODS),
                "payment_status": "SUCCESS",
                "reference": payment_reference,
            }
        )

        payment_ids = [payment_id]

        # ====================================================
        # DUPLICATE PAYMENT
        # ====================================================

        if scenario == "DUPLICATE_PAYMENT":

            duplicate_id = f"PAY{payment_counter:04d}"
            payment_counter += 1

            payments.append(
                {
                    "payment_id": duplicate_id,
                    "invoice_id": invoice_id,
                    "customer_id": customer_id,
                    "amount": payment_amount,
                    "payment_date": (
                        payment_date + timedelta(days=1)
                    ).isoformat(),
                    "payment_method": random.choice(PAYMENT_METHODS),
                    "payment_status": "SUCCESS",
                    "reference": f"REF-{invoice_id}-{duplicate_id}",
                }
            )

            payment_ids.append(duplicate_id)

        settlement_ids = []
        bank_ids = []

        total_true_net = 0

        # ====================================================
        # SETTLEMENTS
        # ====================================================

        for payment_index, current_payment_id in enumerate(payment_ids):

            gross_amount = payment_amount

            gateway_fee = 0
            gst_on_fee = 0
            refund_adjustment = 0
            chargeback_adjustment = 0
            other_adjustment = 0

            # ------------------------------------------------
            # Gateway fee + GST
            # ------------------------------------------------

            if scenario == "GATEWAY_FEE_GST":

                gateway_fee = money(
                    gross_amount * 0.02
                )

                gst_on_fee = money(
                    gateway_fee * 0.18
                )

            # ------------------------------------------------
            # Full refund
            # ------------------------------------------------

            if (
                scenario == "FULL_REFUND"
                and payment_index == 0
            ):

                refund_adjustment = gross_amount

                refunds.append(
                    {
                        "refund_id": f"RFND{refund_counter:04d}",
                        "payment_id": current_payment_id,
                        "invoice_id": invoice_id,
                        "amount": refund_adjustment,
                        "refund_date": (
                            payment_date + timedelta(days=2)
                        ).isoformat(),
                        "refund_status": "PROCESSED",
                    }
                )

                refund_counter += 1

            # ------------------------------------------------
            # Partial refund
            # ------------------------------------------------

            if (
                scenario == "PARTIAL_REFUND"
                and payment_index == 0
            ):

                refund_adjustment = money(
                    gross_amount
                    * random.choice(
                        [0.20, 0.25, 0.30, 0.40]
                    )
                )

                refunds.append(
                    {
                        "refund_id": f"RFND{refund_counter:04d}",
                        "payment_id": current_payment_id,
                        "invoice_id": invoice_id,
                        "amount": refund_adjustment,
                        "refund_date": (
                            payment_date + timedelta(days=2)
                        ).isoformat(),
                        "refund_status": "PROCESSED",
                    }
                )

                refund_counter += 1

            # ------------------------------------------------
            # Chargeback
            # ------------------------------------------------

            if (
                scenario == "CHARGEBACK"
                and payment_index == 0
            ):

                chargeback_adjustment = gross_amount

                chargebacks.append(
                    {
                        "chargeback_id": f"CB{chargeback_counter:04d}",
                        "payment_id": current_payment_id,
                        "amount": chargeback_adjustment,
                        "chargeback_date": (
                            payment_date + timedelta(days=5)
                        ).isoformat(),
                        "status": "ACCEPTED",
                        "reason": random.choice(
                            [
                                "CUSTOMER_DISPUTE",
                                "CARD_NOT_PRESENT_DISPUTE",
                                "SERVICE_NOT_RECEIVED",
                            ]
                        ),
                    }
                )

                chargeback_counter += 1

            # =================================================
            # EXPECTED SETTLEMENT
            # =================================================

            expected_net = (
                gross_amount
                - gateway_fee
                - gst_on_fee
                - refund_adjustment
                - chargeback_adjustment
                + other_adjustment
            )

            expected_net = max(0, expected_net)

            settlement_id = f"SET{settlement_counter:04d}"
            settlement_counter += 1

            settlement_ids.append(settlement_id)

            settlement_payment_id = current_payment_id
            settlement_reference = f"STL-{current_payment_id}"

            if scenario == "FUZZY_REFERENCE":

                settlement_payment_id = ""

                settlement_reference = (
                    f"{noisy_name(customer['customer_name'])}"
                    f"-{gross_amount}-"
                    f"{payment_date.strftime('%d%m%y')}"
                )

            settlement_date = (
                payment_date
                + timedelta(days=2)
            )

            settlements.append(
                {
                    "settlement_id": settlement_id,
                    "payment_id": settlement_payment_id,
                    "gross_amount": gross_amount,
                    "gateway_fee": gateway_fee,
                    "gst_on_fee": gst_on_fee,
                    "refund_adjustment": refund_adjustment,
                    "chargeback_adjustment": chargeback_adjustment,
                    "other_adjustment": other_adjustment,
                    "expected_net": expected_net,
                    "settlement_date": settlement_date.isoformat(),
                    "reference": settlement_reference,
                }
            )

            # =================================================
            # ACTUAL BANK CREDIT
            # =================================================

            actual_bank_amount = expected_net

            # Truly unexplained financial discrepancy.
            if scenario == "UNRESOLVED":

                actual_bank_amount = max(
                    0,
                    expected_net
                    - random.choice(
                        [3000, 5000, 8000, 12000]
                    )
                )

            # Missing-bank-entry case.
            if scenario == "MISSING_BANK_ENTRY":

                total_true_net += expected_net
                continue

            bank_txn_id = f"BNK{bank_counter:04d}"
            bank_counter += 1

            bank_ids.append(bank_txn_id)

            bank_date = settlement_date

            if scenario == "SETTLEMENT_DELAY":

                bank_date = (
                    settlement_date
                    + timedelta(days=random.randint(4, 8))
                )

            bank_settlement_id = settlement_id
            bank_reference = f"BANK-{settlement_id}"

            if scenario == "FUZZY_REFERENCE":

                bank_settlement_id = ""

                bank_reference = (
                    f"{noisy_name(customer['customer_name'])} "
                    f"SETTLEMENT {gross_amount}"
                )

            bank_transactions.append(
                {
                    "bank_txn_id": bank_txn_id,
                    "settlement_id": bank_settlement_id,
                    "reference": bank_reference,
                    "amount": actual_bank_amount,
                    "transaction_date": bank_date.isoformat(),
                    "description": (
                        "Settlement credit - "
                        f"{noisy_name(customer['customer_name'])}"
                    ),
                }
            )

            total_true_net += expected_net

        # ====================================================
        # EVALUATION TRUTH
        # ====================================================

        truth["expected_payment_ids"] = "|".join(payment_ids)
        truth["expected_settlement_ids"] = "|".join(settlement_ids)
        truth["expected_bank_txn_ids"] = "|".join(bank_ids)
        truth["true_net_settlement"] = total_true_net
        truth["true_payment_delay_days"] = delay_days

        if scenario in {
            "CLEAN",
            "GATEWAY_FEE_GST",
            "FUZZY_REFERENCE",
        }:

            truth["true_status"] = "RECONCILED"

        elif scenario in {
            "FULL_REFUND",
            "PARTIAL_REFUND",
            "CHARGEBACK",
            "PARTIAL_PAYMENT",
            "SETTLEMENT_DELAY",
            "DUPLICATE_PAYMENT",
        }:

            truth["true_status"] = "EXPLAINED_EXCEPTION"

        else:

            truth["true_status"] = "UNRESOLVED"
            truth["should_auto_resolve"] = False

        ground_truth.append(truth)

    # ========================================================
    # EXPENSES FOR FUTURE CASH FORECASTING
    # ========================================================

    categories = [
        "SALARY",
        "GST",
        "RENT",
        "CLOUD",
        "VENDOR",
        "SOFTWARE",
        "LOGISTICS",
    ]

    for i in range(1, 41):

        expense_due = (
            date(2026, 8, 21)
            + timedelta(days=random.randint(0, 60))
        )

        expenses.append(
            {
                "expense_id": f"EXP{i:03d}",
                "category": random.choice(categories),
                "vendor": f"Vendor {i:02d}",
                "amount": random.randrange(
                    10_000,
                    300_001,
                    1000,
                ),
                "due_date": expense_due.isoformat(),
                "priority": random.choice(
                    [
                        "CRITICAL",
                        "HIGH",
                        "MEDIUM",
                        "LOW",
                    ]
                ),
                "status": "SCHEDULED",
            }
        )

    # ========================================================
    # RAW OPERATIONAL DATA
    # ========================================================

    raw_datasets = {
        "customers.csv": customers,
        "invoices.csv": pd.DataFrame(invoices),
        "payments.csv": pd.DataFrame(payments),
        "settlements.csv": pd.DataFrame(settlements),
        "bank_transactions.csv": pd.DataFrame(bank_transactions),
        "refunds.csv": pd.DataFrame(refunds),
        "chargebacks.csv": pd.DataFrame(chargebacks),
        "expenses.csv": pd.DataFrame(expenses),
    }

    for filename, dataframe in raw_datasets.items():

        dataframe.to_csv(
            RAW_DIR / filename,
            index=False,
        )

    # ========================================================
    # EVALUATION-ONLY DATA
    # ========================================================

    truth_df = pd.DataFrame(ground_truth)

    truth_df.to_csv(
        EVALUATION_DIR / "ground_truth.csv",
        index=False,
    )

    # ========================================================
    # TERMINAL REPORT
    # ========================================================

    print()
    print("========================================")
    print(" FLOWGUARD REVIEWER-SAFE DATASET")
    print("========================================")
    print()

    print("RAW OPERATIONAL DATA")
    print()

    for filename, dataframe in raw_datasets.items():

        print(
            f"{filename:<24}"
            f"{len(dataframe):>4} rows"
        )

    print()
    print("EVALUATION-ONLY DATA")
    print()

    print(
        f"{'ground_truth.csv':<24}"
        f"{len(truth_df):>4} rows"
    )

    print()
    print("Scenario distribution:")
    print()

    print(
        truth_df["scenario"]
        .value_counts()
        .sort_index()
        .to_string()
    )

    print()
    print(f"Raw directory:        {RAW_DIR}")
    print(f"Evaluation directory: {EVALUATION_DIR}")

    print()
    print(
        "IMPORTANT: No benchmark case IDs or "
        "scenario labels were written to raw data."
    )
    print()


if __name__ == "__main__":
    generate()