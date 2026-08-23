from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.prediction.delay_predictor import DelayPredictor


HIGH_RISK_THRESHOLD_PCT = 70.0


class FinancialDrilldownService:
    """
    Deterministic invoice/customer intelligence.

    Works against any normalized FlowGuard raw_dir:
      - data/raw
      - imported CSV normalized directory

    No benchmark/ground-truth data is used.
    """

    def __init__(
        self,
        *,
        raw_dir: str | Path,
        as_of_date: date,
    ) -> None:
        self.raw_dir = Path(raw_dir)
        self.as_of_date = as_of_date

    def _load_customers(self) -> dict[str, dict[str, str]]:
        path = self.raw_dir / "customers.csv"

        if not path.exists():
            return {}

        customers: dict[str, dict[str, str]] = {}

        with path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            for row in csv.DictReader(handle):
                customer_id = str(
                    row.get("customer_id", "")
                ).strip()

                if not customer_id:
                    continue

                customers[customer_id] = {
                    "customer_id": customer_id,
                    "customer_name": str(
                        row.get("customer_name", "")
                    ).strip(),
                    "industry": str(
                        row.get("industry", "")
                    ).strip(),
                    "payment_terms_days": str(
                        row.get("payment_terms_days", "")
                    ).strip(),
                }

        return customers

    def invoice_intelligence(
        self,
    ) -> list[dict[str, Any]]:
        predictor = DelayPredictor(
            raw_dir=self.raw_dir,
            as_of_date=self.as_of_date,
        )

        predictions = predictor.predict_open_invoices()
        rows: list[dict[str, Any]] = []

        for prediction in predictions:
            if prediction.late_probability >= 85:
                risk_level = "CRITICAL"
            elif prediction.late_probability >= HIGH_RISK_THRESHOLD_PCT:
                risk_level = "HIGH"
            elif prediction.late_probability >= 50:
                risk_level = "MEDIUM"
            else:
                risk_level = "LOW"

            rows.append(
                {
                    "invoice_id": prediction.invoice_id,
                    "customer_id": prediction.customer_id,
                    "invoice_amount": format(
                        prediction.invoice_amount,
                        ".2f",
                    ),
                    "outstanding_amount": format(
                        prediction.outstanding_amount,
                        ".2f",
                    ),
                    "amount_at_risk": format(
                        prediction.amount_at_risk,
                        ".2f",
                    ),
                    "due_date": (
                        prediction.due_date.isoformat()
                    ),
                    "expected_payment_date": (
                        prediction.expected_payment_date.isoformat()
                    ),
                    "expected_delay_days": (
                        prediction.expected_delay_days
                    ),
                    "late_probability_pct": round(
                        prediction.late_probability,
                        2,
                    ),
                    "prediction_confidence_pct": round(
                        prediction.confidence,
                        2,
                    ),
                    "history_count": (
                        prediction.history_count
                    ),
                    "prediction_basis": (
                        prediction.prediction_basis
                    ),
                    "risk_level": risk_level,
                    "high_risk": (
                        prediction.late_probability
                        >= HIGH_RISK_THRESHOLD_PCT
                    ),
                }
            )

        rows.sort(
            key=lambda row: (
                row["late_probability_pct"],
                Decimal(row["outstanding_amount"]),
            ),
            reverse=True,
        )

        return rows

    def customer_intelligence(
        self,
    ) -> list[dict[str, Any]]:
        invoices = self.invoice_intelligence()
        customers = self._load_customers()

        grouped: dict[str, list[dict[str, Any]]] = (
            defaultdict(list)
        )

        for invoice in invoices:
            grouped[invoice["customer_id"]].append(
                invoice
            )

        results: list[dict[str, Any]] = []

        for customer_id, customer_invoices in grouped.items():
            profile = customers.get(
                customer_id,
                {
                    "customer_id": customer_id,
                    "customer_name": "",
                    "industry": "",
                    "payment_terms_days": "",
                },
            )

            total_outstanding = sum(
                (
                    Decimal(
                        invoice["outstanding_amount"]
                    )
                    for invoice in customer_invoices
                ),
                Decimal("0.00"),
            )

            amount_at_risk = sum(
                (
                    Decimal(
                        invoice["amount_at_risk"]
                    )
                    for invoice in customer_invoices
                ),
                Decimal("0.00"),
            )

            high_risk = [
                invoice
                for invoice in customer_invoices
                if invoice["high_risk"]
            ]

            if total_outstanding > 0:
                weighted_late_probability = sum(
                    (
                        Decimal(
                            str(
                                invoice[
                                    "late_probability_pct"
                                ]
                            )
                        )
                        * Decimal(
                            invoice[
                                "outstanding_amount"
                            ]
                        )
                        for invoice in customer_invoices
                    ),
                    Decimal("0.00"),
                ) / total_outstanding

                weighted_delay = sum(
                    (
                        Decimal(
                            invoice[
                                "outstanding_amount"
                            ]
                        )
                        * Decimal(
                            invoice[
                                "expected_delay_days"
                            ]
                        )
                        for invoice in customer_invoices
                    ),
                    Decimal("0.00"),
                ) / total_outstanding

            else:
                weighted_late_probability = (
                    Decimal("0.00")
                )
                weighted_delay = Decimal("0.00")

            avg_confidence = (
                sum(
                    Decimal(
                        str(
                            invoice[
                                "prediction_confidence_pct"
                            ]
                        )
                    )
                    for invoice in customer_invoices
                )
                / Decimal(len(customer_invoices))
                if customer_invoices
                else Decimal("0.00")
            )

            max_probability = max(
                (
                    invoice[
                        "late_probability_pct"
                    ]
                    for invoice in customer_invoices
                ),
                default=0.0,
            )

            if max_probability >= 85:
                risk_level = "CRITICAL"
            elif high_risk:
                risk_level = "HIGH"
            elif max_probability >= 50:
                risk_level = "MEDIUM"
            else:
                risk_level = "LOW"

            results.append(
                {
                    **profile,
                    "open_invoices": len(
                        customer_invoices
                    ),
                    "high_risk_invoices": len(
                        high_risk
                    ),
                    "total_outstanding": format(
                        total_outstanding,
                        ".2f",
                    ),
                    "predicted_delayed_exposure": format(
                        amount_at_risk,
                        ".2f",
                    ),
                    "weighted_late_probability_pct": round(
                        float(
                            weighted_late_probability
                        ),
                        2,
                    ),
                    "weighted_expected_delay_days": round(
                        float(weighted_delay),
                        2,
                    ),
                    "average_prediction_confidence_pct": round(
                        float(avg_confidence),
                        2,
                    ),
                    "risk_level": risk_level,
                    "invoice_ids": [
                        invoice["invoice_id"]
                        for invoice in customer_invoices
                    ],
                }
            )

        results.sort(
            key=lambda row: (
                Decimal(
                    row[
                        "predicted_delayed_exposure"
                    ]
                ),
                row[
                    "weighted_late_probability_pct"
                ],
            ),
            reverse=True,
        )

        return results

    def customer_cashflow_impact(
        self,
        *,
        customer_id: str,
        opening_cash_balance: Decimal = Decimal("0.00"),
        horizon_days: int = 90,
    ) -> dict[str, Any]:
        """
        Isolate the cashflow effect of predicted payment delays
        for one customer.

        Baseline:
            every open invoice arrives on its contractual
            due date (or analysis date if already overdue).

        Customer-delay scenario:
            only the selected customer's invoices move to
            their FlowGuard-predicted payment dates.

        Other customers remain unchanged. This makes the
        resulting liquidity difference attributable to the
        selected customer.
        """
        from datetime import timedelta

        if horizon_days < 1:
            raise ValueError(
                "horizon_days must be at least 1."
            )

        customer_id = str(customer_id).strip()

        invoices = self.invoice_intelligence()

        customer_invoices = [
            invoice
            for invoice in invoices
            if invoice["customer_id"] == customer_id
        ]

        if not customer_invoices:
            raise ValueError(
                f"No open invoice exposure found for "
                f"customer {customer_id}."
            )

        horizon_end = (
            self.as_of_date
            + timedelta(days=horizon_days)
        )

        baseline_inflows: dict[date, Decimal] = {}
        scenario_inflows: dict[date, Decimal] = {}
        outflows: dict[date, Decimal] = {}

        def add_amount(
            target: dict[date, Decimal],
            day: date,
            amount: Decimal,
        ) -> None:
            target[day] = (
                target.get(day, Decimal("0.00"))
                + amount
            )

        delayed_exposure = Decimal("0.00")
        weighted_delay_amount = Decimal("0.00")
        delayed_invoice_ids: list[str] = []

        # -----------------------------------------
        # Company inflows
        # -----------------------------------------

        for invoice in invoices:
            outstanding = Decimal(
                invoice["outstanding_amount"]
            )

            if outstanding <= Decimal("0.00"):
                continue

            due_date = date.fromisoformat(
                invoice["due_date"]
            )

            baseline_date = max(
                due_date,
                self.as_of_date,
            )

            predicted_date = date.fromisoformat(
                invoice["expected_payment_date"]
            )

            predicted_date = max(
                predicted_date,
                self.as_of_date,
            )

            # Baseline assumes contractual timing.
            if baseline_date <= horizon_end:
                add_amount(
                    baseline_inflows,
                    baseline_date,
                    outstanding,
                )

            scenario_date = baseline_date

            # Only move invoices belonging to the
            # selected customer.
            if invoice["customer_id"] == customer_id:
                scenario_date = predicted_date

                delay_days = max(
                    0,
                    (
                        predicted_date
                        - baseline_date
                    ).days,
                )

                if delay_days > 0:
                    delayed_exposure += outstanding
                    weighted_delay_amount += (
                        outstanding
                        * Decimal(delay_days)
                    )
                    delayed_invoice_ids.append(
                        invoice["invoice_id"]
                    )

            if scenario_date <= horizon_end:
                add_amount(
                    scenario_inflows,
                    scenario_date,
                    outstanding,
                )

        # -----------------------------------------
        # Scheduled expenses
        # -----------------------------------------

        expenses_path = (
            self.raw_dir / "expenses.csv"
        )

        if expenses_path.exists():
            with expenses_path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as handle:
                for row in csv.DictReader(handle):
                    status = str(
                        row.get("status", "")
                    ).strip().upper()

                    if status != "SCHEDULED":
                        continue

                    raw_due_date = str(
                        row.get("due_date", "")
                    ).strip()

                    if not raw_due_date:
                        continue

                    expense_date = (
                        date.fromisoformat(
                            raw_due_date
                        )
                    )

                    if not (
                        self.as_of_date
                        <= expense_date
                        <= horizon_end
                    ):
                        continue

                    raw_amount = row.get(
                        "amount",
                        row.get(
                            "amount_decimal",
                            "0",
                        ),
                    )

                    expense_amount = Decimal(
                        str(raw_amount)
                        .replace(",", "")
                        .strip()
                    )

                    add_amount(
                        outflows,
                        expense_date,
                        expense_amount,
                    )

        # -----------------------------------------
        # Simulate baseline and customer-delay case
        # -----------------------------------------

        baseline_balance = opening_cash_balance
        scenario_balance = opening_cash_balance

        baseline_minimum = opening_cash_balance
        scenario_minimum = opening_cash_balance

        baseline_minimum_date = self.as_of_date
        scenario_minimum_date = self.as_of_date

        maximum_temporary_cash_gap = (
            Decimal("0.00")
        )
        maximum_gap_date: date | None = None

        days_with_reduced_liquidity = 0

        for offset in range(horizon_days + 1):
            day = (
                self.as_of_date
                + timedelta(days=offset)
            )

            baseline_balance += (
                baseline_inflows.get(
                    day,
                    Decimal("0.00"),
                )
            )

            scenario_balance += (
                scenario_inflows.get(
                    day,
                    Decimal("0.00"),
                )
            )

            baseline_balance -= outflows.get(
                day,
                Decimal("0.00"),
            )

            scenario_balance -= outflows.get(
                day,
                Decimal("0.00"),
            )

            if baseline_balance < baseline_minimum:
                baseline_minimum = baseline_balance
                baseline_minimum_date = day

            if scenario_balance < scenario_minimum:
                scenario_minimum = scenario_balance
                scenario_minimum_date = day

            daily_gap = max(
                Decimal("0.00"),
                baseline_balance
                - scenario_balance,
            )

            if daily_gap > Decimal("0.00"):
                days_with_reduced_liquidity += 1

            if daily_gap > maximum_temporary_cash_gap:
                maximum_temporary_cash_gap = (
                    daily_gap
                )
                maximum_gap_date = day

        # -----------------------------------------
        # Shortfall impact
        # -----------------------------------------

        baseline_shortfall = max(
            Decimal("0.00"),
            -baseline_minimum,
        )

        scenario_shortfall = max(
            Decimal("0.00"),
            -scenario_minimum,
        )

        incremental_shortfall = max(
            Decimal("0.00"),
            scenario_shortfall
            - baseline_shortfall,
        )

        minimum_balance_deterioration = max(
            Decimal("0.00"),
            baseline_minimum
            - scenario_minimum,
        )

        weighted_delay_days = (
            weighted_delay_amount
            / delayed_exposure
            if delayed_exposure > Decimal("0.00")
            else Decimal("0.00")
        )

        # -----------------------------------------
        # First scheduled expense impact
        # -----------------------------------------

        first_expense_date = (
            min(outflows)
            if outflows
            else None
        )

        cash_delayed_by_first_expense = (
            Decimal("0.00")
        )

        if first_expense_date is not None:
            baseline_before_expense = sum(
                (
                    amount
                    for day, amount
                    in baseline_inflows.items()
                    if day <= first_expense_date
                ),
                Decimal("0.00"),
            )

            scenario_before_expense = sum(
                (
                    amount
                    for day, amount
                    in scenario_inflows.items()
                    if day <= first_expense_date
                ),
                Decimal("0.00"),
            )

            cash_delayed_by_first_expense = max(
                Decimal("0.00"),
                baseline_before_expense
                - scenario_before_expense,
            )

        # -----------------------------------------
        # Customer identity
        # -----------------------------------------

        customer_profile = self._load_customers().get(
            customer_id,
            {
                "customer_id": customer_id,
                "customer_name": "",
                "industry": "",
                "payment_terms_days": "",
            },
        )

        total_outstanding = sum(
            (
                Decimal(
                    invoice["outstanding_amount"]
                )
                for invoice in customer_invoices
            ),
            Decimal("0.00"),
        )

        high_risk_invoices = sum(
            1
            for invoice in customer_invoices
            if invoice["high_risk"]
        )

        # -----------------------------------------
        # Severity
        # -----------------------------------------

        if incremental_shortfall > Decimal("0.00"):
            severity = "HIGH"
        elif (
            opening_cash_balance > Decimal("0.00")
            and maximum_temporary_cash_gap
            >= opening_cash_balance
        ):
            severity = "HIGH"
        elif maximum_temporary_cash_gap > Decimal("0.00"):
            severity = "MEDIUM"
        else:
            severity = "LOW"

        return {
            **customer_profile,
            "open_invoices": len(
                customer_invoices
            ),
            "high_risk_invoices": (
                high_risk_invoices
            ),
            "invoice_ids": [
                invoice["invoice_id"]
                for invoice in customer_invoices
            ],
            "delayed_invoice_ids": (
                delayed_invoice_ids
            ),
            "total_outstanding": format(
                total_outstanding,
                ".2f",
            ),
            "predicted_delayed_exposure": format(
                delayed_exposure,
                ".2f",
            ),
            "weighted_expected_delay_days": round(
                float(weighted_delay_days),
                2,
            ),
            "maximum_temporary_cash_gap": format(
                maximum_temporary_cash_gap,
                ".2f",
            ),
            "maximum_gap_date": (
                maximum_gap_date.isoformat()
                if maximum_gap_date
                else None
            ),
            "days_with_reduced_liquidity": (
                days_with_reduced_liquidity
            ),
            "first_scheduled_expense_date": (
                first_expense_date.isoformat()
                if first_expense_date
                else None
            ),
            "cash_delayed_by_first_expense": format(
                cash_delayed_by_first_expense,
                ".2f",
            ),
            "baseline_minimum_balance": format(
                baseline_minimum,
                ".2f",
            ),
            "baseline_minimum_balance_date": (
                baseline_minimum_date.isoformat()
            ),
            "customer_delay_minimum_balance": format(
                scenario_minimum,
                ".2f",
            ),
            "customer_delay_minimum_balance_date": (
                scenario_minimum_date.isoformat()
            ),
            "minimum_balance_deterioration": format(
                minimum_balance_deterioration,
                ".2f",
            ),
            "baseline_shortfall": format(
                baseline_shortfall,
                ".2f",
            ),
            "customer_delay_shortfall": format(
                scenario_shortfall,
                ".2f",
            ),
            "incremental_shortfall": format(
                incremental_shortfall,
                ".2f",
            ),
            "baseline_ending_balance": format(
                baseline_balance,
                ".2f",
            ),
            "customer_delay_ending_balance": format(
                scenario_balance,
                ".2f",
            ),
            "severity": severity,
            "horizon_days": horizon_days,
        }

    def rank_customers_by_cashflow_impact(
        self,
        *,
        opening_cash_balance: Decimal = Decimal("0.00"),
        horizon_days: int = 90,
        limit: int = 5,
    ) -> dict[str, Any]:
        """
        Rank customers by their isolated impact on company cashflow.

        If any customer creates an additional cash shortfall,
        ranking prioritizes incremental shortfall.

        Otherwise customers are ranked by temporary liquidity
        pressure, which avoids incorrectly calling every delay
        a cash shortage.
        """
        if limit < 1:
            raise ValueError("limit must be at least 1.")

        customers = self.customer_intelligence()

        impacts: list[dict[str, Any]] = []

        for customer in customers:
            impact = self.customer_cashflow_impact(
                customer_id=customer["customer_id"],
                opening_cash_balance=opening_cash_balance,
                horizon_days=horizon_days,
            )
            impacts.append(impact)

        actual_shortfall_exists = any(
            Decimal(impact["incremental_shortfall"])
            > Decimal("0.00")
            for impact in impacts
        )

        if actual_shortfall_exists:
            ranking_basis = "incremental_shortfall"

            impacts.sort(
                key=lambda impact: (
                    Decimal(
                        impact["incremental_shortfall"]
                    ),
                    Decimal(
                        impact[
                            "maximum_temporary_cash_gap"
                        ]
                    ),
                    Decimal(
                        impact[
                            "predicted_delayed_exposure"
                        ]
                    ),
                ),
                reverse=True,
            )

        else:
            ranking_basis = (
                "temporary_liquidity_pressure"
            )

            impacts.sort(
                key=lambda impact: (
                    Decimal(
                        impact[
                            "maximum_temporary_cash_gap"
                        ]
                    ),
                    Decimal(
                        impact[
                            "predicted_delayed_exposure"
                        ]
                    ),
                    impact["high_risk_invoices"],
                ),
                reverse=True,
            )

        ranked: list[dict[str, Any]] = []

        for rank, impact in enumerate(
            impacts[:limit],
            start=1,
        ):
            row = dict(impact)
            row["rank"] = rank
            ranked.append(row)

        return {
            "ranking_basis": ranking_basis,
            "customer_count_evaluated": len(impacts),
            "customers": ranked,
        }

    def combined_customer_cashflow_impact(
        self,
        *,
        customer_ids: list[str],
        opening_cash_balance: Decimal = Decimal("0.00"),
        horizon_days: int = 90,
    ) -> dict[str, Any]:
        """
        Calculate the combined company cashflow impact when
        multiple selected customers pay on their predicted
        payment dates.

        This runs one combined timeline rather than adding
        individual customer cash gaps.
        """
        from datetime import timedelta

        selected_ids = {
            str(customer_id).strip()
            for customer_id in customer_ids
            if str(customer_id).strip()
        }

        if not selected_ids:
            raise ValueError(
                "At least one customer_id is required."
            )

        if horizon_days < 1:
            raise ValueError(
                "horizon_days must be at least 1."
            )

        invoices = self.invoice_intelligence()
        customers = self._load_customers()

        selected_invoices = [
            invoice
            for invoice in invoices
            if invoice["customer_id"] in selected_ids
        ]

        if not selected_invoices:
            raise ValueError(
                "No open invoice exposure found for the "
                "selected customers."
            )

        horizon_end = (
            self.as_of_date
            + timedelta(days=horizon_days)
        )

        baseline_inflows: dict[date, Decimal] = {}
        scenario_inflows: dict[date, Decimal] = {}
        outflows: dict[date, Decimal] = {}

        def add_amount(
            target: dict[date, Decimal],
            day: date,
            amount: Decimal,
        ) -> None:
            target[day] = (
                target.get(day, Decimal("0.00"))
                + amount
            )

        combined_outstanding = Decimal("0.00")
        combined_delayed_exposure = Decimal("0.00")
        weighted_delay_amount = Decimal("0.00")
        delayed_invoice_ids: list[str] = []

        per_customer: dict[str, dict[str, Any]] = {}

        for customer_id in selected_ids:
            profile = customers.get(
                customer_id,
                {
                    "customer_id": customer_id,
                    "customer_name": "",
                },
            )

            per_customer[customer_id] = {
                "customer_id": customer_id,
                "customer_name": profile.get(
                    "customer_name",
                    "",
                ),
                "outstanding": Decimal("0.00"),
                "delayed_exposure": Decimal("0.00"),
                "delayed_invoice_ids": [],
            }

        # -----------------------------------------
        # Build baseline and combined-delay inflows
        # -----------------------------------------

        for invoice in invoices:
            outstanding = Decimal(
                invoice["outstanding_amount"]
            )

            if outstanding <= Decimal("0.00"):
                continue

            due_date = date.fromisoformat(
                invoice["due_date"]
            )

            baseline_date = max(
                due_date,
                self.as_of_date,
            )

            predicted_date = max(
                date.fromisoformat(
                    invoice["expected_payment_date"]
                ),
                self.as_of_date,
            )

            if baseline_date <= horizon_end:
                add_amount(
                    baseline_inflows,
                    baseline_date,
                    outstanding,
                )

            scenario_date = baseline_date

            customer_id = invoice["customer_id"]

            if customer_id in selected_ids:
                combined_outstanding += outstanding

                per_customer[customer_id][
                    "outstanding"
                ] += outstanding

                scenario_date = predicted_date

                delay_days = max(
                    0,
                    (
                        predicted_date
                        - baseline_date
                    ).days,
                )

                if delay_days > 0:
                    combined_delayed_exposure += (
                        outstanding
                    )

                    weighted_delay_amount += (
                        outstanding
                        * Decimal(delay_days)
                    )

                    delayed_invoice_ids.append(
                        invoice["invoice_id"]
                    )

                    per_customer[customer_id][
                        "delayed_exposure"
                    ] += outstanding

                    per_customer[customer_id][
                        "delayed_invoice_ids"
                    ].append(
                        invoice["invoice_id"]
                    )

            if scenario_date <= horizon_end:
                add_amount(
                    scenario_inflows,
                    scenario_date,
                    outstanding,
                )

        # -----------------------------------------
        # Load scheduled expenses
        # -----------------------------------------

        expenses_path = self.raw_dir / "expenses.csv"

        if expenses_path.exists():
            with expenses_path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as handle:
                for row in csv.DictReader(handle):
                    status = str(
                        row.get("status", "")
                    ).strip().upper()

                    if status != "SCHEDULED":
                        continue

                    raw_due_date = str(
                        row.get("due_date", "")
                    ).strip()

                    if not raw_due_date:
                        continue

                    expense_date = date.fromisoformat(
                        raw_due_date
                    )

                    if not (
                        self.as_of_date
                        <= expense_date
                        <= horizon_end
                    ):
                        continue

                    amount = Decimal(
                        str(
                            row.get(
                                "amount",
                                "0",
                            )
                        )
                        .replace(",", "")
                        .strip()
                    )

                    add_amount(
                        outflows,
                        expense_date,
                        amount,
                    )

        # -----------------------------------------
        # Simulate both timelines
        # -----------------------------------------

        baseline_balance = opening_cash_balance
        scenario_balance = opening_cash_balance

        baseline_minimum = opening_cash_balance
        scenario_minimum = opening_cash_balance

        baseline_minimum_date = self.as_of_date
        scenario_minimum_date = self.as_of_date

        maximum_temporary_cash_gap = (
            Decimal("0.00")
        )
        maximum_gap_date: date | None = None

        days_with_reduced_liquidity = 0

        for offset in range(horizon_days + 1):
            day = (
                self.as_of_date
                + timedelta(days=offset)
            )

            baseline_balance += baseline_inflows.get(
                day,
                Decimal("0.00"),
            )

            scenario_balance += scenario_inflows.get(
                day,
                Decimal("0.00"),
            )

            baseline_balance -= outflows.get(
                day,
                Decimal("0.00"),
            )

            scenario_balance -= outflows.get(
                day,
                Decimal("0.00"),
            )

            if baseline_balance < baseline_minimum:
                baseline_minimum = baseline_balance
                baseline_minimum_date = day

            if scenario_balance < scenario_minimum:
                scenario_minimum = scenario_balance
                scenario_minimum_date = day

            daily_gap = max(
                Decimal("0.00"),
                baseline_balance
                - scenario_balance,
            )

            if daily_gap > Decimal("0.00"):
                days_with_reduced_liquidity += 1

            if daily_gap > maximum_temporary_cash_gap:
                maximum_temporary_cash_gap = daily_gap
                maximum_gap_date = day

        # -----------------------------------------
        # Shortfall impact
        # -----------------------------------------

        baseline_shortfall = max(
            Decimal("0.00"),
            -baseline_minimum,
        )

        scenario_shortfall = max(
            Decimal("0.00"),
            -scenario_minimum,
        )

        incremental_shortfall = max(
            Decimal("0.00"),
            scenario_shortfall
            - baseline_shortfall,
        )

        minimum_balance_deterioration = max(
            Decimal("0.00"),
            baseline_minimum
            - scenario_minimum,
        )

        weighted_delay_days = (
            weighted_delay_amount
            / combined_delayed_exposure
            if combined_delayed_exposure
            > Decimal("0.00")
            else Decimal("0.00")
        )

        if incremental_shortfall > Decimal("0.00"):
            severity = "HIGH"
        elif (
            opening_cash_balance > Decimal("0.00")
            and maximum_temporary_cash_gap
            >= opening_cash_balance
        ):
            severity = "HIGH"
        elif maximum_temporary_cash_gap > Decimal("0.00"):
            severity = "MEDIUM"
        else:
            severity = "LOW"

        customer_breakdown = []

        for customer_id in sorted(selected_ids):
            row = per_customer[customer_id]

            customer_breakdown.append(
                {
                    "customer_id": customer_id,
                    "customer_name": (
                        row["customer_name"]
                    ),
                    "outstanding": format(
                        row["outstanding"],
                        ".2f",
                    ),
                    "delayed_exposure": format(
                        row["delayed_exposure"],
                        ".2f",
                    ),
                    "delayed_invoice_ids": (
                        row["delayed_invoice_ids"]
                    ),
                }
            )

        return {
            "customer_ids": sorted(selected_ids),
            "customer_count": len(selected_ids),
            "customers": customer_breakdown,
            "combined_outstanding": format(
                combined_outstanding,
                ".2f",
            ),
            "combined_delayed_exposure": format(
                combined_delayed_exposure,
                ".2f",
            ),
            "delayed_invoice_ids": delayed_invoice_ids,
            "weighted_expected_delay_days": round(
                float(weighted_delay_days),
                2,
            ),
            "maximum_temporary_cash_gap": format(
                maximum_temporary_cash_gap,
                ".2f",
            ),
            "maximum_gap_date": (
                maximum_gap_date.isoformat()
                if maximum_gap_date
                else None
            ),
            "days_with_reduced_liquidity": (
                days_with_reduced_liquidity
            ),
            "baseline_minimum_balance": format(
                baseline_minimum,
                ".2f",
            ),
            "baseline_minimum_balance_date": (
                baseline_minimum_date.isoformat()
            ),
            "combined_delay_minimum_balance": format(
                scenario_minimum,
                ".2f",
            ),
            "combined_delay_minimum_balance_date": (
                scenario_minimum_date.isoformat()
            ),
            "minimum_balance_deterioration": format(
                minimum_balance_deterioration,
                ".2f",
            ),
            "baseline_shortfall": format(
                baseline_shortfall,
                ".2f",
            ),
            "combined_delay_shortfall": format(
                scenario_shortfall,
                ".2f",
            ),
            "incremental_shortfall": format(
                incremental_shortfall,
                ".2f",
            ),
            "baseline_ending_balance": format(
                baseline_balance,
                ".2f",
            ),
            "combined_delay_ending_balance": format(
                scenario_balance,
                ".2f",
            ),
            "severity": severity,
            "horizon_days": horizon_days,
        }
