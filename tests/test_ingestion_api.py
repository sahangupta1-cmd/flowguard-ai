from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.app.ingestion.routes as ingestion_routes

from backend.app.ingestion.contracts import CONTRACTS
from backend.app.main import app


RAW_PATH = Path("data/raw")

client = TestClient(app)


def _valid_uploads() -> dict:
    uploads = {}

    for dataset_type, contract in CONTRACTS.items():
        path = RAW_PATH / contract.filename

        uploads[dataset_type] = (
            contract.filename,
            path.read_bytes(),
            "text/csv",
        )

    return uploads


def _invoice_with_benchmark_column() -> bytes:
    source = RAW_PATH / "invoices.csv"

    with source.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)

        fieldnames = list(
            reader.fieldnames or []
        )

        rows = list(reader)

    fieldnames.append(
        "scenario"
    )

    output = io.StringIO(
        newline=""
    )

    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames,
        lineterminator="\n",
    )

    writer.writeheader()

    for row in rows:
        row["scenario"] = "SHOULD_NOT_ENTER_PIPELINE"
        writer.writerow(row)

    return output.getvalue().encode(
        "utf-8"
    )


def test_upload_api_creates_isolated_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import_root = (
        tmp_path
        / "imports"
    )

    monkeypatch.setattr(
        ingestion_routes,
        "DEFAULT_IMPORT_ROOT",
        import_root,
    )

    response = client.post(
        "/api/v1/imports",
        files=_valid_uploads(),
    )

    assert response.status_code == 201

    payload = response.json()

    assert payload["total_rows"] == 469
    assert len(payload["datasets"]) == 8

    assert payload["import_id"].startswith(
        "imp_"
    )

    assert len(
        payload["fingerprint"]
    ) == 64

    assert (
        payload["safety"][
            "demo_dataset_modified"
        ]
        is False
    )

    assert (
        payload["safety"][
            "benchmark_fields_allowed"
        ]
        is False
    )

    assert (
        payload["safety"][
            "invalid_money_coerced_to_zero"
        ]
        is False
    )

    assert (
        import_root
        / payload["import_id"]
        / "manifest.json"
    ).is_file()


def test_uploaded_import_can_be_retrieved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ingestion_routes,
        "DEFAULT_IMPORT_ROOT",
        tmp_path / "imports",
    )

    created = client.post(
        "/api/v1/imports",
        files=_valid_uploads(),
    )

    assert created.status_code == 201

    created_payload = created.json()

    import_id = created_payload[
        "import_id"
    ]

    response = client.get(
        f"/api/v1/imports/{import_id}"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["import_id"] == import_id

    assert (
        payload["fingerprint"]
        == created_payload["fingerprint"]
    )


def test_import_api_does_not_expose_internal_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ingestion_routes,
        "DEFAULT_IMPORT_ROOT",
        tmp_path / "imports",
    )

    response = client.post(
        "/api/v1/imports",
        files=_valid_uploads(),
    )

    assert response.status_code == 201

    payload = response.json()

    forbidden = {
        "import_path",
        "normalized_path",
        "manifest_path",
    }

    assert forbidden.isdisjoint(
        payload.keys()
    )


def test_import_api_rejects_benchmark_columns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ingestion_routes,
        "DEFAULT_IMPORT_ROOT",
        tmp_path / "imports",
    )

    files = _valid_uploads()

    files["invoices"] = (
        "invoices.csv",
        _invoice_with_benchmark_column(),
        "text/csv",
    )

    response = client.post(
        "/api/v1/imports",
        files=files,
    )

    assert response.status_code == 422

    assert (
        "forbidden benchmark/evaluation"
        in response.json()["detail"]
    )


def test_import_lookup_rejects_invalid_id() -> None:
    response = client.get(
        "/api/v1/imports/not-a-valid-import"
    )

    assert response.status_code == 404
