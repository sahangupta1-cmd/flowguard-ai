from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Any

import pandas as pd


# ============================================================
# MONEY CONFIGURATION
# ============================================================

MONEY_PLACES = Decimal("0.01")


# ============================================================
# MONEY NORMALIZATION
# ============================================================


def to_decimal(
    value: Any,
    *,
    allow_blank: bool = False,
) -> Decimal | None:
    """
    Convert a raw financial value into Decimal.

    Invalid monetary values are never silently converted
    to zero.

    Blank values may return None only when allow_blank=True.
    """

    if value is None:
        if allow_blank:
            return None

        raise ValueError(
            "Financial amount cannot be None."
        )

    try:
        if pd.isna(value):
            if allow_blank:
                return None

            raise ValueError(
                "Financial amount cannot be NaN."
            )

    except TypeError:
        pass

    text = str(value).strip()

    if not text:
        if allow_blank:
            return None

        raise ValueError(
            "Financial amount cannot be blank."
        )

    text = (
        text
        .replace("₹", "")
        .replace(",", "")
        .strip()
    )

    try:
        amount = Decimal(text)

    except (InvalidOperation, ValueError) as exc:
        raise ValueError(
            f"Invalid financial amount: {value!r}"
        ) from exc

    return amount.quantize(
        MONEY_PLACES,
        rounding=ROUND_HALF_UP,
    )


def money_equal(
    first: Any,
    second: Any,
    tolerance: Decimal = Decimal("0.01"),
) -> bool:
    """
    Compare two valid financial amounts.

    Invalid values raise an error instead of being
    silently interpreted as zero.
    """

    first_amount = to_decimal(first)
    second_amount = to_decimal(second)

    return (
        abs(first_amount - second_amount)
        <= tolerance
    )


def money_difference(
    expected: Any,
    actual: Any,
) -> Decimal:
    """
    Calculate expected - actual using Decimal arithmetic.
    """

    expected_amount = to_decimal(expected)
    actual_amount = to_decimal(actual)

    return (
        expected_amount
        - actual_amount
    ).quantize(
        MONEY_PLACES,
        rounding=ROUND_HALF_UP,
    )


# ============================================================
# TEXT NORMALIZATION
# ============================================================


def normalize_text(value: Any) -> str:
    """
    General-purpose normalization for financial references.
    """

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    text = str(value).upper().strip()

    text = re.sub(
        r"[^A-Z0-9]+",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# COMPANY NAME NORMALIZATION
# ============================================================


COMPANY_REPLACEMENTS = {
    "PRIVATE LIMITED": "",
    "PVT LTD": "",
    "PVT": "",
    "LIMITED": "",
    "LTD": "",
    "LLP": "",
    "TECHNOLOGIES": "TECH",
    "TECHNOLOGY": "TECH",
    "SERVICES": "SRVCS",
    "SOLUTIONS": "SOLNS",
    "RETAIL": "RTL",
}


def normalize_company_name(
    value: Any,
) -> str:
    """
    Normalize company names commonly seen across
    invoices, gateway reports and bank descriptions.

    Example:
        Nova Technologies Pvt Ltd
        -> NOVA TECH
    """

    text = normalize_text(value)

    for old, new in COMPANY_REPLACEMENTS.items():

        pattern = (
            r"\b"
            + re.escape(old)
            + r"\b"
        )

        text = re.sub(
            pattern,
            new,
            text,
        )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


# ============================================================
# ID NORMALIZATION
# ============================================================


def normalize_id(value: Any) -> str:
    """
    Normalize identifiers while retaining letters
    and numbers.
    """

    text = normalize_text(value)

    return text.replace(
        " ",
        "",
    )


# ============================================================
# REFERENCE NORMALIZATION
# ============================================================


def normalize_reference(
    value: Any,
) -> str:
    """
    Normalize payment, settlement and bank references.
    """

    return normalize_text(value)


# ============================================================
# DATE NORMALIZATION
# ============================================================


def parse_date(
    value: Any,
) -> datetime | None:
    """
    Convert CSV date values into datetime objects.

    Invalid values return None rather than raising.
    """

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    parsed = pd.to_datetime(
        value,
        errors="coerce",
    )

    if pd.isna(parsed):
        return None

    return parsed.to_pydatetime()


def date_distance_days(
    first: Any,
    second: Any,
) -> int | None:
    """
    Return absolute distance between two dates.
    """

    first_date = parse_date(first)
    second_date = parse_date(second)

    if (
        first_date is None
        or second_date is None
    ):
        return None

    return abs(
        (
            first_date
            - second_date
        ).days
    )


def signed_date_difference_days(
    earlier: Any,
    later: Any,
) -> int | None:
    """
    Return later - earlier in days.

    Useful for settlement-delay detection.
    """

    earlier_date = parse_date(
        earlier
    )

    later_date = parse_date(
        later
    )

    if (
        earlier_date is None
        or later_date is None
    ):
        return None

    return (
        later_date
        - earlier_date
    ).days


# ============================================================
# EMPTY VALUE HELPER
# ============================================================


def is_blank(value: Any) -> bool:
    """
    Safely determine whether a CSV field is empty.
    """

    if value is None:
        return True

    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass

    return str(value).strip() == ""