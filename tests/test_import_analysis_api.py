from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.app.ingestion.routes as ingestion_routes

from backend.app.ingestion.contracts import CONTRACTS
from backend.app.main import app


RAW_PATH = Path("data/raw")

client = TestClient(app)


def _uploads(
    *,
    include_optional: bool,
) -> dict:
    files = {}

    for dataset_type, contract in CONTRACTS.items():
        if contract.optional and not include_optional:
            continue

        source = RAW_PATH / contract.filename

        files[dataset_type] = (
            contract.filename,
            source.read_bytes(),
            "text/csv",
        )

    return files


def _create_import(
    *,
    include_optional: bool,
) -> dict:
    response = client.post(
        "/api/v1/imports",
        files=_uploads(
            include_optional=include_optional
        ),
    )

    assert response.status_code == 201

    return response.json()


def test_full_import_can_be_analyzed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ingestion_routes,
        "DEFAULT_IMPORT_ROOT",
        tmp_path / "imports",
    )

    imported = _create_import(
        include_optional=True
    )

    response = client.post(
        (
            f"/api/v1/imports/"
            f"{imported['import_id']}/analyze"
        ),
        json={
            "as_of_date": "2026-08-01",
            "opening_cash_balance": "500000.00",
            "horizon_days": 90,
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert (
        payload["import_id"]
        == imported["import_id"]
    )

    assert (
        payload["fingerprint"]
        == imported["fingerprint"]
    )

    analysis = payload["analysis"]

    assert analysis["as_of_date"] == "2026-08-01"

    assert (
        analysis["reconciliation"]["cases_processed"]
        == 100
    )

    assert (
        analysis["receivables"]["open_invoices"]
        == 44
    )

    assert (
        analysis["receivables"]["high_risk_invoices"]
        == 36
    )

    assert (
        analysis["cashflow"][
            "projected_ending_balance"
        ]
        == "3674900.00"
    )


def test_required_only_import_can_be_analyzed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ingestion_routes,
        "DEFAULT_IMPORT_ROOT",
        tmp_path / "imports",
    )

    imported = _create_import(
        include_optional=False
    )

    assert len(
        imported["datasets"]
    ) == 6

    response = client.post(
        (
            f"/api/v1/imports/"
            f"{imported['import_id']}/analyze"
        ),
        json={
            "as_of_date": "2026-08-01",
            "opening_cash_balance": "500000.00",
            "horizon_days": 90,
        },
    )

    assert response.status_code == 200

    analysis = response.json()[
        "analysis"
    ]

    assert (
        analysis["reconciliation"]["cases_processed"]
        == 100
    )

    assert (
        analysis["receivables"]["open_invoices"]
        == 44
    )


def test_import_analysis_validates_parameters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ingestion_routes,
        "DEFAULT_IMPORT_ROOT",
        tmp_path / "imports",
    )

    imported = _create_import(
        include_optional=True
    )

    response = client.post(
        (
            f"/api/v1/imports/"
            f"{imported['import_id']}/analyze"
        ),
        json={
            "as_of_date": "2026-08-01",
            "opening_cash_balance": "-1.00",
            "horizon_days": 0,
        },
    )

    assert response.status_code == 422


def test_unknown_import_cannot_be_analyzed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ingestion_routes,
        "DEFAULT_IMPORT_ROOT",
        tmp_path / "imports",
    )

    response = client.post(
        "/api/v1/imports/imp_000000000000/analyze",
        json={
            "as_of_date": "2026-08-01",
            "opening_cash_balance": "500000.00",
            "horizon_days": 90,
        },
    )

    assert response.status_code == 404
