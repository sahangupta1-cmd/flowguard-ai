from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class DelayPrediction:
    invoice_id: str
    customer_id: str

    invoice_amount: Decimal
    due_date: date

    expected_delay_days: int
    expected_payment_date: date

    late_probability: float
    confidence: float

    history_count: int

    prediction_basis: str

    amount_at_risk: Decimal

    def to_dict(self) -> dict[str, object]:
        return {
            "invoice_id": self.invoice_id,
            "customer_id": self.customer_id,
            "invoice_amount": format(
                self.invoice_amount,
                ".2f",
            ),
            "due_date": self.due_date.isoformat(),
            "expected_delay_days": self.expected_delay_days,
            "expected_payment_date": (
                self.expected_payment_date.isoformat()
            ),
            "late_probability": round(
                self.late_probability,
                2,
            ),
            "confidence": round(
                self.confidence,
                2,
            ),
            "history_count": self.history_count,
            "prediction_basis": self.prediction_basis,
            "amount_at_risk": format(
                self.amount_at_risk,
                ".2f",
            ),
        }