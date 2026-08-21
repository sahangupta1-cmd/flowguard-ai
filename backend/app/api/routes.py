from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.app.api.schemas import (
    DashboardSummaryResponse,
    CashDelayImpactRequest,
    CashDelayImpactResponse,
    CashflowForecastRequest,
    CashflowForecastResponse,
    HealthResponse,
    ReconciliationDetailResponse,
    ReconciliationListResponse,
    ReconciliationResultResponse,
    ReconciliationRunRequest,
    ReconciliationRunResponse,
    PaymentDelayListResponse,
    PaymentDelayResponse,
)
from backend.app.reconciliation.engine import ReconciliationEngine

from backend.app.prediction.delay_predictor import DelayPredictor
from backend.app.cashflow.engine import CashImpactEngine
from backend.app.cashflow.impact_analyzer import CashDelayImpactAnalyzer


logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _json_safe(value: Any) -> Any:
    """
    Convert operational values into JSON-safe representations.

    Financial Decimal values are kept as decimal strings rather
    than binary floating-point numbers.
    """

    if isinstance(value, Decimal):
        return format(value, ".2f")

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [
            _json_safe(item)
            for item in value
        ]

    return value


def _enum_text(value: Any) -> str:
    """
    Return the underlying Enum value when available.
    """

    if isinstance(value, Enum):
        return str(value.value)

    return str(value)


def _to_api_result(result: Any) -> ReconciliationResultResponse:
    """
    Convert the existing reconciliation-domain result into
    the operational API contract.

    No reconciliation logic is duplicated here.
    """

    return ReconciliationResultResponse(
        invoice_id=str(result.invoice_id),
        customer_id=str(result.customer_id),
        customer_name=str(result.customer_name),
        invoice_amount=result.invoice_amount,
        payment_ids=list(result.payment_ids),
        settlement_ids=list(result.settlement_ids),
        bank_transaction_ids=list(
            result.bank_transaction_ids
        ),
        payment_amount=result.payment_amount,
        expected_settlement=result.expected_settlement,
        actual_bank_amount=result.actual_bank_amount,
        difference=result.difference,
        status=_enum_text(result.status),
        root_cause=_enum_text(result.root_cause),
        confidence=float(result.confidence),
        match_method=_enum_text(result.match_method),
        requires_review=bool(result.requires_review),
        explanation=str(result.explanation),
        recommended_action=str(
            result.recommended_action
        ),
        evidence=_json_safe(result.evidence),
    )


# ---------------------------------------------------------------------------
# Engine execution
# ---------------------------------------------------------------------------

def _run_engine(
    *,
    write_outputs: bool = False,
):
    """
    Execute only the operational reconciliation engine.

    This function does not import or access the benchmark evaluator
    or ground-truth dataset.
    """

    try:
        engine = ReconciliationEngine()

        return engine.run(
            write_outputs=write_outputs
        )

    except (
        FileNotFoundError,
        ValueError,
        RuntimeError,
    ) as exc:
        logger.exception(
            "Operational reconciliation failed."
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Operational reconciliation failed. "
                "Check the source financial data."
            ),
        ) from exc


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
)
def health() -> HealthResponse:
    return HealthResponse()


# ---------------------------------------------------------------------------
# Run reconciliation
# ---------------------------------------------------------------------------

@router.post(
    "/api/v1/reconcile",
    response_model=ReconciliationRunResponse,
    tags=["reconciliation"],
)
def run_reconciliation(
    request: ReconciliationRunRequest,
) -> ReconciliationRunResponse:
    batch = _run_engine(
        write_outputs=request.persist_output
    )

    results = [
        _to_api_result(result)
        for result in batch.results
    ]

    return ReconciliationRunResponse(
        processed=len(results),
        summary=_json_safe(batch.summary),
        results=results,
    )


# ---------------------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------------------

@router.get(
    "/api/v1/summary",
    response_model=DashboardSummaryResponse,
    tags=["reconciliation"],
)
def get_summary() -> DashboardSummaryResponse:
    batch = _run_engine(
        write_outputs=False
    )

    return DashboardSummaryResponse(
        summary=_json_safe(batch.summary)
    )


# ---------------------------------------------------------------------------
# Reconciliation list
# ---------------------------------------------------------------------------

@router.get(
    "/api/v1/reconciliations",
    response_model=ReconciliationListResponse,
    tags=["reconciliation"],
)
def list_reconciliations(
    status: str | None = Query(
        default=None,
        description="Optional reconciliation status filter.",
    ),
    requires_review: bool | None = Query(
        default=None,
        description="Filter cases requiring human review.",
    ),
) -> ReconciliationListResponse:
    batch = _run_engine(
        write_outputs=False
    )

    results = [
        _to_api_result(result)
        for result in batch.results
    ]

    if status is not None:
        requested_status = status.strip().casefold()

        results = [
            result
            for result in results
            if result.status.strip().casefold()
            == requested_status
        ]

    if requires_review is not None:
        results = [
            result
            for result in results
            if result.requires_review
            is requires_review
        ]

    return ReconciliationListResponse(
        count=len(results),
        results=results,
    )


# ---------------------------------------------------------------------------
# Reconciliation detail
# ---------------------------------------------------------------------------

@router.get(
    "/api/v1/reconciliations/{invoice_id}",
    response_model=ReconciliationDetailResponse,
    tags=["reconciliation"],
)
def get_reconciliation(
    invoice_id: str,
) -> ReconciliationDetailResponse:
    requested_invoice = (
        invoice_id
        .strip()
        .casefold()
    )

    batch = _run_engine(
        write_outputs=False
    )

    for result in batch.results:
        current_invoice = (
            str(result.invoice_id)
            .strip()
            .casefold()
        )

        if current_invoice == requested_invoice:
            return ReconciliationDetailResponse(
                result=_to_api_result(result)
            )

    raise HTTPException(
        status_code=404,
        detail=(
            f"Reconciliation result for invoice "
            f"'{invoice_id}' was not found."
        ),
    )


# ============================================================
# Payment-delay predictions
# ============================================================

@router.get(
    "/api/v1/payment-delays",
    response_model=PaymentDelayListResponse,
    tags=["prediction"],
)
def get_payment_delays() -> PaymentDelayListResponse:
    """
    Predict payment timing for currently open invoices.

    Uses operational finance data only.
    Benchmark / ground-truth datasets are never accessed.
    """
    try:
        predictor = DelayPredictor()
        predictions = predictor.predict_open_invoices()

        api_predictions = [
            PaymentDelayResponse(
                **prediction.to_dict()
            )
            for prediction in predictions
        ]

        return PaymentDelayListResponse(
            as_of_date=predictor.as_of_date.isoformat(),
            count=len(api_predictions),
            predictions=api_predictions,
        )

    except (
        FileNotFoundError,
        ValueError,
        RuntimeError,
    ) as exc:
        logger.exception(
            "Payment-delay prediction failed."
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Payment-delay prediction failed. "
                "Check the operational finance data."
            ),
        ) from exc


# ============================================================
# Cashflow forecast
# ============================================================

@router.post(
    "/api/v1/cashflow/forecast",
    response_model=CashflowForecastResponse,
    tags=["cashflow"],
)
def get_cashflow_forecast(
    request: CashflowForecastRequest,
) -> CashflowForecastResponse:
    """
    Forecast operational cash position using predicted
    receivable timing and scheduled expenses.
    """
    try:
        engine = CashImpactEngine()

        result = engine.forecast(
            opening_cash_balance=request.opening_cash_balance,
            horizon_days=request.horizon_days,
        )

        return CashflowForecastResponse(
            as_of_date=result.as_of_date.isoformat(),
            horizon_end=result.horizon_end.isoformat(),
            opening_cash_balance=result.opening_cash_balance,
            total_expected_inflows=result.total_expected_inflows,
            total_scheduled_outflows=result.total_scheduled_outflows,
            projected_ending_balance=result.projected_ending_balance,
            shortfall_detected=result.shortfall_detected,
            first_shortfall_date=(
                result.first_shortfall_date.isoformat()
                if result.first_shortfall_date
                else None
            ),
            maximum_shortfall=result.maximum_shortfall,
            minimum_projected_balance=(
                result.minimum_projected_balance
            ),
            severity=result.severity,
            recommended_action=result.recommended_action,
        )

    except (
        FileNotFoundError,
        ValueError,
        RuntimeError,
    ) as exc:
        logger.exception(
            "Cashflow forecast failed."
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Cashflow forecast failed. "
                "Check the operational finance data."
            ),
        ) from exc


# ============================================================
# Payment-delay liquidity impact
# ============================================================

@router.post(
    "/api/v1/cashflow/delay-impact",
    response_model=CashDelayImpactResponse,
    tags=["cashflow"],
)
def get_cash_delay_impact(
    request: CashDelayImpactRequest,
) -> CashDelayImpactResponse:
    """
    Measure how predicted payment delays affect liquidity.

    This endpoint compares contractual payment timing against
    predicted payment timing using operational data only.
    """
    try:
        analyzer = CashDelayImpactAnalyzer()

        result = analyzer.analyze(
            opening_cash_balance=request.opening_cash_balance,
            horizon_days=request.horizon_days,
        )

        return CashDelayImpactResponse(
            **result
        )

    except (
        FileNotFoundError,
        ValueError,
        RuntimeError,
    ) as exc:
        logger.exception(
            "Cash-delay impact analysis failed."
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Cash-delay impact analysis failed. "
                "Check the operational finance data."
            ),
        ) from exc
