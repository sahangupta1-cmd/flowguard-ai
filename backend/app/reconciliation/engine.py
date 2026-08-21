from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd

from .exact_matcher import (
    canonical_exact_identifier,
    require_columns,
)
from .models import (
    MatchMethod,
    ReconciliationResult,
    ReconciliationStatus,
    RootCause,
)
from .normalizers import to_decimal
from .root_cause import RootCauseAnalyzer
from .settlement_matcher import (
    ReconciliationChain,
    ReconciliationLinker,
)


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_RAW_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
)

DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "output"
)


# ============================================================
# DEFENSE-IN-DEPTH
# ============================================================

FORBIDDEN_OPERATIONAL_COLUMNS = {
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
# BATCH RESULT
# ============================================================


@dataclass(slots=True)
class BatchRunResult:
    """
    Complete operational result for one reconciliation run.
    """

    results: list[ReconciliationResult]

    summary: dict[str, Any]


# ============================================================
# RECONCILIATION ENGINE
# ============================================================


class ReconciliationEngine:
    """
    FlowGuard production reconciliation runner.

    Responsibilities:
        1. Load operational finance data.
        2. Reject benchmark-label leakage.
        3. Link invoice -> payment -> settlement -> bank.
        4. Investigate financial root cause.
        5. Produce auditable results.
        6. Measure operational throughput and coverage.

    IMPORTANT:
    This module NEVER reads data/evaluation/ground_truth.csv.

    Benchmark accuracy belongs exclusively to the evaluation
    layer and will be calculated separately.
    """

    def __init__(
        self,
        *,
        raw_dir: Path = DEFAULT_RAW_DIR,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
    ) -> None:

        self.raw_dir = Path(
            raw_dir
        )

        self.output_dir = Path(
            output_dir
        )

    # ========================================================
    # DATA LOADING
    # ========================================================

    def _read_csv(
        self,
        filename: str,
    ) -> pd.DataFrame:

        path = (
            self.raw_dir
            / filename
        )

        if not path.exists():

            raise FileNotFoundError(
                f"Required operational file not found: "
                f"{path}"
            )

        return pd.read_csv(
            path
        )

    def _assert_no_benchmark_columns(
        self,
        dataset_name: str,
        dataframe: pd.DataFrame,
    ) -> None:
        """
        Defense-in-depth against accidental benchmark leakage.

        Even if someone later modifies the generator, the
        reconciliation engine refuses to run if evaluation
        labels appear in operational data.
        """

        leaked = (
            set(dataframe.columns)
            & FORBIDDEN_OPERATIONAL_COLUMNS
        )

        if leaked:

            raise ValueError(
                f"{dataset_name} contains forbidden "
                f"benchmark/evaluation column(s): "
                + ", ".join(
                    sorted(leaked)
                )
            )

    def load_operational_data(
        self,
    ) -> dict[str, pd.DataFrame]:
        """
        Load ONLY production-style operational datasets.
        """

        data = {
            "invoices":
                self._read_csv(
                    "invoices.csv"
                ),

            "payments":
                self._read_csv(
                    "payments.csv"
                ),

            "settlements":
                self._read_csv(
                    "settlements.csv"
                ),

            "bank_transactions":
                self._read_csv(
                    "bank_transactions.csv"
                ),

            "refunds":
                self._read_csv(
                    "refunds.csv"
                ),

            "chargebacks":
                self._read_csv(
                    "chargebacks.csv"
                ),
        }

        for name, dataframe in data.items():

            self._assert_no_benchmark_columns(
                name,
                dataframe,
            )

        self._validate_invoice_schema(
            data["invoices"]
        )

        return data

    # ========================================================
    # INPUT VALIDATION
    # ========================================================

    @staticmethod
    def _validate_invoice_schema(
        invoices: pd.DataFrame,
    ) -> None:

        require_columns(
            invoices,
            {
                "invoice_id",
                "customer_id",
                "customer_name",
                "invoice_amount",
                "issue_date",
                "due_date",
                "payment_policy",
            },
            dataset_name="invoices",
        )

        normalized_ids = (
            invoices["invoice_id"]
            .apply(
                canonical_exact_identifier
            )
        )

        if (
            normalized_ids
            == ""
        ).any():

            raise ValueError(
                "Invoices contain blank invoice IDs."
            )

        if normalized_ids.duplicated().any():

            duplicates = (
                normalized_ids[
                    normalized_ids.duplicated(
                        keep=False
                    )
                ]
                .unique()
                .tolist()
            )

            raise ValueError(
                "Duplicate invoice IDs detected: "
                + ", ".join(
                    sorted(duplicates)
                )
            )

    # ========================================================
    # MONEY HELPERS
    # ========================================================

    @staticmethod
    def _sum_money(
        records: pd.DataFrame,
        column: str,
    ) -> Decimal:

        total = Decimal(
            "0.00"
        )

        if records.empty:
            return total

        if column not in records.columns:

            raise ValueError(
                f"Missing financial column: {column}"
            )

        for value in records[column]:

            total += to_decimal(
                value
            )

        return total.quantize(
            Decimal("0.01")
        )

    # ========================================================
    # MATCH SUMMARY
    # ========================================================

    @staticmethod
    def _overall_match_method(
        chain: ReconciliationChain,
    ) -> MatchMethod:
        """
        Describe the weakest/most complex accepted linkage
        used in a reconciliation chain.
        """

        accepted_methods = [
            item.get("method")
            for item in chain.trace
            if item.get("accepted") is True
        ]

        if (
            MatchMethod.FUZZY.value
            in accepted_methods
        ):

            return MatchMethod.FUZZY

        if (
            MatchMethod.EXACT_ID.value
            in accepted_methods
        ):

            return MatchMethod.EXACT_ID

        return MatchMethod.NONE

    # ========================================================
    # RESULT CREATION
    # ========================================================

    def _build_result(
        self,
        invoice: pd.Series,
        chain: ReconciliationChain,
        decision,
    ) -> ReconciliationResult:

        invoice_amount = to_decimal(
            invoice["invoice_amount"]
        )

        payment_total = (
            self._sum_money(
                chain.payments,
                "amount",
            )
        )

        expected_settlement = (
            self._sum_money(
                chain.settlements,
                "expected_net",
            )
        )

        actual_bank_amount = (
            self._sum_money(
                chain.bank_transactions,
                "amount",
            )
        )

        difference = (
            expected_settlement
            - actual_bank_amount
        ).quantize(
            Decimal("0.01")
        )

        payment_ids = (
            self._extract_ids(
                chain.payments,
                "payment_id",
            )
        )

        settlement_ids = (
            self._extract_ids(
                chain.settlements,
                "settlement_id",
            )
        )

        bank_ids = (
            self._extract_ids(
                chain.bank_transactions,
                "bank_txn_id",
            )
        )

        return ReconciliationResult(
            invoice_id=(
                canonical_exact_identifier(
                    invoice["invoice_id"]
                )
            ),

            customer_id=(
                canonical_exact_identifier(
                    invoice["customer_id"]
                )
            ),

            customer_name=str(
                invoice["customer_name"]
            ),

            invoice_amount=
                invoice_amount,

            payment_ids=
                payment_ids,

            settlement_ids=
                settlement_ids,

            bank_transaction_ids=
                bank_ids,

            payment_amount=
                payment_total,

            expected_settlement=
                expected_settlement,

            actual_bank_amount=
                actual_bank_amount,

            difference=
                difference,

            status=
                decision.status,

            root_cause=
                decision.root_cause,

            confidence=
                decision.confidence,

            match_method=
                self._overall_match_method(
                    chain
                ),

            requires_review=(
                decision.requires_review
                or chain.requires_review
            ),

            explanation=
                decision.explanation,

            recommended_action=
                decision.recommended_action,

            evidence={
                "root_cause":
                    decision.evidence,

                "match_trace":
                    chain.trace,

                "chain_issues":
                    list(
                        chain.issues
                    ),
            },
        )

    @staticmethod
    def _extract_ids(
        records: pd.DataFrame,
        id_column: str,
    ) -> list[str]:

        if records.empty:
            return []

        if id_column not in records.columns:

            raise ValueError(
                f"Missing ID column: "
                f"{id_column}"
            )

        ids: list[str] = []

        for value in records[
            id_column
        ]:

            identifier = (
                canonical_exact_identifier(
                    value
                )
            )

            if identifier:
                ids.append(
                    identifier
                )

        return ids

    # ========================================================
    # SERIALIZATION
    # ========================================================

    @staticmethod
    def _result_to_csv_row(
        result: ReconciliationResult,
    ) -> dict[str, Any]:
        """
        Flatten structured output into a stable CSV format.
        """

        row = result.to_dict()

        row["payment_ids"] = "|".join(
            result.payment_ids
        )

        row["settlement_ids"] = "|".join(
            result.settlement_ids
        )

        row[
            "bank_transaction_ids"
        ] = "|".join(
            result.bank_transaction_ids
        )

        row["evidence"] = json.dumps(
            result.evidence,
            sort_keys=True,
            default=str,
        )

        return row

    # ========================================================
    # METRICS
    # ========================================================

    @staticmethod
    def _percentage(
        numerator: int,
        denominator: int,
    ) -> float:

        if denominator == 0:
            return 0.0

        return round(
            (
                numerator
                / denominator
            )
            * 100,
            2,
        )

    def _build_summary(
        self,
        results: list[
            ReconciliationResult
        ],
        *,
        elapsed_seconds: float,
    ) -> dict[str, Any]:

        total = len(
            results
        )

        status_counts = Counter(
            result.status.value
            for result in results
        )

        root_cause_counts = Counter(
            result.root_cause.value
            for result in results
        )

        review_count = sum(
            result.requires_review
            for result in results
        )

        auto_closed = sum(
            (
                not result.requires_review
                and result.status
                in {
                    ReconciliationStatus.RECONCILED,
                    ReconciliationStatus.EXPLAINED_EXCEPTION,
                }
            )
            for result in results
        )

        complete_chain_count = sum(
            bool(result.payment_ids)
            and bool(
                result.settlement_ids
            )
            and bool(
                result.bank_transaction_ids
            )
            for result in results
        )

        fuzzy_case_count = sum(
            result.match_method
            == MatchMethod.FUZZY
            for result in results
        )

        exact_case_count = sum(
            result.match_method
            == MatchMethod.EXACT_ID
            for result in results
        )

        unresolved_count = (
            status_counts[
                ReconciliationStatus.UNRESOLVED.value
            ]
            + status_counts[
                ReconciliationStatus.HUMAN_REVIEW.value
            ]
        )

        throughput = (
            total / elapsed_seconds
            if elapsed_seconds > 0
            else 0.0
        )

        return {
            "cases_processed":
                total,

            "processing_seconds":
                round(
                    elapsed_seconds,
                    6,
                ),

            "throughput_cases_per_second":
                round(
                    throughput,
                    2,
                ),

            "complete_chain_count":
                complete_chain_count,

            "complete_chain_rate_pct":
                self._percentage(
                    complete_chain_count,
                    total,
                ),

            "auto_closed_count":
                auto_closed,

            "auto_closure_rate_pct":
                self._percentage(
                    auto_closed,
                    total,
                ),

            "requires_review_count":
                review_count,

            "requires_review_rate_pct":
                self._percentage(
                    review_count,
                    total,
                ),

            "unresolved_or_review_count":
                unresolved_count,

            "exact_match_cases":
                exact_case_count,

            "fuzzy_recovery_cases":
                fuzzy_case_count,

            "status_distribution":
                dict(
                    sorted(
                        status_counts.items()
                    )
                ),

            "root_cause_distribution":
                dict(
                    sorted(
                        root_cause_counts.items()
                    )
                ),

            "accuracy_note": (
                "No benchmark accuracy is calculated by "
                "the operational engine. Accuracy is "
                "measured separately by the isolated "
                "evaluation layer."
            ),
        }

    # ========================================================
    # OUTPUT
    # ========================================================

    def _write_outputs(
        self,
        run: BatchRunResult,
    ) -> None:

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        results_path = (
            self.output_dir
            / "reconciliation_results.csv"
        )

        summary_path = (
            self.output_dir
            / "run_summary.json"
        )

        rows = [
            self._result_to_csv_row(
                result
            )
            for result in run.results
        ]

        pd.DataFrame(
            rows
        ).to_csv(
            results_path,
            index=False,
        )

        summary_path.write_text(
            json.dumps(
                run.summary,
                indent=2,
                sort_keys=True,
                default=str,
            )
            + "\n",
            encoding="utf-8",
        )

    # ========================================================
    # PUBLIC BATCH RUN
    # ========================================================

    def run(
        self,
        *,
        write_outputs: bool = True,
    ) -> BatchRunResult:
        """
        Execute the complete operational reconciliation batch.
        """

        started = perf_counter()

        data = (
            self.load_operational_data()
        )

        invoices = data[
            "invoices"
        ]

        linker = ReconciliationLinker(
            payments=
                data["payments"],

            settlements=
                data["settlements"],

            bank_transactions=
                data[
                    "bank_transactions"
                ],
        )

        analyzer = RootCauseAnalyzer(
            refunds=
                data["refunds"],

            chargebacks=
                data["chargebacks"],
        )

        chains = linker.resolve_batch(
            invoices
        )

        invoice_lookup = {
            canonical_exact_identifier(
                row["invoice_id"]
            ): row

            for _, row
            in invoices.iterrows()
        }

        results: list[
            ReconciliationResult
        ] = []

        for chain in chains:

            invoice = invoice_lookup.get(
                chain.invoice_id
            )

            if invoice is None:

                raise RuntimeError(
                    f"Internal reconciliation error: "
                    f"invoice {chain.invoice_id} "
                    f"cannot be resolved."
                )

            decision = analyzer.analyze(
                invoice,
                chain,
            )

            result = self._build_result(
                invoice,
                chain,
                decision,
            )

            results.append(
                result
            )

        elapsed = (
            perf_counter()
            - started
        )

        summary = self._build_summary(
            results,
            elapsed_seconds=elapsed,
        )

        run = BatchRunResult(
            results=results,
            summary=summary,
        )

        if write_outputs:

            self._write_outputs(
                run
            )

        return run


# ============================================================
# TERMINAL REPORT
# ============================================================


def print_summary(
    summary: dict[str, Any],
) -> None:

    print()
    print(
        "=============================================="
    )
    print(
        " FLOWGUARD RECONCILIATION BATCH"
    )
    print(
        "=============================================="
    )
    print()

    print(
        f"Cases processed:          "
        f"{summary['cases_processed']}"
    )

    print(
        f"Processing time:          "
        f"{summary['processing_seconds']:.6f}s"
    )

    print(
        f"Throughput:               "
        f"{summary['throughput_cases_per_second']} "
        f"cases/sec"
    )

    print(
        f"Complete chains:          "
        f"{summary['complete_chain_count']} "
        f"({summary['complete_chain_rate_pct']}%)"
    )

    print(
        f"Auto-closed:              "
        f"{summary['auto_closed_count']} "
        f"({summary['auto_closure_rate_pct']}%)"
    )

    print(
        f"Requires review:          "
        f"{summary['requires_review_count']} "
        f"({summary['requires_review_rate_pct']}%)"
    )

    print(
        f"Exact-match cases:        "
        f"{summary['exact_match_cases']}"
    )

    print(
        f"Fuzzy-recovery cases:     "
        f"{summary['fuzzy_recovery_cases']}"
    )

    print()
    print("--- STATUS DISTRIBUTION ---")
    print()

    for status, count in (
        summary[
            "status_distribution"
        ].items()
    ):

        print(
            f"{status:<24}{count:>4}"
        )

    print()
    print("--- ROOT CAUSES ---")
    print()

    for cause, count in (
        summary[
            "root_cause_distribution"
        ].items()
    ):

        print(
            f"{cause:<24}{count:>4}"
        )

    print()
    print(
        "NOTE: Accuracy is intentionally NOT calculated "
        "inside the operational engine."
    )
    print(
        "Ground-truth evaluation is isolated and runs "
        "separately."
    )

    print()
    print(
        "=============================================="
    )


# ============================================================
# CLI ENTRY POINT
# ============================================================


def main() -> None:

    engine = ReconciliationEngine()

    run = engine.run(
        write_outputs=True
    )

    print_summary(
        run.summary
    )

    print()
    print(
        "Results saved to:"
    )
    print(
        DEFAULT_OUTPUT_DIR
        / "reconciliation_results.csv"
    )

    print(
        DEFAULT_OUTPUT_DIR
        / "run_summary.json"
    )
    print()


if __name__ == "__main__":
    main()