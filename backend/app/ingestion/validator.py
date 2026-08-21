from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from backend.app.ingestion.contracts import (
    ALLOW_BLANK_FIELDS,
    COLUMN_ALIASES,
    CONTRACTS,
    DATE_COLUMNS,
    FORBIDDEN_OPERATIONAL_COLUMNS,
    IDENTIFIER_COLUMNS,
    MONEY_COLUMNS,
)
from backend.app.reconciliation.normalizers import to_decimal


# ============================================================
# Validation report
# ============================================================

@dataclass
class CSVValidationReport:
    dataset_type: str
    filename: str
    row_count: int
    alias_mappings: dict[str, str]
    extra_columns: tuple[str, ...]


@dataclass
class HeaderValidationResult:
    dataset_type: str

    # Original source header -> canonical FlowGuard header
    column_mapping: dict[str, str]

    alias_mappings: dict[str, str]
    extra_columns: tuple[str, ...]


# ============================================================
# Header normalization
# ============================================================

def normalize_header_name(value: str) -> str:
    """
    Normalize a CSV header without guessing its meaning.

    Example:
        "Invoice Number" -> "invoice_number"
        "Payment-Date"   -> "payment_date"
    """

    value = value.replace("\ufeff", "")
    value = value.strip().lower()

    value = re.sub(
        r"[\s\-]+",
        "_",
        value,
    )

    value = re.sub(
        r"_+",
        "_",
        value,
    )

    return value.strip("_")


def validate_headers(
    dataset_type: str,
    headers: list[str],
) -> HeaderValidationResult:
    """
    Validate and map external headers to the canonical
    FlowGuard schema.

    Important:
    - Benchmark/evaluation columns are rejected.
    - Ambiguous mappings are rejected.
    - Required columns must be present.
    - Unknown extra columns are ignored but reported.
    """

    if dataset_type not in CONTRACTS:
        raise ValueError(
            f"Unknown dataset type: {dataset_type!r}"
        )

    if not headers:
        raise ValueError(
            f"{dataset_type}: CSV has no headers."
        )

    contract = CONTRACTS[dataset_type]

    required = set(
        contract.required_columns
    )

    normalized_seen: dict[str, str] = {}

    for original in headers:
        normalized = normalize_header_name(
            original
        )

        if not normalized:
            raise ValueError(
                f"{dataset_type}: blank column name detected."
            )

        if normalized in normalized_seen:
            first = normalized_seen[normalized]

            raise ValueError(
                f"{dataset_type}: duplicate columns "
                f"{first!r} and {original!r} normalize "
                f"to {normalized!r}."
            )

        normalized_seen[normalized] = original

    # --------------------------------------------------------
    # Reject benchmark / evaluation leakage
    # --------------------------------------------------------

    forbidden_found = sorted(
        normalized
        for normalized in normalized_seen
        if normalized in FORBIDDEN_OPERATIONAL_COLUMNS
    )

    if forbidden_found:
        raise ValueError(
            f"{dataset_type}: operational CSV contains "
            f"forbidden benchmark/evaluation columns: "
            f"{', '.join(forbidden_found)}"
        )

    column_mapping: dict[str, str] = {}
    alias_mappings: dict[str, str] = {}
    extra_columns: list[str] = []

    canonical_to_source: dict[str, str] = {}

    for normalized, original in normalized_seen.items():
        canonical: str | None = None

        # Exact canonical column
        if normalized in required:
            canonical = normalized

        # Known alias, but only if that target belongs
        # to this specific dataset contract.
        else:
            alias_target = COLUMN_ALIASES.get(
                normalized
            )

            if (
                alias_target is not None
                and alias_target in required
            ):
                canonical = alias_target
                alias_mappings[
                    normalized
                ] = alias_target

        # Unknown columns are retained only in the report.
        if canonical is None:
            extra_columns.append(
                normalized
            )
            continue

        # ----------------------------------------------------
        # Never silently allow two source columns to map
        # to the same FlowGuard field.
        # ----------------------------------------------------

        existing_source = canonical_to_source.get(
            canonical
        )

        if existing_source is not None:
            raise ValueError(
                f"{dataset_type}: ambiguous mapping. "
                f"Both {existing_source!r} and "
                f"{original!r} map to "
                f"{canonical!r}."
            )

        canonical_to_source[
            canonical
        ] = original

        column_mapping[
            original
        ] = canonical

    missing = sorted(
        required
        - set(canonical_to_source)
    )

    if missing:
        raise ValueError(
            f"{dataset_type}: missing required columns: "
            f"{', '.join(missing)}"
        )

    return HeaderValidationResult(
        dataset_type=dataset_type,
        column_mapping=column_mapping,
        alias_mappings=alias_mappings,
        extra_columns=tuple(
            sorted(extra_columns)
        ),
    )


# ============================================================
# Value normalization
# ============================================================

def _normalize_date(
    value: Any,
    *,
    dataset_type: str,
    column: str,
    row_number: int,
) -> str:
    """
    Accept ISO dates only.

    Examples:
        2026-08-01
        2026-08-01T12:30:00

    Ambiguous formats such as 01/02/2026 are deliberately
    rejected rather than guessed.
    """

    if value is None:
        raise ValueError(
            f"{dataset_type}: row {row_number}, "
            f"{column}: missing date."
        )

    text = str(value).strip()

    if not text:
        raise ValueError(
            f"{dataset_type}: row {row_number}, "
            f"{column}: blank date."
        )

    try:
        parsed = date.fromisoformat(
            text
        )

        return parsed.isoformat()

    except ValueError:
        pass

    try:
        parsed_datetime = datetime.fromisoformat(
            text.replace(
                "Z",
                "+00:00",
            )
        )

        return parsed_datetime.date().isoformat()

    except ValueError as exc:
        raise ValueError(
            f"{dataset_type}: row {row_number}, "
            f"{column}: unsupported or ambiguous "
            f"date {text!r}. Use ISO YYYY-MM-DD."
        ) from exc


def _normalize_integer(
    value: Any,
    *,
    dataset_type: str,
    column: str,
    row_number: int,
) -> str:
    if value is None:
        raise ValueError(
            f"{dataset_type}: row {row_number}, "
            f"{column}: missing integer value."
        )

    text = str(value).strip()

    if not text:
        raise ValueError(
            f"{dataset_type}: row {row_number}, "
            f"{column}: blank integer value."
        )

    try:
        number = int(text)

    except ValueError as exc:
        raise ValueError(
            f"{dataset_type}: row {row_number}, "
            f"{column}: invalid integer "
            f"{text!r}."
        ) from exc

    if number < 0:
        raise ValueError(
            f"{dataset_type}: row {row_number}, "
            f"{column}: negative values are "
            f"not allowed."
        )

    return str(number)


def _normalize_value(
    value: Any,
    *,
    dataset_type: str,
    column: str,
    row_number: int,
) -> str:
    # --------------------------------------------------------
    # Money
    # --------------------------------------------------------

    if column in MONEY_COLUMNS:
        try:
            amount = to_decimal(
                value,
                allow_blank=False,
            )

        except ValueError as exc:
            raise ValueError(
                f"{dataset_type}: row {row_number}, "
                f"{column}: invalid money value "
                f"{value!r}."
            ) from exc

        return format(
            amount,
            ".2f",
        )

    # --------------------------------------------------------
    # Dates
    # --------------------------------------------------------

    if column in DATE_COLUMNS:
        return _normalize_date(
            value,
            dataset_type=dataset_type,
            column=column,
            row_number=row_number,
        )

    # --------------------------------------------------------
    # Identifiers
    # --------------------------------------------------------

    if column in IDENTIFIER_COLUMNS:
        text = (
            ""
            if value is None
            else str(value).strip()
        )

        if not text:
            allowed_blank = (
                column
                in ALLOW_BLANK_FIELDS.get(
                    dataset_type,
                    frozenset(),
                )
            )

            if allowed_blank:
                return ""

            raise ValueError(
                f"{dataset_type}: row {row_number}, "
                f"{column}: blank identifier."
            )

        return text

    # --------------------------------------------------------
    # Integer business fields
    # --------------------------------------------------------

    if column == "payment_terms_days":
        return _normalize_integer(
            value,
            dataset_type=dataset_type,
            column=column,
            row_number=row_number,
        )

    # --------------------------------------------------------
    # Normal string
    # --------------------------------------------------------

    if value is None:
        return ""

    return str(value).strip()


# ============================================================
# Row normalization
# ============================================================

def normalize_row(
    dataset_type: str,
    row: dict[str, Any],
    header_result: HeaderValidationResult,
    *,
    row_number: int,
) -> dict[str, str]:
    contract = CONTRACTS[
        dataset_type
    ]

    # canonical column -> source column
    source_for: dict[str, str] = {
        canonical: source
        for source, canonical
        in header_result.column_mapping.items()
    }

    normalized: dict[str, str] = {}

    for canonical in contract.required_columns:
        source_column = source_for[
            canonical
        ]

        value = row.get(
            source_column
        )

        normalized[
            canonical
        ] = _normalize_value(
            value,
            dataset_type=dataset_type,
            column=canonical,
            row_number=row_number,
        )

    return normalized


# ============================================================
# CSV reader / validator
# ============================================================

def read_and_normalize_csv(
    dataset_type: str,
    path: str | Path,
) -> tuple[
    CSVValidationReport,
    list[dict[str, str]],
]:
    """
    Read and validate a CSV without modifying the source file.
    """

    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"CSV not found: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Not a file: {path}"
        )

    rows: list[dict[str, str]] = []

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(
            handle
        )

        if reader.fieldnames is None:
            raise ValueError(
                f"{dataset_type}: CSV contains no header row."
            )

        header_result = validate_headers(
            dataset_type,
            list(reader.fieldnames),
        )

        for row_number, row in enumerate(
            reader,
            start=2,
        ):
            normalized = normalize_row(
                dataset_type,
                row,
                header_result,
                row_number=row_number,
            )

            rows.append(
                normalized
            )

    report = CSVValidationReport(
        dataset_type=dataset_type,
        filename=path.name,
        row_count=len(rows),
        alias_mappings=dict(
            header_result.alias_mappings
        ),
        extra_columns=header_result.extra_columns,
    )

    return report, rows


def validate_csv_file(
    dataset_type: str,
    path: str | Path,
) -> CSVValidationReport:
    report, _ = read_and_normalize_csv(
        dataset_type,
        path,
    )

    return report
