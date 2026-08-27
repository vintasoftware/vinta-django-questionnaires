"""Reading answer values, which arrive as JSON.

A date is an ISO string, a file is an object with a size and a content type, a
range is an object with a start and an end.  These helpers return ``None`` when
a value is not what the validator expected, which the validators report as
``invalid_type`` -- the same case Zod's base type catches in the browser.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
from typing import Any


def as_text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    return None


def as_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal | str):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    return None


def as_sequence(value: Any) -> list[Any] | None:
    if isinstance(value, list | tuple):
        return list(value)
    return None


def as_temporal(value: Any) -> dt.datetime | dt.date | dt.time | None:
    """Parse an ISO string, or pass a date/time object through."""
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value
    if not isinstance(value, str):
        return None
    for parse in (dt.datetime.fromisoformat, dt.date.fromisoformat, dt.time.fromisoformat):
        try:
            return parse(value)
        except ValueError:
            continue
    return None


def comparable_temporals(left: Any, right: Any) -> tuple[Any, Any] | None:
    """Normalise two temporals so ``<`` means something, or ``None``."""
    if left is None or right is None:
        return None
    left_is_datetime = isinstance(left, dt.datetime)
    right_is_datetime = isinstance(right, dt.datetime)
    if left_is_datetime != right_is_datetime:
        # A bare date compares against a datetime as that day's midnight.
        if left_is_datetime and isinstance(right, dt.date):
            right = dt.datetime.combine(right, dt.time.min, tzinfo=left.tzinfo)
        elif right_is_datetime and isinstance(left, dt.date):
            left = dt.datetime.combine(left, dt.time.min, tzinfo=right.tzinfo)
        else:
            return None
    if isinstance(left, dt.datetime) and isinstance(right, dt.datetime):
        if (left.tzinfo is None) != (right.tzinfo is None):
            return None
    elif type(left) is not type(right):
        return None
    return left, right


def as_range(value: Any) -> tuple[Any, Any] | None:
    """Read a ``{"start": ..., "end": ...}`` answer."""
    if not isinstance(value, dict):
        return None
    if "start" not in value and "end" not in value:
        return None
    return value.get("start"), value.get("end")


def as_files(value: Any) -> list[dict[str, Any]] | None:
    """Read a file answer, single or multiple, as a list of file objects."""
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return list(value)
    return None
