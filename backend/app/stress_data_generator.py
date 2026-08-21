from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import random

import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_STRESS_DIR = (
    PROJECT_ROOT
    / "data"
    / "stress"
)

SEED = 2026

CASES_PER_SCENARIO = 4


STRESS_SCENARIOS = [
    "CLEAN_EXACT",
    "FUZZY_NOISY_REFERENCE",
    "AMBIGUOUS_PAYMENT",
    "WRONG_CUSTOMER_RIGHT_AMOUNT",
    "NEAR_AMOUNT_NOISE",
    "MATERIAL_AMOUNT_MISMATCH",
    "MISSING_SETTLEMENT_LINK",
    "MISSING_BANK_LINK",
    "SETTLEMENT_DELAY",
    "REFUND_EVIDENCE_MISMATCH",
    "CHARGEBACK_EVIDENCE_MISMATCH",
    "UNKNOWN_ADJUSTMENT",
    "DUPLICATE_PAYMENT",
    "INSTALLMENTS_COMPLETE",
    "PARTIAL_PAYMENT",
    "MISSING_CUSTOMER_ID_FUZZY",
]


CUSTOMERS = [
    ("SC001", "Nova Technologies Pvt Ltd"),
    ("SC002", "Alpha Retail Pvt Ltd"),
    ("SC003", "BluePeak Logistics Pvt Ltd"),
    ("SC004", "Vertex Consulting LLP"),
    ("SC005", "GreenCart Commerce Pvt Ltd"),
    ("SC006", "Orbit Systems Pvt Ltd"),
    ("SC007", "Horizon Foods LLP"),
    ("SC008", "Nimbus Digital Pvt Ltd"),
]


# ============================================================
# MONEY HELPERS
# ============================================================


def decimal_money(
    value,
) -> Decimal:

    return Decimal(
        str(value)
    ).quantize(
        Decimal("0.01")
    )


def csv_money(
    value,
) -> str:

    return format(
        decimal_money(value),
        ".2f",
    )


# ============================================================
# GENERATOR
# ============================================================


def generate(
    base_dir: Path = DEFAULT_STRESS_DIR,
) -> None:

    random.seed(
        SEED
    )

    base_dir = Path(
        base_dir
    )

    raw_dir = (
        base_dir
        / "raw"
    )

    evaluation_dir = (
        base_dir
        / "evaluation"
    )

    output_dir = (
        base_dir
        / "output"
    )

    raw_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    evaluation_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    customers = []
    invoices = []
    payments = []
    settlements = []
    bank_transactions = []
    refunds = []
    chargebacks = []
    expenses = []
    ground_truth = []

    # ========================================================
    # CUSTOMER DATA
    # ========================================================

    for index, (
        customer_id,
        customer_name,
    ) in enumerate(
        CUSTOMERS,
        start=1,
    ):

        customers.append(
            {
                "customer_id":
                    customer_id,

                "customer_name":
                    customer_name,

                "segment":
                    (
                        "ENTERPRISE"
                        if index % 2 == 0
                        else "SME"
                    ),

                "risk_tier":
                    (
                        "LOW"
                        if index % 3
                        else "MEDIUM"
                    ),

                "payment_terms_days":
                    15 + (
                        index % 3
                    ) * 15,

                "average_payment_delay_days":
                    index % 6,
            }
        )

    # ========================================================
    # SCENARIO LIST
    # ========================================================

    scenarios = []

    for scenario in STRESS_SCENARIOS:

        scenarios.extend(
            [scenario]
            * CASES_PER_SCENARIO
        )

    # Keep generation deterministic while preventing visible
    # scenario blocks from lining up with sequential IDs.
    random.shuffle(
        scenarios
    )

    # ========================================================
    # RECORD HELPERS
    # ========================================================

    def add_payment(
        *,
        idx: int,
        suffix: str,
        invoice_id: str,
        customer_id: str,
        amount: Decimal,
        payment_date: date,
        reference: str,
    ) -> str:

        payment_id = (
            f"SPAY{idx:03d}{suffix}"
        )

        payments.append(
            {
                "payment_id":
                    payment_id,

                "invoice_id":
                    invoice_id,

                "customer_id":
                    customer_id,

                "amount":
                    csv_money(amount),

                "payment_date":
                    payment_date.isoformat(),

                "payment_method":
                    (
                        "UPI"
                        if idx % 2
                        else "CARD"
                    ),

                "payment_status":
                    "SUCCESS",

                "reference":
                    reference,
            }
        )

        return payment_id

    def add_settlement(
        *,
        idx: int,
        suffix: str,
        payment_id: str,
        gross_amount: Decimal,
        settlement_date: date,
        reference: str,
        gateway_fee: Decimal = Decimal("0"),
        gst_on_fee: Decimal = Decimal("0"),
        refund_adjustment: Decimal = Decimal("0"),
        chargeback_adjustment: Decimal = Decimal("0"),
        other_adjustment: Decimal = Decimal("0"),
    ) -> tuple[str, Decimal]:

        settlement_id = (
            f"SSET{idx:03d}{suffix}"
        )

        expected_net = (
            decimal_money(
                gross_amount
            )
            - decimal_money(
                gateway_fee
            )
            - decimal_money(
                gst_on_fee
            )
            - decimal_money(
                refund_adjustment
            )
            - decimal_money(
                chargeback_adjustment
            )
            + decimal_money(
                other_adjustment
            )
        )

        settlements.append(
            {
                "settlement_id":
                    settlement_id,

                "payment_id":
                    payment_id,

                "gross_amount":
                    csv_money(
                        gross_amount
                    ),

                "gateway_fee":
                    csv_money(
                        gateway_fee
                    ),

                "gst_on_fee":
                    csv_money(
                        gst_on_fee
                    ),

                "refund_adjustment":
                    csv_money(
                        refund_adjustment
                    ),

                "chargeback_adjustment":
                    csv_money(
                        chargeback_adjustment
                    ),

                "other_adjustment":
                    csv_money(
                        other_adjustment
                    ),

                "expected_net":
                    csv_money(
                        expected_net
                    ),

                "settlement_date":
                    settlement_date.isoformat(),

                "reference":
                    reference,
            }
        )

        return (
            settlement_id,
            expected_net,
        )

    def add_bank(
        *,
        idx: int,
        suffix: str,
        settlement_id: str,
        amount: Decimal,
        transaction_date: date,
        reference: str,
        description: str,
    ) -> str:

        bank_id = (
            f"SBNK{idx:03d}{suffix}"
        )

        bank_transactions.append(
            {
                "bank_txn_id":
                    bank_id,

                "settlement_id":
                    settlement_id,

                "reference":
                    reference,

                "amount":
                    csv_money(
                        amount
                    ),

                "transaction_date":
                    transaction_date.isoformat(),

                "description":
                    description,
            }
        )

        return bank_id

    def add_chain(
        *,
        idx: int,
        suffix: str,
        raw_invoice_link: str,
        raw_customer_id: str,
        customer_name: str,
        amount: Decimal,
        payment_date: date,
        settlement_date: date,
        bank_date: date | None = None,
        raw_payment_link: str | None = None,
        raw_settlement_link: str | None = None,
        payment_reference: str | None = None,
        settlement_reference: str | None = None,
        bank_reference: str | None = None,
        bank_description: str | None = None,
        refund_adjustment: Decimal = Decimal("0"),
        chargeback_adjustment: Decimal = Decimal("0"),
        other_adjustment: Decimal = Decimal("0"),
        bank_amount_override: Decimal | None = None,
    ) -> tuple[str, str, str]:

        payment_id = add_payment(
            idx=idx,
            suffix=suffix,
            invoice_id=raw_invoice_link,
            customer_id=raw_customer_id,
            amount=amount,
            payment_date=payment_date,
            reference=(
                payment_reference
                or (
                    f"{customer_name} "
                    f"payment"
                )
            ),
        )

        settlement_id, expected_net = (
            add_settlement(
                idx=idx,
                suffix=suffix,
                payment_id=(
                    payment_id
                    if raw_payment_link
                    is None
                    else raw_payment_link
                ),
                gross_amount=amount,
                settlement_date=
                    settlement_date,
                reference=(
                    settlement_reference
                    or (
                        f"{customer_name} "
                        f"settlement"
                    )
                ),
                refund_adjustment=
                    refund_adjustment,
                chargeback_adjustment=
                    chargeback_adjustment,
                other_adjustment=
                    other_adjustment,
            )
        )

        actual_bank_amount = (
            expected_net
            if bank_amount_override
            is None
            else decimal_money(
                bank_amount_override
            )
        )

        bank_id = add_bank(
            idx=idx,
            suffix=suffix,
            settlement_id=(
                settlement_id
                if raw_settlement_link
                is None
                else raw_settlement_link
            ),
            amount=
                actual_bank_amount,
            transaction_date=(
                bank_date
                or settlement_date
            ),
            reference=(
                bank_reference
                or (
                    f"{customer_name} "
                    f"bank credit"
                )
            ),
            description=(
                bank_description
                or (
                    f"Settlement credit "
                    f"{customer_name}"
                )
            ),
        )

        return (
            payment_id,
            settlement_id,
            bank_id,
        )

    # ========================================================
    # GENERATE 64 STRESS CASES
    # ========================================================

    for idx, scenario in enumerate(
        scenarios,
        start=1,
    ):

        (
            customer_id,
            customer_name,
        ) = CUSTOMERS[
            (idx - 1)
            % len(CUSTOMERS)
        ]

        invoice_id = (
            f"SINV{idx:03d}"
        )

        stress_id = (
            f"STRESS{idx:03d}"
        )

        issue_date = (
            date(
                2026,
                9,
                1,
            )
            + timedelta(
                days=(
                    idx % 20
                )
            )
        )

        due_date = (
            issue_date
            + timedelta(
                days=30
            )
        )

        payment_date = (
            due_date
            + timedelta(
                days=(
                    idx % 3
                )
            )
        )

        settlement_date = (
            payment_date
            + timedelta(
                days=2
            )
        )

        # Unique amount per case prevents unrelated stress
        # records from accidentally becoming candidates.
        invoice_amount = Decimal(
            50000
            + idx * 1370
        )

        if scenario in {
            "PARTIAL_PAYMENT",
            "INSTALLMENTS_COMPLETE",
        }:

            payment_policy = (
                "INSTALLMENTS_ALLOWED"
            )

        elif scenario in {
            "NEAR_AMOUNT_NOISE",
            "MATERIAL_AMOUNT_MISMATCH",
        }:

            payment_policy = (
                "FULL_ONLY"
            )

        elif idx % 5 == 0:

            # Installment permission also occurs on ordinary
            # cases to avoid another hidden-label shortcut.
            payment_policy = (
                "INSTALLMENTS_ALLOWED"
            )

        else:

            payment_policy = (
                "FULL_ONLY"
            )

        invoices.append(
            {
                "invoice_id":
                    invoice_id,

                "customer_id":
                    customer_id,

                "customer_name":
                    customer_name,

                "invoice_amount":
                    csv_money(
                        invoice_amount
                    ),

                "issue_date":
                    issue_date.isoformat(),

                "due_date":
                    due_date.isoformat(),

                "payment_policy":
                    payment_policy,

                "currency":
                    "INR",
            }
        )

        expected_payment_ids: list[str] = []
        expected_settlement_ids: list[str] = []
        expected_bank_ids: list[str] = []

        true_status = ""
        true_root_cause = ""
        should_auto_resolve = False
        expected_match_method = "NONE"

        # ----------------------------------------------------
        # 1. CLEAN EXACT
        # ----------------------------------------------------

        if scenario == "CLEAN_EXACT":

            p, s, b = add_chain(
                idx=idx,
                suffix="A",
                raw_invoice_link=
                    invoice_id,
                raw_customer_id=
                    customer_id,
                customer_name=
                    customer_name,
                amount=
                    invoice_amount,
                payment_date=
                    payment_date,
                settlement_date=
                    settlement_date,
            )

            expected_payment_ids = [p]
            expected_settlement_ids = [s]
            expected_bank_ids = [b]

            true_status = "RECONCILED"
            true_root_cause = "CLEAN"
            should_auto_resolve = True
            expected_match_method = "EXACT_ID"

        # ----------------------------------------------------
        # 2. NOISY REFERENCES — FUZZY RECOVERY
        # ----------------------------------------------------

        elif (
            scenario
            == "FUZZY_NOISY_REFERENCE"
        ):

            p, s, b = add_chain(
                idx=idx,
                suffix="A",

                # Broken native relationships force recovery.
                raw_invoice_link="",
                raw_payment_link="",
                raw_settlement_link="",

                raw_customer_id=
                    customer_id,

                customer_name=
                    customer_name,

                amount=
                    invoice_amount,

                payment_date=
                    payment_date,

                settlement_date=
                    settlement_date,

                payment_reference=(
                    f"PAYMENT {customer_name} "
                    f"{invoice_id}"
                ),

                settlement_reference=(
                    f"SETTLEMENT "
                    f"{customer_name}"
                ),

                bank_reference=(
                    f"NEFT CREDIT "
                    f"{customer_name}"
                ),

                bank_description=(
                    f"Merchant settlement "
                    f"{customer_name}"
                ),
            )

            expected_payment_ids = [p]
            expected_settlement_ids = [s]
            expected_bank_ids = [b]

            true_status = "RECONCILED"
            true_root_cause = "CLEAN"
            should_auto_resolve = True
            expected_match_method = "FUZZY"

        # ----------------------------------------------------
        # 3. AMBIGUOUS PAYMENT
        # ----------------------------------------------------

        elif scenario == "AMBIGUOUS_PAYMENT":

            common_reference = (
                f"{customer_name} PAYMENT"
            )

            add_payment(
                idx=idx,
                suffix="A",
                invoice_id="",
                customer_id=
                    customer_id,
                amount=
                    invoice_amount,
                payment_date=
                    payment_date,
                reference=
                    common_reference,
            )

            add_payment(
                idx=idx,
                suffix="B",
                invoice_id="",
                customer_id=
                    customer_id,
                amount=
                    invoice_amount,
                payment_date=
                    payment_date,
                reference=
                    common_reference,
            )

            # Correct action is not to select either.
            true_status = "HUMAN_REVIEW"
            true_root_cause = "UNEXPLAINED"
            should_auto_resolve = False
            expected_match_method = "NONE"

        # ----------------------------------------------------
        # 4. RIGHT AMOUNT, WRONG CUSTOMER
        # ----------------------------------------------------

        elif (
            scenario
            == "WRONG_CUSTOMER_RIGHT_AMOUNT"
        ):

            wrong_customer = (
                CUSTOMERS[
                    idx
                    % len(CUSTOMERS)
                ][0]
            )

            add_payment(
                idx=idx,
                suffix="A",
                invoice_id="",
                customer_id=
                    wrong_customer,
                amount=
                    invoice_amount,
                payment_date=
                    payment_date,
                reference=(
                    f"{customer_name} PAYMENT"
                ),
            )

            true_status = "UNRESOLVED"
            true_root_cause = "MISSING_PAYMENT"
            should_auto_resolve = False
            expected_match_method = "NONE"

        # ----------------------------------------------------
        # 5. NEAR AMOUNT — MATCH CANDIDATE BUT FINANCE FAILS
        # ----------------------------------------------------

        elif scenario == "NEAR_AMOUNT_NOISE":

            noisy_amount = (
                invoice_amount
                - Decimal("0.40")
            )

            p, s, b = add_chain(
                idx=idx,
                suffix="A",
                raw_invoice_link="",
                raw_customer_id=
                    customer_id,
                customer_name=
                    customer_name,
                amount=
                    noisy_amount,
                payment_date=
                    payment_date,
                settlement_date=
                    settlement_date,
                payment_reference=(
                    f"{customer_name} "
                    f"{invoice_id}"
                ),
            )

            expected_payment_ids = [p]
            expected_settlement_ids = [s]
            expected_bank_ids = [b]

            true_status = "UNRESOLVED"
            true_root_cause = "AMOUNT_MISMATCH"
            should_auto_resolve = False
            expected_match_method = "FUZZY"

        # ----------------------------------------------------
        # 6. MATERIAL AMOUNT MISMATCH
        # ----------------------------------------------------

        elif (
            scenario
            == "MATERIAL_AMOUNT_MISMATCH"
        ):

            mismatch_amount = (
                invoice_amount
                - Decimal("5000")
            )

            p, s, b = add_chain(
                idx=idx,
                suffix="A",
                raw_invoice_link=
                    invoice_id,
                raw_customer_id=
                    customer_id,
                customer_name=
                    customer_name,
                amount=
                    mismatch_amount,
                payment_date=
                    payment_date,
                settlement_date=
                    settlement_date,
            )

            expected_payment_ids = [p]
            expected_settlement_ids = [s]
            expected_bank_ids = [b]

            true_status = "UNRESOLVED"
            true_root_cause = "AMOUNT_MISMATCH"
            should_auto_resolve = False
            expected_match_method = "EXACT_ID"

        # ----------------------------------------------------
        # 7. MISSING SETTLEMENT
        # ----------------------------------------------------

        elif (
            scenario
            == "MISSING_SETTLEMENT_LINK"
        ):

            p = add_payment(
                idx=idx,
                suffix="A",
                invoice_id=
                    invoice_id,
                customer_id=
                    customer_id,
                amount=
                    invoice_amount,
                payment_date=
                    payment_date,
                reference=(
                    f"{customer_name} PAYMENT"
                ),
            )

            expected_payment_ids = [p]

            true_status = "UNRESOLVED"
            true_root_cause = "MISSING_SETTLEMENT"
            should_auto_resolve = False
            expected_match_method = "EXACT_ID"

        # ----------------------------------------------------
        # 8. MISSING BANK ENTRY
        # ----------------------------------------------------

        elif (
            scenario
            == "MISSING_BANK_LINK"
        ):

            p = add_payment(
                idx=idx,
                suffix="A",
                invoice_id=
                    invoice_id,
                customer_id=
                    customer_id,
                amount=
                    invoice_amount,
                payment_date=
                    payment_date,
                reference=(
                    f"{customer_name} PAYMENT"
                ),
            )

            s, _ = add_settlement(
                idx=idx,
                suffix="A",
                payment_id=p,
                gross_amount=
                    invoice_amount,
                settlement_date=
                    settlement_date,
                reference=(
                    f"{customer_name} SETTLEMENT"
                ),
            )

            expected_payment_ids = [p]
            expected_settlement_ids = [s]

            true_status = "UNRESOLVED"
            true_root_cause = "MISSING_BANK_ENTRY"
            should_auto_resolve = False
            expected_match_method = "EXACT_ID"

        # ----------------------------------------------------
        # 9. DELAYED BANK CREDIT
        # ----------------------------------------------------

        elif scenario == "SETTLEMENT_DELAY":

            p, s, b = add_chain(
                idx=idx,
                suffix="A",
                raw_invoice_link=
                    invoice_id,
                raw_customer_id=
                    customer_id,
                customer_name=
                    customer_name,
                amount=
                    invoice_amount,
                payment_date=
                    payment_date,
                settlement_date=
                    settlement_date,
                bank_date=(
                    settlement_date
                    + timedelta(
                        days=6
                    )
                ),
            )

            expected_payment_ids = [p]
            expected_settlement_ids = [s]
            expected_bank_ids = [b]

            true_status = "EXPLAINED_EXCEPTION"
            true_root_cause = "SETTLEMENT_DELAY"
            should_auto_resolve = True
            expected_match_method = "EXACT_ID"

        # ----------------------------------------------------
        # 10. REFUND EVIDENCE CONFLICT
        # ----------------------------------------------------

        elif (
            scenario
            == "REFUND_EVIDENCE_MISMATCH"
        ):

            refund_adjustment = Decimal(
                "20000"
            )

            p, s, b = add_chain(
                idx=idx,
                suffix="A",
                raw_invoice_link=
                    invoice_id,
                raw_customer_id=
                    customer_id,
                customer_name=
                    customer_name,
                amount=
                    invoice_amount,
                payment_date=
                    payment_date,
                settlement_date=
                    settlement_date,
                refund_adjustment=
                    refund_adjustment,
            )

            refunds.append(
                {
                    "refund_id":
                        f"SRF{idx:03d}",

                    "payment_id":
                        p,

                    "invoice_id":
                        invoice_id,

                    # Deliberately inconsistent evidence.
                    "amount":
                        csv_money(
                            Decimal(
                                "15000"
                            )
                        ),

                    "refund_date":
                        (
                            payment_date
                            + timedelta(
                                days=2
                            )
                        ).isoformat(),

                    "refund_status":
                        "PROCESSED",
                }
            )

            expected_payment_ids = [p]
            expected_settlement_ids = [s]
            expected_bank_ids = [b]

            true_status = "HUMAN_REVIEW"
            true_root_cause = "UNEXPLAINED"
            should_auto_resolve = False
            expected_match_method = "EXACT_ID"

        # ----------------------------------------------------
        # 11. CHARGEBACK EVIDENCE CONFLICT
        # ----------------------------------------------------

        elif (
            scenario
            == "CHARGEBACK_EVIDENCE_MISMATCH"
        ):

            adjustment = Decimal(
                "25000"
            )

            p, s, b = add_chain(
                idx=idx,
                suffix="A",
                raw_invoice_link=
                    invoice_id,
                raw_customer_id=
                    customer_id,
                customer_name=
                    customer_name,
                amount=
                    invoice_amount,
                payment_date=
                    payment_date,
                settlement_date=
                    settlement_date,
                chargeback_adjustment=
                    adjustment,
            )

            chargebacks.append(
                {
                    "chargeback_id":
                        f"SCB{idx:03d}",

                    "payment_id":
                        p,

                    # Deliberately different from settlement.
                    "amount":
                        csv_money(
                            Decimal(
                                "18000"
                            )
                        ),

                    "chargeback_date":
                        (
                            payment_date
                            + timedelta(
                                days=5
                            )
                        ).isoformat(),

                    "status":
                        "ACCEPTED",

                    "reason":
                        "Stress benchmark dispute",
                }
            )

            expected_payment_ids = [p]
            expected_settlement_ids = [s]
            expected_bank_ids = [b]

            true_status = "HUMAN_REVIEW"
            true_root_cause = "UNEXPLAINED"
            should_auto_resolve = False
            expected_match_method = "EXACT_ID"

        # ----------------------------------------------------
        # 12. UNKNOWN PROVIDER ADJUSTMENT
        # ----------------------------------------------------

        elif scenario == "UNKNOWN_ADJUSTMENT":

            p, s, b = add_chain(
                idx=idx,
                suffix="A",
                raw_invoice_link=
                    invoice_id,
                raw_customer_id=
                    customer_id,
                customer_name=
                    customer_name,
                amount=
                    invoice_amount,
                payment_date=
                    payment_date,
                settlement_date=
                    settlement_date,

                # Negative adjustment lowers net settlement.
                other_adjustment=
                    Decimal("-2500"),
            )

            expected_payment_ids = [p]
            expected_settlement_ids = [s]
            expected_bank_ids = [b]

            true_status = "HUMAN_REVIEW"
            true_root_cause = "UNEXPLAINED"
            should_auto_resolve = False
            expected_match_method = "EXACT_ID"

        # ----------------------------------------------------
        # 13. DUPLICATE PAYMENT
        # ----------------------------------------------------

        elif scenario == "DUPLICATE_PAYMENT":

            p1, s1, b1 = add_chain(
                idx=idx,
                suffix="A",
                raw_invoice_link=
                    invoice_id,
                raw_customer_id=
                    customer_id,
                customer_name=
                    customer_name,
                amount=
                    invoice_amount,
                payment_date=
                    payment_date,
                settlement_date=
                    settlement_date,
            )

            p2, s2, b2 = add_chain(
                idx=idx,
                suffix="B",
                raw_invoice_link=
                    invoice_id,
                raw_customer_id=
                    customer_id,
                customer_name=
                    customer_name,
                amount=
                    invoice_amount,
                payment_date=(
                    payment_date
                    + timedelta(
                        days=1
                    )
                ),
                settlement_date=(
                    settlement_date
                    + timedelta(
                        days=1
                    )
                ),
            )

            expected_payment_ids = [
                p1,
                p2,
            ]

            expected_settlement_ids = [
                s1,
                s2,
            ]

            expected_bank_ids = [
                b1,
                b2,
            ]

            true_status = "EXPLAINED_EXCEPTION"
            true_root_cause = "DUPLICATE_PAYMENT"

            # Duplicate payment is detected, but finance
            # still needs to choose refund/credit treatment.
            should_auto_resolve = False
            expected_match_method = "EXACT_ID"

        # ----------------------------------------------------
        # 14. LEGITIMATE INSTALLMENTS — FULLY PAID
        # ----------------------------------------------------

        elif (
            scenario
            == "INSTALLMENTS_COMPLETE"
        ):

            first_amount = (
                invoice_amount
                * Decimal("0.40")
            ).quantize(
                Decimal("0.01")
            )

            second_amount = (
                invoice_amount
                - first_amount
            )

            p1, s1, b1 = add_chain(
                idx=idx,
                suffix="A",
                raw_invoice_link=
                    invoice_id,
                raw_customer_id=
                    customer_id,
                customer_name=
                    customer_name,
                amount=
                    first_amount,
                payment_date=
                    payment_date,
                settlement_date=
                    settlement_date,
            )

            p2, s2, b2 = add_chain(
                idx=idx,
                suffix="B",
                raw_invoice_link=
                    invoice_id,
                raw_customer_id=
                    customer_id,
                customer_name=
                    customer_name,
                amount=
                    second_amount,
                payment_date=(
                    payment_date
                    + timedelta(
                        days=4
                    )
                ),
                settlement_date=(
                    settlement_date
                    + timedelta(
                        days=4
                    )
                ),
            )

            expected_payment_ids = [
                p1,
                p2,
            ]

            expected_settlement_ids = [
                s1,
                s2,
            ]

            expected_bank_ids = [
                b1,
                b2,
            ]

            true_status = "RECONCILED"
            true_root_cause = "CLEAN"
            should_auto_resolve = True
            expected_match_method = "EXACT_ID"

        # ----------------------------------------------------
        # 15. LEGITIMATE PARTIAL PAYMENT
        # ----------------------------------------------------

        elif scenario == "PARTIAL_PAYMENT":

            partial_amount = (
                invoice_amount
                * Decimal("0.60")
            ).quantize(
                Decimal("0.01")
            )

            p, s, b = add_chain(
                idx=idx,
                suffix="A",
                raw_invoice_link=
                    invoice_id,
                raw_customer_id=
                    customer_id,
                customer_name=
                    customer_name,
                amount=
                    partial_amount,
                payment_date=
                    payment_date,
                settlement_date=
                    settlement_date,
            )

            expected_payment_ids = [p]
            expected_settlement_ids = [s]
            expected_bank_ids = [b]

            true_status = "EXPLAINED_EXCEPTION"
            true_root_cause = "PARTIAL_PAYMENT"
            should_auto_resolve = True
            expected_match_method = "EXACT_ID"

        # ----------------------------------------------------
        # 16. MISSING CUSTOMER ID BUT STRONG FUZZY EVIDENCE
        # ----------------------------------------------------

        elif (
            scenario
            == "MISSING_CUSTOMER_ID_FUZZY"
        ):

            p, s, b = add_chain(
                idx=idx,
                suffix="A",

                raw_invoice_link="",
                raw_customer_id="",
                raw_payment_link="",
                raw_settlement_link="",

                customer_name=
                    customer_name,

                amount=
                    invoice_amount,

                payment_date=
                    payment_date,

                settlement_date=
                    settlement_date,

                payment_reference=(
                    f"{customer_name} "
                    f"{invoice_id} PAYMENT"
                ),

                settlement_reference=(
                    f"{customer_name} "
                    f"MERCHANT SETTLEMENT"
                ),

                bank_reference=(
                    f"{customer_name} "
                    f"NEFT CREDIT"
                ),

                bank_description=(
                    f"Settlement credit "
                    f"{customer_name}"
                ),
            )

            expected_payment_ids = [p]
            expected_settlement_ids = [s]
            expected_bank_ids = [b]

            true_status = "RECONCILED"
            true_root_cause = "CLEAN"
            should_auto_resolve = True
            expected_match_method = "FUZZY"

        else:

            raise RuntimeError(
                f"Unhandled stress scenario: "
                f"{scenario}"
            )

        # ====================================================
        # HIDDEN STRESS GROUND TRUTH
        # ====================================================

        ground_truth.append(
            {
                "stress_id":
                    stress_id,

                "invoice_id":
                    invoice_id,

                "scenario":
                    scenario,

                "true_status":
                    true_status,

                "true_root_cause":
                    true_root_cause,

                "expected_payment_ids":
                    "|".join(
                        expected_payment_ids
                    ),

                "expected_settlement_ids":
                    "|".join(
                        expected_settlement_ids
                    ),

                "expected_bank_txn_ids":
                    "|".join(
                        expected_bank_ids
                    ),

                "expected_match_method":
                    expected_match_method,

                "should_auto_resolve":
                    should_auto_resolve,

                "true_invoice_amount":
                    csv_money(
                        invoice_amount
                    ),
            }
        )

    # ========================================================
    # EXPENSE BACKGROUND NOISE
    # ========================================================

    for idx in range(
        1,
        25,
    ):

        expenses.append(
            {
                "expense_id":
                    f"SEXP{idx:03d}",

                "expense_date":
                    (
                        date(
                            2026,
                            9,
                            1,
                        )
                        + timedelta(
                            days=idx
                        )
                    ).isoformat(),

                "category":
                    (
                        "PAYROLL"
                        if idx % 3 == 0
                        else "OPERATIONS"
                    ),

                "amount":
                    csv_money(
                        15000
                        + idx * 750
                    ),

                "description":
                    "Stress benchmark operating expense",
            }
        )

    # ========================================================
    # WRITE DATA
    # ========================================================

    datasets = {
        "customers.csv":
            pd.DataFrame(
                customers
            ),

        "invoices.csv":
            pd.DataFrame(
                invoices
            ),

        "payments.csv":
            pd.DataFrame(
                payments
            ),

        "settlements.csv":
            pd.DataFrame(
                settlements
            ),

        "bank_transactions.csv":
            pd.DataFrame(
                bank_transactions
            ),

        "refunds.csv":
            pd.DataFrame(
                refunds,
                columns=[
                    "refund_id",
                    "payment_id",
                    "invoice_id",
                    "amount",
                    "refund_date",
                    "refund_status",
                ],
            ),

        "chargebacks.csv":
            pd.DataFrame(
                chargebacks,
                columns=[
                    "chargeback_id",
                    "payment_id",
                    "amount",
                    "chargeback_date",
                    "status",
                    "reason",
                ],
            ),

        "expenses.csv":
            pd.DataFrame(
                expenses
            ),
    }

    for filename, dataframe in (
        datasets.items()
    ):

        dataframe.to_csv(
            raw_dir
            / filename,
            index=False,
        )

    truth_dataframe = pd.DataFrame(
        ground_truth
    )

    truth_dataframe.to_csv(
        evaluation_dir
        / "ground_truth.csv",
        index=False,
    )

    # ========================================================
    # TERMINAL SUMMARY
    # ========================================================

    print()
    print(
        "=============================================="
    )
    print(
        " FLOWGUARD ADVERSARIAL STRESS BENCHMARK"
    )
    print(
        "=============================================="
    )
    print()

    print(
        "RAW OPERATIONAL DATA"
    )
    print()

    for filename, dataframe in (
        datasets.items()
    ):

        print(
            f"{filename:<26}"
            f"{len(dataframe):>4} rows"
        )

    print()
    print(
        "EVALUATION-ONLY DATA"
    )
    print()

    print(
        f"{'ground_truth.csv':<26}"
        f"{len(truth_dataframe):>4} rows"
    )

    print()
    print(
        "Stress scenario distribution:"
    )
    print()

    print(
        truth_dataframe[
            "scenario"
        ]
        .value_counts()
        .sort_index()
        .to_string()
    )

    print()
    print(
        f"Raw directory: "
        f"{raw_dir}"
    )

    print(
        f"Evaluation directory: "
        f"{evaluation_dir}"
    )

    print()
    print(
        "IMPORTANT: No stress scenario, expected result, "
        "or benchmark answer was written to raw data."
    )
    print()


if __name__ == "__main__":
    generate()