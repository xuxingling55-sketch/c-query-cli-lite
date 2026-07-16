"""Pair current and last-year long-format review results."""

from collections.abc import Mapping, Sequence
from math import isfinite
from numbers import Number
from typing import Any

import pandas as pd

from .models import ReviewRequest


_PAIR_KEY_FIELDS = (
    "channel",
    "dimension_type",
    "dimension_value",
    "metric",
    "source_version",
    "definition_id",
)
_PERIODS = ("本期", "去年同期")


def _numeric(value: Any) -> bool:
    return isinstance(value, Number) and not isinstance(value, bool)


def _finite_numeric(value: Any) -> bool:
    if not _numeric(value):
        return False
    own_check = getattr(value, "is_finite", None)
    if callable(own_check):
        return bool(own_check())
    try:
        return isfinite(value)
    except OverflowError:
        return True
    except TypeError:
        return False


def _none_if_missing(value: Any) -> Any:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    if _numeric(value) and not _finite_numeric(value):
        return None
    return value


def _date_range(start: Any, end: Any) -> str:
    return f"{start.isoformat()}/{end.isoformat()}"


def pair_periods(
    rows: Sequence[Mapping[str, Any]], request: ReviewRequest
) -> list[dict[str, Any]]:
    """Pair long-format current and last-year rows by their full metric key."""
    grouped: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = {}

    for source_row in rows:
        normalized = {
            field: _none_if_missing(value) for field, value in source_row.items()
        }
        period = normalized.get("period")
        if period not in _PERIODS:
            raise ValueError(f"未知周期数据: {period}")

        key = tuple(normalized.get(field) for field in _PAIR_KEY_FIELDS)
        periods = grouped.setdefault(key, {})
        if period in periods:
            raise ValueError(f"重复周期数据: {period}, key={key}")
        periods[period] = normalized

    result: list[dict[str, Any]] = []
    current_range = _date_range(request.start, request.end)
    last_year_range = _date_range(request.last_year_start, request.last_year_end)

    for key, periods in grouped.items():
        current = periods.get("本期")
        last_year = periods.get("去年同期")
        current_value = current.get("value") if current is not None else None
        last_year_value = last_year.get("value") if last_year is not None else None

        absolute_change = None
        relative_change = None
        if _finite_numeric(current_value) and _finite_numeric(last_year_value):
            absolute_candidate = current_value - last_year_value
            if _finite_numeric(absolute_candidate):
                absolute_change = absolute_candidate
                if last_year_value != 0:
                    relative_candidate = absolute_candidate / last_year_value
                    if _finite_numeric(relative_candidate):
                        relative_change = relative_candidate

        if current is None:
            period_status = "missing_current"
        elif last_year is None:
            period_status = "missing_last_year"
        else:
            period_status = "complete"

        current_updated_at = current.get("data_updated_at") if current is not None else None
        last_year_updated_at = (
            last_year.get("data_updated_at") if last_year is not None else None
        )
        data_updated_at = (
            current_updated_at
            if current_updated_at is not None
            else last_year_updated_at
        )

        paired = dict(zip(_PAIR_KEY_FIELDS, key, strict=True))
        paired.update(
            {
                "current_value": current_value,
                "last_year_value": last_year_value,
                "absolute_change": absolute_change,
                "relative_change": relative_change,
                "period_status": period_status,
                "current_date_range": current_range,
                "last_year_date_range": last_year_range,
                "data_updated_at": data_updated_at,
            }
        )
        result.append(paired)

    return result
