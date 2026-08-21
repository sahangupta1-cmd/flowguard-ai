from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
)


# ---------------------------------------------------------------------------
# Reviewer / benchmark safety
# ---------------------------------------------------------------------------

FORBIDDEN_BENCHMARK_KEYS = {
    "benchmark_id",
    "case_id",
    "stress_id",
    "scenario",
    "true_status",
    "true_root_cause",
    "expected_status",
    "expected_root_cause",
    "expected_match_method",
    "expected_payment_ids",
    "expected_settlement_ids",
    "expected_bank_transaction_ids",
    "should_auto_resolve",
}


def _assert_no_benchmark_leakage(
    value: Any,
    path: str = "payload",
) -> Any:
    """
    Recursively ensure benchmark / ground-truth fields never appear
    in operational API responses.
    """

    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).strip().lower()

            if normalized_key in FORBIDDEN_BENCHMARK_KEYS:
                raise ValueError(
                    f"Benchmark field '{key}' is not allowed "
                    f"in operational API payloads."
                )

            _assert_no_benchmark_leakage(
                item,
                f"{path}.{key}",
            )

    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_no_benchmark_leakage(
                item,
                f"{path}[{index}]",
            )

    return value


# ---------------------------------------------------------------------------
# Common base model
# ---------------------------------------------------------------------------

class StrictAPIModel(BaseModel):
    """
    Base model used by FlowGuard operational APIs.

    Unknown fields are rejected so accidental benchmark fields or
    unexpected data do not silently enter API contracts.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(StrictAPIModel):
    status: str = "ok"
    service: str = "flowguard-api"
    version: str = "1.0.0"


# ---------------------------------------------------------------------------
# Reconciliation execution
# ---------------------------------------------------------------------------

class ReconciliationRunRequest(StrictAPIModel):
    """
    Request for running the reconciliation engine.

    The API intentionally does not accept:
      - benchmark labels
      - ground-truth paths
      - scenarios
      - expected classifications

    The reconciliation engine operates only on operational finance data.
    """

    persist_output: bool = Field(
        default=False,
        description=(
            "Whether reconciliation output should be persisted "
            "to the configured operational output directory."
        ),
    )


# ---------------------------------------------------------------------------
# Reconciliation result
# ---------------------------------------------------------------------------

class ReconciliationResultResponse(StrictAPIModel):
    invoice_id: str = Field(min_length=1)

    customer_id: str = Field(min_length=1)
    customer_name: str = Field(min_length=1)

    invoice_amount: Decimal

    payment_ids: list[str] = Field(default_factory=list)
    settlement_ids: list[str] = Field(default_factory=list)
    bank_transaction_ids: list[str] = Field(default_factory=list)

    payment_amount: Decimal = Decimal("0.00")
    expected_settlement: Decimal = Decimal("0.00")
    actual_bank_amount: Decimal = Decimal("0.00")
    difference: Decimal = Decimal("0.00")

    status: str
    root_cause: str

    confidence: float = Field(
    ge=0.0,
    le=100.0,
    description="Reconciliation confidence percentage from 0 to 100.",
    )

    match_method: str

    requires_review: bool

    explanation: str = ""
    recommended_action: str = ""

    evidence: dict[str, Any] = Field(default_factory=dict)

    @field_validator("evidence")
    @classmethod
    def validate_evidence(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        _assert_no_benchmark_leakage(
            value,
            path="evidence",
        )

        return value

    @field_serializer(
        "invoice_amount",
        "payment_amount",
        "expected_settlement",
        "actual_bank_amount",
        "difference",
    )
    def serialize_money(
        self,
        value: Decimal,
    ) -> str:
        """
        Serialize financial amounts as decimal strings.

        This prevents binary floating-point precision changes
        between Python, JSON and the frontend.
        """
        return format(value, ".2f")


# ---------------------------------------------------------------------------
# Reconciliation list
# ---------------------------------------------------------------------------

class ReconciliationListResponse(StrictAPIModel):
    count: int = Field(ge=0)

    results: list[ReconciliationResultResponse] = Field(
        default_factory=list
    )


# ---------------------------------------------------------------------------
# Reconciliation run response
# ---------------------------------------------------------------------------

class ReconciliationRunResponse(StrictAPIModel):
    processed: int = Field(ge=0)

    summary: dict[str, Any] = Field(
        default_factory=dict
    )

    results: list[ReconciliationResultResponse] = Field(
        default_factory=list
    )

    @field_validator("summary")
    @classmethod
    def validate_summary(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        _assert_no_benchmark_leakage(
            value,
            path="summary",
        )

        return value


# ---------------------------------------------------------------------------
# Reconciliation detail response
# ---------------------------------------------------------------------------

class ReconciliationDetailResponse(StrictAPIModel):
    result: ReconciliationResultResponse


# ---------------------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------------------

class DashboardSummaryResponse(StrictAPIModel):
    """
    Operational dashboard summary.

    Summary contents come from the reconciliation engine and remain
    flexible so additional operational metrics can be added later
    without exposing benchmark information.
    """

    summary: dict[str, Any] = Field(
        default_factory=dict
    )

    @field_validator("summary")
    @classmethod
    def validate_summary(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        _assert_no_benchmark_leakage(
            value,
            path="summary",
        )

        return value


# ---------------------------------------------------------------------------
# Error response
# ---------------------------------------------------------------------------

class APIErrorResponse(StrictAPIModel):
    error: str
    detail: str | None = None

# ============================================================
# Payment-delay prediction API
# ============================================================

class PaymentDelayResponse(StrictAPIModel):
    invoice_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)

    invoice_amount: Decimal
    due_date: str

    expected_delay_days: int = Field(ge=0)
    expected_payment_date: str

    late_probability: float = Field(
        ge=0.0,
        le=100.0,
    )

    confidence: float = Field(
        ge=0.0,
        le=100.0,
    )

    history_count: int = Field(ge=0)
    prediction_basis: str

    amount_at_risk: Decimal

    @field_serializer(
        "invoice_amount",
        "amount_at_risk",
    )
    def serialize_money(
        self,
        value: Decimal,
    ) -> str:
        return format(value, ".2f")


class PaymentDelayListResponse(StrictAPIModel):
    as_of_date: str

    count: int = Field(ge=0)

    predictions: list[PaymentDelayResponse] = Field(
        default_factory=list
    )


# ============================================================
# Cashflow forecast API
# ============================================================

class CashflowForecastRequest(StrictAPIModel):
    opening_cash_balance: Decimal = Field(
        ge=Decimal("0.00"),
        description="Opening cash available at the forecast start date.",
    )

    horizon_days: int = Field(
        default=90,
        ge=1,
        le=365,
        description="Forecast horizon in days.",
    )


class CashflowForecastResponse(StrictAPIModel):
    as_of_date: str
    horizon_end: str

    opening_cash_balance: Decimal
    total_expected_inflows: Decimal
    total_scheduled_outflows: Decimal
    projected_ending_balance: Decimal

    shortfall_detected: bool
    first_shortfall_date: str | None = None

    maximum_shortfall: Decimal
    minimum_projected_balance: Decimal

    severity: str
    recommended_action: str

    @field_serializer(
        "opening_cash_balance",
        "total_expected_inflows",
        "total_scheduled_outflows",
        "projected_ending_balance",
        "maximum_shortfall",
        "minimum_projected_balance",
    )
    def serialize_money(
        self,
        value: Decimal,
    ) -> str:
        return format(value, ".2f")


# ============================================================
# Payment-delay liquidity-impact API
# ============================================================

class CashDelayImpactRequest(StrictAPIModel):
    opening_cash_balance: Decimal = Field(
        ge=Decimal("0.00"),
        description="Opening cash available at the analysis date.",
    )

    horizon_days: int = Field(
        default=90,
        ge=1,
        le=365,
    )


class CashPositionResponse(StrictAPIModel):
    minimum_balance: Decimal
    minimum_balance_date: str
    first_shortfall_date: str | None = None
    maximum_shortfall: Decimal
    ending_balance: Decimal

    @field_serializer(
        "minimum_balance",
        "maximum_shortfall",
        "ending_balance",
    )
    def serialize_money(
        self,
        value: Decimal,
    ) -> str:
        return format(value, ".2f")


class DelayImpactMetricsResponse(StrictAPIModel):
    maximum_temporary_cash_gap: Decimal
    maximum_gap_date: str | None = None

    days_with_reduced_liquidity: int = Field(ge=0)

    first_scheduled_expense_date: str | None = None
    cash_delayed_by_first_expense: Decimal

    minimum_balance_deterioration: Decimal
    incremental_shortfall: Decimal

    severity: str

    @field_serializer(
        "maximum_temporary_cash_gap",
        "cash_delayed_by_first_expense",
        "minimum_balance_deterioration",
        "incremental_shortfall",
    )
    def serialize_money(
        self,
        value: Decimal,
    ) -> str:
        return format(value, ".2f")


class CashDelayImpactResponse(StrictAPIModel):
    as_of_date: str
    horizon_end: str

    opening_cash_balance: Decimal
    total_delayed_receivables: Decimal

    weighted_average_delay_days: float = Field(
        ge=0.0
    )

    baseline: CashPositionResponse
    predicted_delay: CashPositionResponse
    delay_impact: DelayImpactMetricsResponse

    @field_serializer(
        "opening_cash_balance",
        "total_delayed_receivables",
    )
    def serialize_money(
        self,
        value: Decimal,
    ) -> str:
        return format(value, ".2f")
