from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .exact_matcher import (
    canonical_exact_identifier,
    match_invoice_to_payments,
    match_payment_to_settlements,
    match_settlement_to_bank_transactions,
    require_columns,
)
from .fuzzy_matcher import (
    fuzzy_match_invoice_to_payment,
    fuzzy_match_payment_to_settlement,
    fuzzy_match_settlement_to_bank,
)
from .models import MatchMethod


# ============================================================
# RECONCILIATION CHAIN
# ============================================================


@dataclass(slots=True)
class ReconciliationChain:
    """
    Operational records connected to a single invoice.

    This object contains only operational evidence.

    It never reads or stores benchmark scenario labels or
    ground-truth answers.
    """

    invoice_id: str

    payments: pd.DataFrame = field(
        default_factory=pd.DataFrame
    )

    settlements: pd.DataFrame = field(
        default_factory=pd.DataFrame
    )

    bank_transactions: pd.DataFrame = field(
        default_factory=pd.DataFrame
    )

    trace: list[dict[str, Any]] = field(
        default_factory=list
    )

    issues: list[str] = field(
        default_factory=list
    )

    requires_review: bool = False

    def add_issue(
        self,
        issue: str,
        *,
        requires_review: bool = True,
    ) -> None:
        """
        Record a reconciliation issue without silently hiding it.
        """

        if issue not in self.issues:
            self.issues.append(issue)

        if requires_review:
            self.requires_review = True


# ============================================================
# LINKER
# ============================================================


class ReconciliationLinker:
    """
    Exact-first, fuzzy-fallback financial record linker.

    Safety guarantees:
        1. Exact identifiers are always preferred.
        2. Fuzzy records are admitted only when the
           confidence layer explicitly accepts them.
        3. Human-review candidates are never treated as
           confirmed matches.
        4. Operational records cannot be consumed twice.
        5. All matching decisions produce an evidence trace.
        6. Ground-truth/evaluation data is never accessed.
    """

    def __init__(
        self,
        *,
        payments: pd.DataFrame,
        settlements: pd.DataFrame,
        bank_transactions: pd.DataFrame,
    ) -> None:

        self.payments = payments.copy()
        self.settlements = settlements.copy()
        self.bank_transactions = (
            bank_transactions.copy()
        )

        self._validate_schemas()

        # Prevent one financial record being silently assigned
        # to multiple independent reconciliation chains.
        self.used_payment_ids: set[str] = set()
        self.used_settlement_ids: set[str] = set()
        self.used_bank_transaction_ids: set[str] = set()

    # ========================================================
    # SCHEMA VALIDATION
    # ========================================================

    def _validate_schemas(self) -> None:

        require_columns(
            self.payments,
            {
                "payment_id",
                "invoice_id",
                "customer_id",
                "amount",
                "payment_date",
                "reference",
            },
            dataset_name="payments",
        )

        require_columns(
            self.settlements,
            {
                "settlement_id",
                "payment_id",
                "gross_amount",
                "expected_net",
                "settlement_date",
                "reference",
            },
            dataset_name="settlements",
        )

        require_columns(
            self.bank_transactions,
            {
                "bank_txn_id",
                "settlement_id",
                "reference",
                "amount",
                "transaction_date",
                "description",
            },
            dataset_name="bank_transactions",
        )

    # ========================================================
    # STATE CONTROL
    # ========================================================

    def reset_usage(self) -> None:
        """
        Reset consumed-record state.

        Useful for repeatable evaluation runs.
        """

        self.used_payment_ids.clear()
        self.used_settlement_ids.clear()
        self.used_bank_transaction_ids.clear()

    # ========================================================
    # INTERNAL HELPERS
    # ========================================================

    @staticmethod
    def _record_ids(
        records: pd.DataFrame,
        id_field: str,
    ) -> list[str]:

        if records.empty:
            return []

        result: list[str] = []

        for value in records[id_field]:

            record_id = canonical_exact_identifier(
                value
            )

            if record_id:
                result.append(record_id)

        return result

    @staticmethod
    def _empty_like(
        dataframe: pd.DataFrame,
    ) -> pd.DataFrame:

        return dataframe.iloc[0:0].copy()

    def _available_records(
        self,
        dataframe: pd.DataFrame,
        *,
        id_field: str,
        used_ids: set[str],
    ) -> pd.DataFrame:
        """
        Return records not already consumed by another chain.
        """

        if dataframe.empty:
            return dataframe.copy()

        mask = dataframe[id_field].apply(
            lambda value: (
                canonical_exact_identifier(value)
                not in used_ids
            )
        )

        return dataframe.loc[
            mask
        ].copy()

    def _filter_exact_for_reuse(
        self,
        records: pd.DataFrame,
        *,
        id_field: str,
        used_ids: set[str],
        chain: ReconciliationChain,
        conflict_code: str,
    ) -> pd.DataFrame:
        """
        Exact IDs are authoritative, but reuse across unrelated
        chains is a data-integrity conflict and must be exposed.
        """

        if records.empty:
            return records.copy()

        accepted_indexes: list[Any] = []

        for index, row in records.iterrows():

            record_id = (
                canonical_exact_identifier(
                    row[id_field]
                )
            )

            if not record_id:

                chain.add_issue(
                    f"{conflict_code}:BLANK_NATIVE_ID"
                )

                continue

            if record_id in used_ids:

                chain.add_issue(
                    f"{conflict_code}:{record_id}"
                )

                continue

            accepted_indexes.append(index)

        return records.loc[
            accepted_indexes
        ].copy()

    @staticmethod
    def _append_trace(
        chain: ReconciliationChain,
        *,
        stage: str,
        source_id: str,
        target_ids: list[str],
        method: MatchMethod,
        confidence: float,
        accepted: bool,
        requires_review: bool,
        evidence: dict[str, Any] | None = None,
    ) -> None:

        chain.trace.append(
            {
                "stage": stage,
                "source_id": source_id,
                "target_ids": target_ids,
                "method": method.value,
                "confidence": round(
                    float(confidence),
                    2,
                ),
                "accepted": accepted,
                "requires_review": requires_review,
                "evidence": evidence or {},
            }
        )

    # ========================================================
    # INVOICE -> PAYMENT
    # ========================================================

    def _resolve_payments(
        self,
        invoice: pd.Series,
        chain: ReconciliationChain,
    ) -> pd.DataFrame:

        invoice_id = canonical_exact_identifier(
            invoice["invoice_id"]
        )

        exact = match_invoice_to_payments(
            invoice,
            self.payments,
        )

        # ----------------------------------------------------
        # EXACT PATH
        # ----------------------------------------------------

        if not exact.empty:

            exact = self._filter_exact_for_reuse(
                exact,
                id_field="payment_id",
                used_ids=self.used_payment_ids,
                chain=chain,
                conflict_code="PAYMENT_ALREADY_CONSUMED",
            )

            payment_ids = self._record_ids(
                exact,
                "payment_id",
            )

            if payment_ids:

                self.used_payment_ids.update(
                    payment_ids
                )

                self._append_trace(
                    chain,
                    stage="INVOICE_TO_PAYMENT",
                    source_id=invoice_id,
                    target_ids=payment_ids,
                    method=MatchMethod.EXACT_ID,
                    confidence=100.0,
                    accepted=True,
                    requires_review=False,
                    evidence={
                        "match_basis": "invoice_id",
                        "match_count": len(payment_ids),
                    },
                )

                return exact.reset_index(
                    drop=True
                )

            chain.add_issue(
                "PAYMENT_EXACT_MATCH_CONFLICT"
            )

            return self._empty_like(
                self.payments
            )

        # ----------------------------------------------------
        # FUZZY FALLBACK
        # ----------------------------------------------------

        available = self._available_records(
            self.payments,
            id_field="payment_id",
            used_ids=self.used_payment_ids,
        )

        decision, candidate = (
            fuzzy_match_invoice_to_payment(
                invoice,
                available,
            )
        )

        candidate_ids = (
            [decision.record_id]
            if decision.record_id
            else []
        )

        self._append_trace(
            chain,
            stage="INVOICE_TO_PAYMENT",
            source_id=invoice_id,
            target_ids=candidate_ids,
            method=decision.method,
            confidence=decision.confidence,
            accepted=decision.matched,
            requires_review=decision.requires_review,
            evidence=decision.evidence,
        )

        # A human-review candidate is NOT a confirmed match.
        if (
            not decision.matched
            or candidate is None
            or not decision.record_id
        ):

            if decision.requires_review:

                chain.add_issue(
                    "PAYMENT_MATCH_REQUIRES_REVIEW"
                )

            else:

                chain.add_issue(
                    "NO_PAYMENT_MATCH"
                )

            return self._empty_like(
                self.payments
            )

        payment_id = (
            canonical_exact_identifier(
                decision.record_id
            )
        )

        if payment_id in self.used_payment_ids:

            chain.add_issue(
                f"PAYMENT_ALREADY_CONSUMED:{payment_id}"
            )

            return self._empty_like(
                self.payments
            )

        self.used_payment_ids.add(
            payment_id
        )

        return pd.DataFrame(
            [candidate]
        ).reset_index(
            drop=True
        )

    # ========================================================
    # PAYMENT -> SETTLEMENT
    # ========================================================

    def _resolve_settlements(
        self,
        payments: pd.DataFrame,
        *,
        customer_name: str,
        chain: ReconciliationChain,
    ) -> pd.DataFrame:

        collected: list[pd.Series] = []

        for _, payment in payments.iterrows():

            payment_id = (
                canonical_exact_identifier(
                    payment["payment_id"]
                )
            )

            exact = match_payment_to_settlements(
                payment,
                self.settlements,
            )

            # ------------------------------------------------
            # EXACT PATH
            # ------------------------------------------------

            if not exact.empty:

                exact = self._filter_exact_for_reuse(
                    exact,
                    id_field="settlement_id",
                    used_ids=self.used_settlement_ids,
                    chain=chain,
                    conflict_code=
                        "SETTLEMENT_ALREADY_CONSUMED",
                )

                settlement_ids = self._record_ids(
                    exact,
                    "settlement_id",
                )

                if settlement_ids:

                    self.used_settlement_ids.update(
                        settlement_ids
                    )

                    self._append_trace(
                        chain,
                        stage="PAYMENT_TO_SETTLEMENT",
                        source_id=payment_id,
                        target_ids=settlement_ids,
                        method=MatchMethod.EXACT_ID,
                        confidence=100.0,
                        accepted=True,
                        requires_review=False,
                        evidence={
                            "match_basis": "payment_id",
                            "match_count":
                                len(settlement_ids),
                        },
                    )

                    for _, row in exact.iterrows():
                        collected.append(
                            row.copy()
                        )

                    continue

                chain.add_issue(
                    f"SETTLEMENT_EXACT_MATCH_CONFLICT:"
                    f"{payment_id}"
                )

                continue

            # ------------------------------------------------
            # FUZZY FALLBACK
            # ------------------------------------------------

            available = self._available_records(
                self.settlements,
                id_field="settlement_id",
                used_ids=self.used_settlement_ids,
            )

            decision, candidate = (
                fuzzy_match_payment_to_settlement(
                    payment,
                    available,
                    customer_name=customer_name,
                )
            )

            candidate_ids = (
                [decision.record_id]
                if decision.record_id
                else []
            )

            self._append_trace(
                chain,
                stage="PAYMENT_TO_SETTLEMENT",
                source_id=payment_id,
                target_ids=candidate_ids,
                method=decision.method,
                confidence=decision.confidence,
                accepted=decision.matched,
                requires_review=decision.requires_review,
                evidence=decision.evidence,
            )

            if (
                not decision.matched
                or candidate is None
                or not decision.record_id
            ):

                chain.add_issue(
                    f"SETTLEMENT_MATCH_REQUIRES_REVIEW:"
                    f"{payment_id}"
                )

                continue

            settlement_id = (
                canonical_exact_identifier(
                    decision.record_id
                )
            )

            if (
                settlement_id
                in self.used_settlement_ids
            ):

                chain.add_issue(
                    f"SETTLEMENT_ALREADY_CONSUMED:"
                    f"{settlement_id}"
                )

                continue

            self.used_settlement_ids.add(
                settlement_id
            )

            collected.append(
                candidate.copy()
            )

        if not collected:
            return self._empty_like(
                self.settlements
            )

        return pd.DataFrame(
            collected
        ).reset_index(
            drop=True
        )

    # ========================================================
    # SETTLEMENT -> BANK
    # ========================================================

    def _resolve_bank_transactions(
        self,
        settlements: pd.DataFrame,
        *,
        customer_name: str,
        chain: ReconciliationChain,
    ) -> pd.DataFrame:

        collected: list[pd.Series] = []

        for _, settlement in settlements.iterrows():

            settlement_id = (
                canonical_exact_identifier(
                    settlement[
                        "settlement_id"
                    ]
                )
            )

            exact = (
                match_settlement_to_bank_transactions(
                    settlement,
                    self.bank_transactions,
                )
            )

            # ------------------------------------------------
            # EXACT PATH
            # ------------------------------------------------

            if not exact.empty:

                exact = self._filter_exact_for_reuse(
                    exact,
                    id_field="bank_txn_id",
                    used_ids=
                        self.used_bank_transaction_ids,
                    chain=chain,
                    conflict_code=
                        "BANK_TRANSACTION_ALREADY_CONSUMED",
                )

                bank_ids = self._record_ids(
                    exact,
                    "bank_txn_id",
                )

                if bank_ids:

                    self.used_bank_transaction_ids.update(
                        bank_ids
                    )

                    self._append_trace(
                        chain,
                        stage="SETTLEMENT_TO_BANK",
                        source_id=settlement_id,
                        target_ids=bank_ids,
                        method=MatchMethod.EXACT_ID,
                        confidence=100.0,
                        accepted=True,
                        requires_review=False,
                        evidence={
                            "match_basis":
                                "settlement_id",

                            "match_count":
                                len(bank_ids),
                        },
                    )

                    for _, row in exact.iterrows():
                        collected.append(
                            row.copy()
                        )

                    continue

                chain.add_issue(
                    f"BANK_EXACT_MATCH_CONFLICT:"
                    f"{settlement_id}"
                )

                continue

            # ------------------------------------------------
            # FUZZY FALLBACK
            # ------------------------------------------------

            available = self._available_records(
                self.bank_transactions,
                id_field="bank_txn_id",
                used_ids=
                    self.used_bank_transaction_ids,
            )

            decision, candidate = (
                fuzzy_match_settlement_to_bank(
                    settlement,
                    available,
                    customer_name=customer_name,
                )
            )

            candidate_ids = (
                [decision.record_id]
                if decision.record_id
                else []
            )

            self._append_trace(
                chain,
                stage="SETTLEMENT_TO_BANK",
                source_id=settlement_id,
                target_ids=candidate_ids,
                method=decision.method,
                confidence=decision.confidence,
                accepted=decision.matched,
                requires_review=decision.requires_review,
                evidence=decision.evidence,
            )

            if (
                not decision.matched
                or candidate is None
                or not decision.record_id
            ):

                chain.add_issue(
                    f"BANK_MATCH_REQUIRES_REVIEW:"
                    f"{settlement_id}"
                )

                continue

            bank_id = (
                canonical_exact_identifier(
                    decision.record_id
                )
            )

            if (
                bank_id
                in self.used_bank_transaction_ids
            ):

                chain.add_issue(
                    f"BANK_TRANSACTION_ALREADY_CONSUMED:"
                    f"{bank_id}"
                )

                continue

            self.used_bank_transaction_ids.add(
                bank_id
            )

            collected.append(
                candidate.copy()
            )

        if not collected:

            return self._empty_like(
                self.bank_transactions
            )

        return pd.DataFrame(
            collected
        ).reset_index(
            drop=True
        )

    # ========================================================
    # PUBLIC API
    # ========================================================

    def resolve_invoice(
        self,
        invoice: pd.Series,
    ) -> ReconciliationChain:
        """
        Resolve the operational chain for one invoice.
        """

        required_fields = {
            "invoice_id",
            "customer_name",
        }

        missing = (
            required_fields
            - set(invoice.index)
        )

        if missing:

            raise ValueError(
                "Invoice is missing required field(s): "
                + ", ".join(
                    sorted(missing)
                )
            )

        invoice_id = (
            canonical_exact_identifier(
                invoice["invoice_id"]
            )
        )

        if not invoice_id:

            raise ValueError(
                "Invoice ID cannot be blank."
            )

        chain = ReconciliationChain(
            invoice_id=invoice_id
        )

        # ----------------------------------------------------
        # PAYMENT
        # ----------------------------------------------------

        chain.payments = (
            self._resolve_payments(
                invoice,
                chain,
            )
        )

        if chain.payments.empty:

            chain.add_issue(
                "NO_CONFIRMED_PAYMENT"
            )

            return chain

        # ----------------------------------------------------
        # SETTLEMENT
        # ----------------------------------------------------

        chain.settlements = (
            self._resolve_settlements(
                chain.payments,
                customer_name=str(
                    invoice["customer_name"]
                ),
                chain=chain,
            )
        )

        if chain.settlements.empty:

            chain.add_issue(
                "NO_CONFIRMED_SETTLEMENT"
            )

            return chain

        # ----------------------------------------------------
        # BANK
        # ----------------------------------------------------

        chain.bank_transactions = (
            self._resolve_bank_transactions(
                chain.settlements,
                customer_name=str(
                    invoice["customer_name"]
                ),
                chain=chain,
            )
        )

        if chain.bank_transactions.empty:

            chain.add_issue(
                "NO_CONFIRMED_BANK_TRANSACTION"
            )

        return chain

    def resolve_batch(
        self,
        invoices: pd.DataFrame,
    ) -> list[ReconciliationChain]:
        """
        Resolve a full invoice batch.

        Processing order is deterministic so repeated benchmark
        runs produce reproducible results.
        """

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

        self.reset_usage()

        working = invoices.copy()

        working["_sort_invoice_id"] = (
            working["invoice_id"]
            .astype("string")
            .fillna("")
            .str.strip()
            .str.upper()
        )

        working = working.sort_values(
            "_sort_invoice_id",
            kind="stable",
        )

        chains: list[
            ReconciliationChain
        ] = []

        for _, invoice in working.iterrows():

            invoice = invoice.drop(
                labels=["_sort_invoice_id"]
            )

            chains.append(
                self.resolve_invoice(
                    invoice
                )
            )

        return chains