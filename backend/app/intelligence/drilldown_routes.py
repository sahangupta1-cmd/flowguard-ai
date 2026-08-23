from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    status,
)

from backend.app.ingestion.routes import (
    DEFAULT_IMPORT_ROOT,
    get_operational_import,
)
from backend.app.intelligence.drilldown import (
    FinancialDrilldownService,
)


router = APIRouter()


def _resolve_raw_dir(
    import_id: str | None,
) -> tuple[Path, str]:
    if import_id is None:
        return Path("data/raw"), "demo"

    # Reuse existing import validation.
    get_operational_import(import_id)

    raw_dir = (
        DEFAULT_IMPORT_ROOT
        / import_id
        / "normalized"
    )

    if not raw_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Imported operational dataset is unavailable."
            ),
        )

    return raw_dir, "uploaded_import"


@router.get(
    "/api/v1/drilldown/customer-risk",
    tags=["intelligence"],
)
def get_customer_risk_drilldown(
    as_of_date: date,
    opening_cash_balance: Decimal = Decimal("500000.00"),
    horizon_days: int = Query(
        default=90,
        ge=1,
        le=365,
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=30,
    ),
    import_id: str | None = None,
) -> dict[str, Any]:
    """
    Customer-level receivables and cashflow intelligence.

    Works against either:
    - bundled demo data
    - one isolated normalized uploaded import
    """

    raw_dir, source_type = _resolve_raw_dir(
        import_id
    )

    try:
        service = FinancialDrilldownService(
            raw_dir=raw_dir,
            as_of_date=as_of_date,
        )

        base_customers = {
            row["customer_id"]: row
            for row in service.customer_intelligence()
        }

        ranking = (
            service.rank_customers_by_cashflow_impact(
                opening_cash_balance=(
                    opening_cash_balance
                ),
                horizon_days=horizon_days,
                limit=limit,
            )
        )

        customers: list[dict[str, Any]] = []

        for impact in ranking["customers"]:
            customer_id = impact["customer_id"]

            merged = {
                **base_customers.get(
                    customer_id,
                    {},
                ),
                **impact,
            }

            customers.append(merged)

        customer_ids = [
            row["customer_id"]
            for row in customers
        ]

        combined = None

        if customer_ids:
            combined = (
                service.combined_customer_cashflow_impact(
                    customer_ids=customer_ids,
                    opening_cash_balance=(
                        opening_cash_balance
                    ),
                    horizon_days=horizon_days,
                )
            )

        return {
            "source_type": source_type,
            "import_id": import_id,
            "as_of_date": as_of_date.isoformat(),
            "ranking_basis": ranking[
                "ranking_basis"
            ],
            "customer_count_evaluated": ranking[
                "customer_count_evaluated"
            ],
            "customer_count_returned": len(
                customers
            ),
            "customers": customers,
            "combined_impact": combined,
        }

    except (
        FileNotFoundError,
        ValueError,
        RuntimeError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Customer risk intelligence could not "
                "be calculated."
            ),
        ) from exc
