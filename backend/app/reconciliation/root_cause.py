from __future__ import annotations

from itertools import combinations
from typing import Any

import pandas as pd

from .exact_matcher import (
    canonical_exact_identifier,
    require_columns,
)
from .models import (
    ReconciliationStatus,
    RootCause,
    RootCauseDecision,
)
from .normalizers import (
    date_distance_days,
    money_equal,
    signed_date_difference_days,
    to_decimal,
)
from .settlement_matcher import (
    ReconciliationChain,
)


# ============================================================
# CONFIGURATION
# ============================================================

SETTLEMENT_DELAY_DAYS = 4


# ============================================================
# ROOT-CAUSE ANALYZER
# ============================================================


class RootCauseAnalyzer:
    """
    Deterministic financial exception investigator.

    Responsibilities:
        - verify settlement arithmetic
        - inspect refunds and chargebacks
        - detect partial/duplicate payments
        - identify missing records
        - detect settlement delays
        - identify unexplained discrepancies

    Safety rule:
    Benchmark/evaluation labels are never accessed here.
    """

    def __init__(
        self,
        *,
        refunds: pd.DataFrame,
        chargebacks: pd.DataFrame,
    ) -> None:

        self.refunds = refunds.copy()
        self.chargebacks = chargebacks.copy()

        self._validate_schemas()

    # ========================================================
    # VALIDATION
    # ========================================================

    def _validate_schemas(self) -> None:

        require_columns(
            self.refunds,
            {
                "refund_id",
                "payment_id",
                "amount",
                "refund_status",
            },
            dataset_name="refunds",
        )

        require_columns(
            self.chargebacks,
            {
                "chargeback_id",
                "payment_id",
                "amount",
                "status",
            },
            dataset_name="chargebacks",
        )

    # ========================================================
    # GENERIC HELPERS
    # ========================================================

    @staticmethod
    def _decision(
        *,
        root_cause: RootCause,
        status: ReconciliationStatus,
        confidence: float,
        explanation: str,
        recommended_action: str,
        requires_review: bool,
        evidence: dict[str, Any],
    ) -> RootCauseDecision:

        return RootCauseDecision(
            root_cause=root_cause,
            status=status,
            confidence=round(
                float(confidence),
                2,
            ),
            explanation=explanation,
            recommended_action=recommended_action,
            requires_review=requires_review,
            evidence=evidence,
        )

    @staticmethod
    def _sum_column(
        records: pd.DataFrame,
        column: str,
    ):
        """
        Sum monetary values using Decimal arithmetic.
        """

        total = to_decimal("0")

        if records.empty:
            return total

        if column not in records.columns:
            raise ValueError(
                f"Missing financial column: {column}"
            )

        for value in records[column]:
            total += to_decimal(value)

        return total.quantize(
            to_decimal("0.01")
        )

    @staticmethod
    def _payment_ids(
        chain: ReconciliationChain,
    ) -> set[str]:

        if chain.payments.empty:
            return set()

        return {
            canonical_exact_identifier(value)
            for value
            in chain.payments["payment_id"]
            if canonical_exact_identifier(value)
        }

    @staticmethod
    def _chain_confidence(
        chain: ReconciliationChain,
    ) -> float:
        """
        Return the weakest accepted match confidence.

        Financial conclusions cannot be more confident than
        the weakest confirmed relationship supporting them.
        """

        accepted_scores = [
            float(item["confidence"])
            for item in chain.trace
            if item.get("accepted") is True
        ]

        if not accepted_scores:
            return 100.0

        return min(
            accepted_scores
        )

    @staticmethod
    def _has_ambiguous_match(
        chain: ReconciliationChain,
    ) -> bool:
        """
        Detect cases where a plausible candidate existed but
        was deliberately not admitted automatically.
        """

        for item in chain.trace:

            if item.get("accepted") is True:
                continue

            target_ids = item.get(
                "target_ids",
                [],
            )

            if target_ids:
                return True

            evidence = item.get(
                "evidence",
                {},
            )

            if (
                evidence.get("confidence_band")
                == "HUMAN_REVIEW"
            ):
                return True

        for issue in chain.issues:

            if (
                "ALREADY_CONSUMED" in issue
                or "CONFLICT" in issue
            ):
                return True

        return False

    @staticmethod
    def _stage_has_missing_target(
        chain: ReconciliationChain,
        stage: str,
    ) -> bool:

        for item in chain.trace:

            if item.get("stage") != stage:
                continue

            if item.get("accepted") is True:
                continue

            if not item.get(
                "target_ids",
                [],
            ):
                return True

        return False

    # ========================================================
    # EXTERNAL EVENT EVIDENCE
    # ========================================================

    def _processed_refunds(
        self,
        payment_ids: set[str],
    ) -> pd.DataFrame:

        if not payment_ids:
            return self.refunds.iloc[
                0:0
            ].copy()

        mask = self.refunds[
            "payment_id"
        ].apply(
            lambda value:
                canonical_exact_identifier(value)
                in payment_ids
        )

        status_mask = (
            self.refunds["refund_status"]
            .astype("string")
            .fillna("")
            .str.strip()
            .str.upper()
            == "PROCESSED"
        )

        return self.refunds.loc[
            mask & status_mask
        ].copy()

    def _accepted_chargebacks(
        self,
        payment_ids: set[str],
    ) -> pd.DataFrame:

        if not payment_ids:
            return self.chargebacks.iloc[
                0:0
            ].copy()

        mask = self.chargebacks[
            "payment_id"
        ].apply(
            lambda value:
                canonical_exact_identifier(value)
                in payment_ids
        )

        status_mask = (
            self.chargebacks["status"]
            .astype("string")
            .fillna("")
            .str.strip()
            .str.upper()
            == "ACCEPTED"
        )

        return self.chargebacks.loc[
            mask & status_mask
        ].copy()

    # ========================================================
    # DUPLICATE DETECTION
    # ========================================================

    @staticmethod
    def _looks_like_duplicate_payment(
        invoice_amount,
        payments: pd.DataFrame,
    ) -> bool:
        """
        Conservative duplicate detection.

        Two payments are considered duplicate candidates only
        when both independently equal the full invoice amount
        and occur within three days of each other.

        Legitimate split installments therefore do not trigger
        this rule merely because multiple payments exist.
        """

        if len(payments) < 2:
            return False

        rows = [
            row
            for _, row
            in payments.iterrows()
        ]

        for first, second in combinations(
            rows,
            2,
        ):

            if not money_equal(
                first["amount"],
                invoice_amount,
            ):
                continue

            if not money_equal(
                second["amount"],
                invoice_amount,
            ):
                continue

            distance = date_distance_days(
                first["payment_date"],
                second["payment_date"],
            )

            if (
                distance is not None
                and distance <= 3
            ):
                return True

        return False

    # ========================================================
    # SETTLEMENT ARITHMETIC
    # ========================================================

    @staticmethod
    def _settlement_arithmetic(
        settlements: pd.DataFrame,
    ) -> tuple[
        bool,
        list[dict[str, str]],
    ]:
        """
        Independently recompute every expected settlement.

        We do NOT simply trust expected_net from the source.
        """

        required = {
            "settlement_id",
            "gross_amount",
            "gateway_fee",
            "gst_on_fee",
            "refund_adjustment",
            "chargeback_adjustment",
            "other_adjustment",
            "expected_net",
        }

        missing = (
            required
            - set(settlements.columns)
        )

        if missing:
            raise ValueError(
                "Settlements are missing required "
                "financial column(s): "
                + ", ".join(sorted(missing))
            )

        failures: list[
            dict[str, str]
        ] = []

        for _, row in settlements.iterrows():

            calculated = (
                to_decimal(
                    row["gross_amount"]
                )
                - to_decimal(
                    row["gateway_fee"]
                )
                - to_decimal(
                    row["gst_on_fee"]
                )
                - to_decimal(
                    row["refund_adjustment"]
                )
                - to_decimal(
                    row["chargeback_adjustment"]
                )
                + to_decimal(
                    row["other_adjustment"]
                )
            )

            stated = to_decimal(
                row["expected_net"]
            )

            if not money_equal(
                calculated,
                stated,
            ):

                failures.append(
                    {
                        "settlement_id":
                            str(
                                row[
                                    "settlement_id"
                                ]
                            ),

                        "calculated_expected_net":
                            str(calculated),

                        "stated_expected_net":
                            str(stated),
                    }
                )

        return (
            len(failures) == 0,
            failures,
        )

    # ========================================================
    # PUBLIC ANALYSIS
    # ========================================================

    def analyze(
        self,
        invoice: pd.Series,
        chain: ReconciliationChain,
    ) -> RootCauseDecision:
        """
        Investigate one fully/partially linked finance case.
        """

        required_invoice_fields = {
            "invoice_id",
            "invoice_amount",
            "payment_policy",
        }

        missing = (
            required_invoice_fields
            - set(invoice.index)
        )

        if missing:

            raise ValueError(
                "Invoice is missing required field(s): "
                + ", ".join(sorted(missing))
            )

        invoice_id = (
            canonical_exact_identifier(
                invoice["invoice_id"]
            )
        )

        invoice_amount = to_decimal(
            invoice["invoice_amount"]
        )

        payment_policy = (
            str(
                invoice[
                    "payment_policy"
                ]
            )
            .strip()
            .upper()
        )

        match_confidence = (
            self._chain_confidence(
                chain
            )
        )

        # ====================================================
        # 1. AMBIGUOUS LINKAGE
        # ====================================================

        if self._has_ambiguous_match(
            chain
        ):

            return self._decision(
                root_cause=
                    RootCause.UNEXPLAINED,

                status=
                    ReconciliationStatus.HUMAN_REVIEW,

                confidence=
                    match_confidence,

                explanation=(
                    "FlowGuard found competing or "
                    "conflicting financial records and "
                    "refused to force a reconciliation."
                ),

                recommended_action=(
                    "Review the competing transaction "
                    "candidates before posting or closing "
                    "this reconciliation."
                ),

                requires_review=True,

                evidence={
                    "invoice_id":
                        invoice_id,

                    "chain_issues":
                        list(
                            chain.issues
                        ),

                    "trace":
                        chain.trace,
                },
            )

        # ====================================================
        # 2. MISSING PAYMENT
        # ====================================================

        if chain.payments.empty:

            return self._decision(
                root_cause=
                    RootCause.MISSING_PAYMENT,

                status=
                    ReconciliationStatus.UNRESOLVED,

                confidence=95.0,

                explanation=(
                    "No confirmed payment could be found "
                    "for the invoice."
                ),

                recommended_action=(
                    "Verify the receivable with the "
                    "customer and inspect payment-provider "
                    "records."
                ),

                requires_review=True,

                evidence={
                    "invoice_id":
                        invoice_id,

                    "invoice_amount":
                        str(invoice_amount),
                },
            )

        # ====================================================
        # 3. MISSING SETTLEMENT
        # ====================================================

        missing_settlement_stage = (
            self._stage_has_missing_target(
                chain,
                "PAYMENT_TO_SETTLEMENT",
            )
        )

        if (
            chain.settlements.empty
            or missing_settlement_stage
        ):

            return self._decision(
                root_cause=
                    RootCause.MISSING_SETTLEMENT,

                status=
                    ReconciliationStatus.UNRESOLVED,

                confidence=
                    match_confidence,

                explanation=(
                    "A confirmed payment exists, but one "
                    "or more corresponding settlement "
                    "records could not be found."
                ),

                recommended_action=(
                    "Review the payment-provider settlement "
                    "report and confirm whether settlement "
                    "is pending."
                ),

                requires_review=True,

                evidence={
                    "payment_ids":
                        sorted(
                            self._payment_ids(
                                chain
                            )
                        ),
                },
            )

        # ====================================================
        # 4. MISSING BANK CREDIT
        # ====================================================

        missing_bank_stage = (
            self._stage_has_missing_target(
                chain,
                "SETTLEMENT_TO_BANK",
            )
        )

        if (
            chain.bank_transactions.empty
            or missing_bank_stage
        ):

            return self._decision(
                root_cause=
                    RootCause.MISSING_BANK_ENTRY,

                status=
                    ReconciliationStatus.UNRESOLVED,

                confidence=
                    match_confidence,

                explanation=(
                    "Settlement evidence exists, but one "
                    "or more expected bank credits are "
                    "missing."
                ),

                recommended_action=(
                    "Check settlement status and bank "
                    "statements; escalate to the payment "
                    "provider if the credit is overdue."
                ),

                requires_review=True,

                evidence={
                    "settlement_ids":
                        [
                            str(value)
                            for value
                            in chain.settlements[
                                "settlement_id"
                            ]
                        ],
                },
            )

        # ====================================================
        # 5. VERIFY SETTLEMENT ARITHMETIC
        # ====================================================

        arithmetic_ok, failures = (
            self._settlement_arithmetic(
                chain.settlements
            )
        )

        if not arithmetic_ok:

            return self._decision(
                root_cause=
                    RootCause.UNEXPLAINED,

                status=
                    ReconciliationStatus.HUMAN_REVIEW,

                confidence=
                    match_confidence,

                explanation=(
                    "Settlement arithmetic does not "
                    "recompute from gross amount and known "
                    "adjustments."
                ),

                recommended_action=(
                    "Do not auto-close this case. Review "
                    "the source settlement statement."
                ),

                requires_review=True,

                evidence={
                    "arithmetic_failures":
                        failures,
                },
            )

        # ====================================================
        # 6. FINANCIAL TOTALS
        # ====================================================

        payment_total = self._sum_column(
            chain.payments,
            "amount",
        )

        expected_total = self._sum_column(
            chain.settlements,
            "expected_net",
        )

        actual_bank_total = self._sum_column(
            chain.bank_transactions,
            "amount",
        )

        gateway_fee_total = (
            self._sum_column(
                chain.settlements,
                "gateway_fee",
            )
        )

        gst_total = self._sum_column(
            chain.settlements,
            "gst_on_fee",
        )

        refund_adjustment_total = (
            self._sum_column(
                chain.settlements,
                "refund_adjustment",
            )
        )

        chargeback_adjustment_total = (
            self._sum_column(
                chain.settlements,
                "chargeback_adjustment",
            )
        )

        other_adjustment_total = (
            self._sum_column(
                chain.settlements,
                "other_adjustment",
            )
        )

        payment_ids = (
            self._payment_ids(
                chain
            )
        )

        processed_refunds = (
            self._processed_refunds(
                payment_ids
            )
        )

        refund_evidence_total = (
            self._sum_column(
                processed_refunds,
                "amount",
            )
        )

        accepted_chargebacks = (
            self._accepted_chargebacks(
                payment_ids
            )
        )

        chargeback_evidence_total = (
            self._sum_column(
                accepted_chargebacks,
                "amount",
            )
        )

        base_evidence = {
            "invoice_amount":
                str(invoice_amount),

            "payment_total":
                str(payment_total),

            "expected_settlement":
                str(expected_total),

            "actual_bank_amount":
                str(actual_bank_total),

            "gateway_fee_total":
                str(gateway_fee_total),

            "gst_total":
                str(gst_total),

            "refund_adjustment_total":
                str(
                    refund_adjustment_total
                ),

            "refund_evidence_total":
                str(
                    refund_evidence_total
                ),

            "chargeback_adjustment_total":
                str(
                    chargeback_adjustment_total
                ),

            "chargeback_evidence_total":
                str(
                    chargeback_evidence_total
                ),

            "other_adjustment_total":
                str(
                    other_adjustment_total
                ),

            "match_confidence":
                match_confidence,
        }

        # ====================================================
        # 7. VERIFY REFUND EVIDENCE
        # ====================================================

        if not money_equal(
            refund_adjustment_total,
            refund_evidence_total,
        ):

            return self._decision(
                root_cause=
                    RootCause.UNEXPLAINED,

                status=
                    ReconciliationStatus.HUMAN_REVIEW,

                confidence=
                    match_confidence,

                explanation=(
                    "Settlement refund adjustments do not "
                    "agree with processed refund records."
                ),

                recommended_action=(
                    "Verify refund records before closing "
                    "the settlement."
                ),

                requires_review=True,

                evidence=
                    base_evidence,
            )

        # ====================================================
        # 8. VERIFY CHARGEBACK EVIDENCE
        # ====================================================

        if not money_equal(
            chargeback_adjustment_total,
            chargeback_evidence_total,
        ):

            return self._decision(
                root_cause=
                    RootCause.UNEXPLAINED,

                status=
                    ReconciliationStatus.HUMAN_REVIEW,

                confidence=
                    match_confidence,

                explanation=(
                    "Settlement chargeback adjustments do "
                    "not agree with accepted chargeback "
                    "records."
                ),

                recommended_action=(
                    "Review dispute and chargeback records "
                    "before closing the reconciliation."
                ),

                requires_review=True,

                evidence=
                    base_evidence,
            )

        # Unknown adjustments are never silently accepted.
        if not money_equal(
            other_adjustment_total,
            "0",
        ):

            return self._decision(
                root_cause=
                    RootCause.UNEXPLAINED,

                status=
                    ReconciliationStatus.HUMAN_REVIEW,

                confidence=
                    match_confidence,

                explanation=(
                    "The settlement contains an adjustment "
                    "that FlowGuard cannot independently "
                    "classify."
                ),

                recommended_action=(
                    "Review the provider adjustment before "
                    "auto-reconciliation."
                ),

                requires_review=True,

                evidence=
                    base_evidence,
            )

        # ====================================================
        # 9. BANK RECONCILIATION
        # ====================================================

        if not money_equal(
            expected_total,
            actual_bank_total,
        ):

            difference = (
                expected_total
                - actual_bank_total
            )

            evidence = dict(
                base_evidence
            )

            evidence[
                "unexplained_difference"
            ] = str(difference)

            return self._decision(
                root_cause=
                    RootCause.UNEXPLAINED,

                status=
                    ReconciliationStatus.UNRESOLVED,

                confidence=
                    match_confidence,

                explanation=(
                    f"₹{abs(difference):,.2f} cannot be "
                    "explained by verified fees, refunds, "
                    "chargebacks or known adjustments."
                ),

                recommended_action=(
                    "Escalate the settlement for manual "
                    "investigation."
                ),

                requires_review=True,

                evidence=evidence,
            )

        # ====================================================
        # 10. DUPLICATE PAYMENT
        # ====================================================

        if self._looks_like_duplicate_payment(
            invoice_amount,
            chain.payments,
        ):

            return self._decision(
                root_cause=
                    RootCause.DUPLICATE_PAYMENT,

                status=
                    ReconciliationStatus.EXPLAINED_EXCEPTION,

                confidence=
                    match_confidence,

                explanation=(
                    "Multiple full-value payments were "
                    "received against the same invoice "
                    "within a short time window."
                ),

                recommended_action=(
                    "Review the duplicate receipt and "
                    "determine whether a refund or customer "
                    "credit is required."
                ),

                requires_review=True,

                evidence=
                    base_evidence,
            )

        # ====================================================
        # 11. PARTIAL / INCORRECT PAYMENT
        # ====================================================

        if not money_equal(
            payment_total,
            invoice_amount,
        ):

            difference = (
                invoice_amount
                - payment_total
            )

            evidence = dict(
                base_evidence
            )

            evidence[
                "invoice_payment_difference"
            ] = str(difference)

            if (
                payment_total < invoice_amount
                and payment_policy
                == "INSTALLMENTS_ALLOWED"
            ):

                return self._decision(
                    root_cause=
                        RootCause.PARTIAL_PAYMENT,

                    status=
                        ReconciliationStatus.EXPLAINED_EXCEPTION,

                    confidence=
                        match_confidence,

                    explanation=(
                        "The invoice permits installments "
                        "and only part of the receivable has "
                        "been collected."
                    ),

                    recommended_action=(
                        "Keep the remaining balance open "
                        "and include it in receivables and "
                        "cash-flow forecasting."
                    ),

                    requires_review=False,

                    evidence=evidence,
                )

            return self._decision(
                root_cause=
                    RootCause.AMOUNT_MISMATCH,

                status=
                    ReconciliationStatus.UNRESOLVED,

                confidence=
                    match_confidence,

                explanation=(
                    "The amount collected does not agree "
                    "with the invoice terms."
                ),

                recommended_action=(
                    "Review the payment amount and invoice "
                    "terms before reconciliation."
                ),

                requires_review=True,

                evidence=evidence,
            )

        # ====================================================
        # 12. REFUNDS
        # ====================================================

        if refund_evidence_total > 0:

            if money_equal(
                refund_evidence_total,
                payment_total,
            ):

                root_cause = (
                    RootCause.FULL_REFUND
                )

                explanation = (
                    "The settlement reduction is fully "
                    "explained by a processed full refund."
                )

            elif (
                refund_evidence_total
                < payment_total
            ):

                root_cause = (
                    RootCause.PARTIAL_REFUND
                )

                explanation = (
                    "The settlement reduction is "
                    "explained by a processed partial "
                    "refund."
                )

            else:

                return self._decision(
                    root_cause=
                        RootCause.UNEXPLAINED,

                    status=
                        ReconciliationStatus.HUMAN_REVIEW,

                    confidence=
                        match_confidence,

                    explanation=(
                        "Refund evidence exceeds the "
                        "linked payment amount."
                    ),

                    recommended_action=(
                        "Review refund allocation before "
                        "closing the reconciliation."
                    ),

                    requires_review=True,

                    evidence=
                        base_evidence,
                )

            return self._decision(
                root_cause=
                    root_cause,

                status=
                    ReconciliationStatus.EXPLAINED_EXCEPTION,

                confidence=
                    match_confidence,

                explanation=
                    explanation,

                recommended_action=(
                    "No reconciliation correction is "
                    "required; retain the refund linkage "
                    "for audit."
                ),

                requires_review=False,

                evidence=
                    base_evidence,
            )

        # ====================================================
        # 13. CHARGEBACK
        # ====================================================

        if chargeback_evidence_total > 0:

            return self._decision(
                root_cause=
                    RootCause.CHARGEBACK,

                status=
                    ReconciliationStatus.EXPLAINED_EXCEPTION,

                confidence=
                    match_confidence,

                explanation=(
                    "The settlement reduction is explained "
                    "by an accepted customer chargeback."
                ),

                recommended_action=(
                    "Record the dispute impact and exclude "
                    "the charged-back amount from expected "
                    "receivables."
                ),

                requires_review=False,

                evidence=
                    base_evidence,
            )

        # ====================================================
        # 14. SETTLEMENT DELAY
        # ====================================================

        delayed_days: list[int] = []

        for _, settlement in (
            chain.settlements.iterrows()
        ):

            settlement_id = (
                canonical_exact_identifier(
                    settlement[
                        "settlement_id"
                    ]
                )
            )

            matching_bank_rows = (
                chain.bank_transactions[
                    chain.bank_transactions[
                        "settlement_id"
                    ]
                    .astype("string")
                    .fillna("")
                    .str.strip()
                    .str.upper()
                    == settlement_id
                ]
            )

            for _, bank in (
                matching_bank_rows.iterrows()
            ):

                days = (
                    signed_date_difference_days(
                        settlement[
                            "settlement_date"
                        ],
                        bank[
                            "transaction_date"
                        ],
                    )
                )

                if (
                    days is not None
                    and days
                    >= SETTLEMENT_DELAY_DAYS
                ):
                    delayed_days.append(
                        days
                    )

        if delayed_days:

            evidence = dict(
                base_evidence
            )

            evidence[
                "settlement_delay_days"
            ] = delayed_days

            return self._decision(
                root_cause=
                    RootCause.SETTLEMENT_DELAY,

                status=
                    ReconciliationStatus.EXPLAINED_EXCEPTION,

                confidence=
                    match_confidence,

                explanation=(
                    "The settlement amount reconciles, "
                    "but the corresponding bank credit "
                    "arrived later than the expected "
                    "settlement window."
                ),

                recommended_action=(
                    "Track this delay in cash-position "
                    "forecasting and monitor provider "
                    "settlement performance."
                ),

                requires_review=False,

                evidence=evidence,
            )

        # ====================================================
        # 15. GATEWAY FEE + GST
        # ====================================================

        if (
            gateway_fee_total > 0
            or gst_total > 0
        ):

            return self._decision(
                root_cause=
                    RootCause.GATEWAY_FEE_GST,

                status=
                    ReconciliationStatus.RECONCILED,

                confidence=
                    match_confidence,

                explanation=(
                    "The lower bank credit is fully "
                    "explained by recorded gateway fees "
                    "and GST."
                ),

                recommended_action=(
                    "No reconciliation action required."
                ),

                requires_review=False,

                evidence=
                    base_evidence,
            )

        # ====================================================
        # 16. CLEAN
        # ====================================================

        return self._decision(
            root_cause=
                RootCause.CLEAN,

            status=
                ReconciliationStatus.RECONCILED,

            confidence=
                match_confidence,

            explanation=(
                "Invoice, payment, settlement and bank "
                "credit reconcile without unexplained "
                "differences."
            ),

            recommended_action=(
                "No action required."
            ),

            requires_review=False,

            evidence=
                base_evidence,
        )