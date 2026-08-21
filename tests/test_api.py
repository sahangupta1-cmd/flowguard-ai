from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


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


def assert_no_benchmark_fields(value: Any) -> None:
    """
    Recursively verify that operational API responses
    never expose benchmark or ground-truth information.
    """

    if isinstance(value, dict):
        for key, item in value.items():
            assert (
                str(key).strip().lower()
                not in FORBIDDEN_BENCHMARK_KEYS
            )

            assert_no_benchmark_fields(item)

    elif isinstance(value, list):
        for item in value:
            assert_no_benchmark_fields(item)


def test_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "ok"
    assert payload["service"] == "flowguard-api"
    assert payload["version"] == "1.0.0"


def test_summary_endpoint() -> None:
    response = client.get("/api/v1/summary")

    assert response.status_code == 200

    payload = response.json()

    assert "summary" in payload
    assert isinstance(payload["summary"], dict)

    assert_no_benchmark_fields(payload)


def test_reconciliation_list_endpoint() -> None:
    response = client.get(
        "/api/v1/reconciliations"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["count"] == len(
        payload["results"]
    )

    assert payload["count"] > 0

    assert_no_benchmark_fields(payload)


def test_reconciliation_detail_endpoint() -> None:
    list_response = client.get(
        "/api/v1/reconciliations"
    )

    assert list_response.status_code == 200

    results = list_response.json()["results"]

    assert results

    invoice_id = results[0]["invoice_id"]

    response = client.get(
        f"/api/v1/reconciliations/{invoice_id}"
    )

    assert response.status_code == 200

    payload = response.json()

    assert (
        payload["result"]["invoice_id"]
        == invoice_id
    )

    assert_no_benchmark_fields(payload)


def test_unknown_invoice_returns_404() -> None:
    response = client.get(
        "/api/v1/reconciliations/"
        "THIS-INVOICE-DOES-NOT-EXIST"
    )

    assert response.status_code == 404


def test_requires_review_filter() -> None:
    response = client.get(
        "/api/v1/reconciliations",
        params={
            "requires_review": "true",
        },
    )

    assert response.status_code == 200

    payload = response.json()

    for result in payload["results"]:
        assert result["requires_review"] is True

    assert_no_benchmark_fields(payload)


def test_money_is_serialized_as_decimal_string() -> None:
    response = client.get(
        "/api/v1/reconciliations"
    )

    assert response.status_code == 200

    results = response.json()["results"]

    assert results

    result = results[0]

    money_fields = (
        "invoice_amount",
        "payment_amount",
        "expected_settlement",
        "actual_bank_amount",
        "difference",
    )

    for field in money_fields:
        assert isinstance(
            result[field],
            str,
        )

        assert "." in result[field]

        decimals = result[field].split(".")[1]

        assert len(decimals) == 2


def test_reconciliation_run_without_persistence() -> None:
    response = client.post(
        "/api/v1/reconcile",
        json={
            "persist_output": False,
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["processed"] == len(
        payload["results"]
    )

    assert payload["processed"] > 0

    assert isinstance(
        payload["summary"],
        dict,
    )

    assert_no_benchmark_fields(payload)

# ============================================================
# Operational intelligence API tests
# ============================================================

def test_payment_delay_endpoint() -> None:
    response = client.get(
        "/api/v1/payment-delays"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["as_of_date"] == "2026-08-01"
    assert payload["count"] > 0
    assert payload["count"] == len(
        payload["predictions"]
    )

    prediction = payload["predictions"][0]

    required_fields = {
        "invoice_id",
        "customer_id",
        "invoice_amount",
        "due_date",
        "expected_delay_days",
        "expected_payment_date",
        "late_probability",
        "confidence",
        "history_count",
        "prediction_basis",
        "amount_at_risk",
    }

    assert required_fields.issubset(
        prediction.keys()
    )

    assert 0.0 <= prediction["late_probability"] <= 100.0
    assert 0.0 <= prediction["confidence"] <= 100.0


def test_cashflow_forecast_endpoint() -> None:
    response = client.post(
        "/api/v1/cashflow/forecast",
        json={
            "opening_cash_balance": "500000.00",
            "horizon_days": 90,
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["as_of_date"] == "2026-08-01"
    assert payload["horizon_end"] == "2026-10-30"

    assert "total_expected_inflows" in payload
    assert "total_scheduled_outflows" in payload
    assert "projected_ending_balance" in payload
    assert "shortfall_detected" in payload
    assert "severity" in payload
    assert "recommended_action" in payload

    # Financial values must remain decimal strings.
    assert isinstance(
        payload["opening_cash_balance"],
        str,
    )

    assert isinstance(
        payload["projected_ending_balance"],
        str,
    )


def test_cash_delay_impact_endpoint() -> None:
    response = client.post(
        "/api/v1/cashflow/delay-impact",
        json={
            "opening_cash_balance": "500000.00",
            "horizon_days": 90,
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["as_of_date"] == "2026-08-01"
    assert payload["horizon_end"] == "2026-10-30"

    impact = payload["delay_impact"]

    assert (
        float(
            impact["maximum_temporary_cash_gap"]
        )
        >= 0.0
    )

    assert (
        impact["days_with_reduced_liquidity"]
        >= 0
    )

    assert impact["severity"] in {
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    }


def test_cashflow_request_validation() -> None:
    response = client.post(
        "/api/v1/cashflow/forecast",
        json={
            "opening_cash_balance": "500000.00",
            "horizon_days": 0,
        },
    )

    assert response.status_code == 422


# ============================================================
# CFO Intelligence API
# ============================================================

def test_cfo_intelligence_overview_endpoint() -> None:
    response = client.get(
        "/api/v1/intelligence/overview",
        params={
            "opening_cash_balance": "500000.00",
            "horizon_days": 90,
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["as_of_date"] == "2026-08-01"

    assert "reconciliation" in payload
    assert "receivables" in payload
    assert "cashflow" in payload
    assert "liquidity_risk" in payload
    assert "priorities" in payload

    assert (
        payload["reconciliation"]["cases_processed"]
        == 100
    )

    assert (
        payload["reconciliation"]["requires_review_count"]
        >= 0
    )

    assert payload["receivables"]["open_invoices"] > 0

    assert (
        payload["receivables"]["high_risk_invoices"]
        <= payload["receivables"]["open_invoices"]
    )

    assert isinstance(
        payload["cashflow"]["projected_ending_balance"],
        str,
    )

    assert isinstance(
        payload["liquidity_risk"][
            "maximum_temporary_cash_gap"
        ],
        str,
    )

    assert isinstance(payload["priorities"], list)


def test_cfo_intelligence_invalid_horizon() -> None:
    response = client.get(
        "/api/v1/intelligence/overview",
        params={
            "opening_cash_balance": "500000.00",
            "horizon_days": 0,
        },
    )

    assert response.status_code == 422


def test_cfo_intelligence_rejects_negative_cash() -> None:
    response = client.get(
        "/api/v1/intelligence/overview",
        params={
            "opening_cash_balance": "-1.00",
            "horizon_days": 90,
        },
    )

    assert response.status_code == 422


def test_cfo_intelligence_has_no_benchmark_fields() -> None:
    response = client.get(
        "/api/v1/intelligence/overview"
    )

    assert response.status_code == 200

    payload_text = str(response.json()).lower()

    forbidden = [
        "ground_truth",
        "benchmark_id",
        "stress_id",
        "case_id",
        "true_status",
        "true_root_cause",
        "expected_status",
        "expected_root_cause",
        "should_auto_resolve",
    ]

    for key in forbidden:
        assert key not in payload_text
