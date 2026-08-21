from __future__ import annotations

from decimal import Decimal
from datetime import date
from pathlib import Path
from typing import Any

from backend.app.cashflow.engine import CashImpactEngine
from backend.app.cashflow.impact_analyzer import CashDelayImpactAnalyzer
from backend.app.prediction.delay_predictor import DelayPredictor
from backend.app.reconciliation.engine import ReconciliationEngine


HIGH_RISK_LATE_PROBABILITY_PCT = 70.0

DEFAULT_RAW_DIR = Path("data/raw")
DEFAULT_AS_OF_DATE = date(2026, 8, 1)


def _money(value: Decimal) -> str:
    return format(value, ".2f")


def _severity_rank(value: str) -> int:
    return {
        "LOW": 1,
        "MEDIUM": 2,
        "HIGH": 3,
        "CRITICAL": 4,
    }.get(str(value).upper(), 0)


class CFOIntelligenceService:
    """
    Aggregate FlowGuard operational finance intelligence.

    This service combines:
    - reconciliation health
    - payment-delay prediction
    - receivables risk
    - cashflow forecast
    - payment-delay liquidity impact

    Benchmark and ground-truth datasets are intentionally not used here.
    """

    def __init__(
        self,
        *,
        raw_dir: Path = DEFAULT_RAW_DIR,
        as_of_date: date = DEFAULT_AS_OF_DATE,
    ) -> None:
        """
        Configure the operational dataset for CFO intelligence.

        Defaults preserve the bundled deterministic demo.
        Imported datasets can provide an isolated normalized
        directory and an explicit analysis date.
        """
        self.raw_dir = Path(raw_dir)
        self.as_of_date = as_of_date

    def _priority_actions(
        self,
        *,
        review_count: int,
        review_rate_pct: float,
        high_risk_count: int,
        high_risk_amount: Decimal,
        liquidity_severity: str,
        maximum_temporary_cash_gap: str,
        days_with_reduced_liquidity: int,
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []

        if review_count > 0:
            review_severity = (
                "HIGH"
                if review_rate_pct >= 20.0
                else "MEDIUM"
            )

            actions.append(
                {
                    "code": "RECONCILIATION_REVIEW",
                    "severity": review_severity,
                    "title": "Review reconciliation exceptions",
                    "detail": (
                        f"{review_count} reconciliation cases "
                        "currently require human review."
                    ),
                }
            )

        if high_risk_count > 0:
            actions.append(
                {
                    "code": "COLLECTIONS_PRIORITY",
                    "severity": (
                        "HIGH"
                        if high_risk_count >= 10
                        else "MEDIUM"
                    ),
                    "title": "Prioritize high-risk receivables",
                    "detail": (
                        f"{high_risk_count} open invoices exceed "
                        f"the {HIGH_RISK_LATE_PROBABILITY_PCT:.0f}% "
                        "late-payment risk threshold, representing "
                        f"{_money(high_risk_amount)} in predicted "
                        "receivables at risk."
                    ),
                }
            )

        if (
            Decimal(maximum_temporary_cash_gap)
            > Decimal("0.00")
        ):
            actions.append(
                {
                    "code": "LIQUIDITY_MONITORING",
                    "severity": liquidity_severity,
                    "title": "Monitor payment-delay liquidity exposure",
                    "detail": (
                        f"Predicted payment timing creates a temporary "
                        f"cash displacement of "
                        f"{maximum_temporary_cash_gap} across "
                        f"{days_with_reduced_liquidity} days."
                    ),
                }
            )

        actions.sort(
            key=lambda item: _severity_rank(
                str(item["severity"])
            ),
            reverse=True,
        )

        return actions

    def build_overview(
        self,
        *,
        opening_cash_balance: (
            Decimal | str | int | float
        ) = "500000.00",
        horizon_days: int = 90,
    ) -> dict[str, Any]:
        """
        Build one deterministic operational overview for the CFO dashboard.
        """

        # ----------------------------------------------------
        # Reconciliation
        # ----------------------------------------------------

        reconciliation_engine = ReconciliationEngine(
            raw_dir=self.raw_dir,
        )

        reconciliation_batch = (
            reconciliation_engine.run(
                write_outputs=False
            )
        )

        reconciliation_summary = (
            reconciliation_batch.summary
        )

        # ----------------------------------------------------
        # Payment-delay intelligence
        # ----------------------------------------------------

        predictor = DelayPredictor(
            raw_dir=self.raw_dir,
            as_of_date=self.as_of_date,
        )

        predictions = (
            predictor.predict_open_invoices()
        )

        amount_at_risk = sum(
            (
                prediction.amount_at_risk
                for prediction in predictions
            ),
            Decimal("0.00"),
        )

        high_risk_predictions = [
            prediction
            for prediction in predictions
            if prediction.late_probability
            >= HIGH_RISK_LATE_PROBABILITY_PCT
        ]

        high_risk_amount = sum(
            (
                prediction.amount_at_risk
                for prediction
                in high_risk_predictions
            ),
            Decimal("0.00"),
        )

        if predictions:
            average_late_probability = round(
                sum(
                    prediction.late_probability
                    for prediction in predictions
                )
                / len(predictions),
                2,
            )

            average_prediction_confidence = round(
                sum(
                    prediction.confidence
                    for prediction in predictions
                )
                / len(predictions),
                2,
            )
        else:
            average_late_probability = 0.0
            average_prediction_confidence = 0.0

        # ----------------------------------------------------
        # Cashflow
        # ----------------------------------------------------

        cashflow_engine = CashImpactEngine(
            raw_dir=self.raw_dir,
            as_of_date=self.as_of_date,
        )

        cashflow = cashflow_engine.forecast(
            opening_cash_balance=opening_cash_balance,
            horizon_days=horizon_days,
        )

        # ----------------------------------------------------
        # Delay-driven liquidity impact
        # ----------------------------------------------------

        impact_analyzer = (
            CashDelayImpactAnalyzer(
                raw_dir=self.raw_dir,
                as_of_date=self.as_of_date,
            )
        )

        impact = impact_analyzer.analyze(
            opening_cash_balance=opening_cash_balance,
            horizon_days=horizon_days,
        )

        delay_impact = impact["delay_impact"]

        # ----------------------------------------------------
        # Cross-module consistency
        # ----------------------------------------------------

        prediction_as_of = (
            predictor.as_of_date.isoformat()
        )

        cashflow_as_of = (
            cashflow.as_of_date.isoformat()
        )

        impact_as_of = str(
            impact["as_of_date"]
        )

        if len(
            {
                prediction_as_of,
                cashflow_as_of,
                impact_as_of,
            }
        ) != 1:
            raise RuntimeError(
                "Operational intelligence modules "
                "do not share the same as-of date."
            )

        # ----------------------------------------------------
        # CFO priorities
        # ----------------------------------------------------

        review_count = int(
            reconciliation_summary.get(
                "requires_review_count",
                0,
            )
        )

        review_rate_pct = float(
            reconciliation_summary.get(
                "requires_review_rate_pct",
                0.0,
            )
        )

        priorities = self._priority_actions(
            review_count=review_count,
            review_rate_pct=review_rate_pct,
            high_risk_count=len(
                high_risk_predictions
            ),
            high_risk_amount=high_risk_amount,
            liquidity_severity=str(
                delay_impact["severity"]
            ),
            maximum_temporary_cash_gap=str(
                delay_impact[
                    "maximum_temporary_cash_gap"
                ]
            ),
            days_with_reduced_liquidity=int(
                delay_impact[
                    "days_with_reduced_liquidity"
                ]
            ),
        )

        # ----------------------------------------------------
        # Final operational overview
        # ----------------------------------------------------

        return {
            "as_of_date": prediction_as_of,

            "reconciliation": {
                "cases_processed": int(
                    reconciliation_summary.get(
                        "cases_processed",
                        len(
                            reconciliation_batch.results
                        ),
                    )
                ),
                "complete_chain_count": int(
                    reconciliation_summary.get(
                        "complete_chain_count",
                        0,
                    )
                ),
                "complete_chain_rate_pct": float(
                    reconciliation_summary.get(
                        "complete_chain_rate_pct",
                        0.0,
                    )
                ),
                "auto_closed_count": int(
                    reconciliation_summary.get(
                        "auto_closed_count",
                        0,
                    )
                ),
                "auto_closure_rate_pct": float(
                    reconciliation_summary.get(
                        "auto_closure_rate_pct",
                        0.0,
                    )
                ),
                "requires_review_count": (
                    review_count
                ),
                "requires_review_rate_pct": (
                    review_rate_pct
                ),
                "exact_match_cases": int(
                    reconciliation_summary.get(
                        "exact_match_cases",
                        0,
                    )
                ),
                "fuzzy_recovery_cases": int(
                    reconciliation_summary.get(
                        "fuzzy_recovery_cases",
                        0,
                    )
                ),
                "unresolved_or_review_count": int(
                    reconciliation_summary.get(
                        "unresolved_or_review_count",
                        0,
                    )
                ),
            },

            "receivables": {
                "open_invoices": len(
                    predictions
                ),
                "amount_at_risk": _money(
                    amount_at_risk
                ),
                "high_risk_threshold_pct": (
                    HIGH_RISK_LATE_PROBABILITY_PCT
                ),
                "high_risk_invoices": len(
                    high_risk_predictions
                ),
                "high_risk_amount": _money(
                    high_risk_amount
                ),
                "average_late_probability_pct": (
                    average_late_probability
                ),
                "average_prediction_confidence_pct": (
                    average_prediction_confidence
                ),
            },

            "cashflow": {
                "opening_cash_balance": _money(
                    cashflow.opening_cash_balance
                ),
                "horizon_end": (
                    cashflow.horizon_end.isoformat()
                ),
                "total_expected_inflows": _money(
                    cashflow.total_expected_inflows
                ),
                "total_scheduled_outflows": _money(
                    cashflow.total_scheduled_outflows
                ),
                "projected_ending_balance": _money(
                    cashflow.projected_ending_balance
                ),
                "shortfall_detected": (
                    cashflow.shortfall_detected
                ),
                "first_shortfall_date": (
                    cashflow.first_shortfall_date.isoformat()
                    if cashflow.first_shortfall_date
                    else None
                ),
                "maximum_shortfall": _money(
                    cashflow.maximum_shortfall
                ),
                "minimum_projected_balance": _money(
                    cashflow.minimum_projected_balance
                ),
                "severity": cashflow.severity,
                "recommended_action": (
                    cashflow.recommended_action
                ),
            },

            "liquidity_risk": {
                "total_delayed_receivables": str(
                    impact[
                        "total_delayed_receivables"
                    ]
                ),
                "weighted_average_delay_days": float(
                    impact[
                        "weighted_average_delay_days"
                    ]
                ),
                "maximum_temporary_cash_gap": str(
                    delay_impact[
                        "maximum_temporary_cash_gap"
                    ]
                ),
                "maximum_gap_date": (
                    delay_impact[
                        "maximum_gap_date"
                    ]
                ),
                "days_with_reduced_liquidity": int(
                    delay_impact[
                        "days_with_reduced_liquidity"
                    ]
                ),
                "cash_delayed_by_first_expense": str(
                    delay_impact[
                        "cash_delayed_by_first_expense"
                    ]
                ),
                "incremental_shortfall": str(
                    delay_impact[
                        "incremental_shortfall"
                    ]
                ),
                "severity": str(
                    delay_impact["severity"]
                ),
            },

            "priorities": priorities,
        }
