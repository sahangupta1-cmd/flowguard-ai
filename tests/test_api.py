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