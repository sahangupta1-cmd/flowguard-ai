from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from backend.app.ingestion.contracts import CONTRACTS
from backend.app.ingestion.service import CSVImportService
from backend.app.ingestion.validator import (
    normalize_row,
    validate_csv_file,
    validate_headers,
)


RAW_PATH = Path("data/raw")


def _operational_files() -> dict[str, Path]:
    return {
        dataset_type: RAW_PATH / contract.filename
        for dataset_type, contract in CONTRACTS.items()
    }


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def test_all_demo_operational_csvs_validate() -> None:
    expected_rows = {
        "customers": 20,
        "invoices": 100,
        "payments": 100,
        "settlements": 100,
        "bank_transactions": 96,
        "expenses": 40,
        "refunds": 8,
        "chargebacks": 5,
    }

    for dataset_type, contract in CONTRACTS.items():
        report = validate_csv_file(
            dataset_type,
            RAW_PATH / contract.filename,
        )

        assert (
            report.row_count
            == expected_rows[dataset_type]
        )

        assert report.alias_mappings == {}
        assert report.extra_columns == ()


def test_external_payment_aliases_map_safely() -> None:
    headers = [
        "Payment No",
        "Invoice Number",
        "Client ID",
        "Paid Amount",
        "Payment Date",
        "Method",
        "Payment State",
        "Payment Reference",
    ]

    result = validate_headers(
        "payments",
        headers,
    )

    assert result.column_mapping[
        "Payment No"
    ] == "payment_id"

    assert result.column_mapping[
        "Invoice Number"
    ] == "invoice_id"

    assert result.column_mapping[
        "Client ID"
    ] == "customer_id"

    assert result.column_mapping[
        "Paid Amount"
    ] == "amount"

    assert result.column_mapping[
        "Payment Reference"
    ] == "reference"

    assert result.extra_columns == ()


def test_benchmark_columns_are_rejected() -> None:
    headers = [
        "invoice_id",
        "customer_id",
        "customer_name",
        "invoice_amount",
        "issue_date",
        "due_date",
        "payment_policy",
        "currency",
        "scenario",
        "expected_status",
    ]

    with pytest.raises(
        ValueError,
        match="forbidden benchmark/evaluation",
    ):
        validate_headers(
            "invoices",
            headers,
        )


def test_blank_linkage_allowed_but_primary_id_required() -> None:
    headers = [
        "payment_id",
        "invoice_id",
        "customer_id",
        "amount",
        "payment_date",
        "payment_method",
        "payment_status",
        "reference",
    ]

    header_result = validate_headers(
        "payments",
        headers,
    )

    row = {
        "payment_id": "PAY_TEST_1",
        "invoice_id": "",
        "customer_id": "CUS_TEST",
        "amount": "1000.00",
        "payment_date": "2026-08-01",
        "payment_method": "UPI",
        "payment_status": "SUCCESS",
        "reference": "TEST123",
    }

    normalized = normalize_row(
        "payments",
        row,
        header_result,
        row_number=2,
    )

    assert normalized["invoice_id"] == ""
    assert normalized["payment_id"] == "PAY_TEST_1"
    assert normalized["amount"] == "1000.00"

    row["payment_id"] = ""

    with pytest.raises(
        ValueError,
        match="blank identifier",
    ):
        normalize_row(
            "payments",
            row,
            header_result,
            row_number=2,
        )


def test_import_is_isolated_and_reproducible(
    tmp_path: Path,
) -> None:
    files = _operational_files()

    demo_invoice_hash_before = _file_sha256(
        RAW_PATH / "invoices.csv"
    )

    service = CSVImportService(
        import_root=tmp_path / "imports"
    )

    first = service.create_import(
        files
    )

    second = service.create_import(
        files
    )

    assert first.total_rows == 469
    assert second.total_rows == 469

    assert (
        first.fingerprint
        == second.fingerprint
    )

    assert (
        first.import_id
        != second.import_id
    )

    first_normalized = Path(
        first.normalized_path
    )

    assert (
        len(
            list(
                first_normalized.glob(
                    "*.csv"
                )
            )
        )
        == 8
    )

    assert Path(
        first.manifest_path
    ).exists()

    demo_invoice_hash_after = _file_sha256(
        RAW_PATH / "invoices.csv"
    )

    assert (
        demo_invoice_hash_before
        == demo_invoice_hash_after
    )


def test_missing_required_dataset_is_rejected(
    tmp_path: Path,
) -> None:
    files = _operational_files()

    files.pop(
        "payments"
    )

    service = CSVImportService(
        import_root=tmp_path / "imports"
    )

    with pytest.raises(
        ValueError,
        match="Missing required operational datasets",
    ):
        service.create_import(
            files
        )
