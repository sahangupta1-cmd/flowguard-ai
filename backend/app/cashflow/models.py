from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class DailyCashPosition:
    date: date
    opening_balance: Decimal
    expected_inflows: Decimal
    scheduled_outflows: Decimal
    closing_balance: Decimal

    def to_dict(self) -> dict[str, object]:
        return {
            "date": self.date.isoformat(),
            "opening_balance": format(
                self.opening_balance,
                ".2f",
            ),
            "expected_inflows": format(
                self.expected_inflows,
                ".2f",
            ),
            "scheduled_outflows": format(
                self.scheduled_outflows,
                ".2f",
            ),
            "closing_balance": format(
                self.closing_balance,
                ".2f",
            ),
        }


@dataclass(frozen=True)
class CashImpactResult:
    as_of_date: date
    horizon_end: date

    opening_cash_balance: Decimal

    total_expected_inflows: Decimal
    total_scheduled_outflows: Decimal

    projected_ending_balance: Decimal

    shortfall_detected: bool
    first_shortfall_date: date | None
    maximum_shortfall: Decimal

    minimum_projected_balance: Decimal

    severity: str
    recommended_action: str

    daily_positions: list[DailyCashPosition]

    def to_dict(self) -> dict[str, object]:
        return {
            "as_of_date": self.as_of_date.isoformat(),
            "horizon_end": self.horizon_end.isoformat(),
            "opening_cash_balance": format(
                self.opening_cash_balance,
                ".2f",
            ),
            "total_expected_inflows": format(
                self.total_expected_inflows,
                ".2f",
            ),
            "total_scheduled_outflows": format(
                self.total_scheduled_outflows,
                ".2f",
            ),
            "projected_ending_balance": format(
                self.projected_ending_balance,
                ".2f",
            ),
            "shortfall_detected": (
                self.shortfall_detected
            ),
            "first_shortfall_date": (
                self.first_shortfall_date.isoformat()
                if self.first_shortfall_date
                else None
            ),
            "maximum_shortfall": format(
                self.maximum_shortfall,
                ".2f",
            ),
            "minimum_projected_balance": format(
                self.minimum_projected_balance,
                ".2f",
            ),
            "severity": self.severity,
            "recommended_action": (
                self.recommended_action
            ),
            "daily_positions": [
                position.to_dict()
                for position in self.daily_positions
            ],
        }