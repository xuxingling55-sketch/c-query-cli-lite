"""Render and validate fixed review SQL templates."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from executor import validate_sql

from .models import ReviewRequest


_UNRESOLVED_TOKEN = re.compile(r"\{\{[^{}]*\}\}")


class NotApplicableError(Exception):
    """Raised when a template requires an unavailable optional source."""


def _format_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _format_target(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def render_sql(path: str | Path, request: ReviewRequest) -> str:
    """Substitute allowlisted parameters and return safety-checked SQL."""
    sql = Path(path).read_text(encoding="utf-8")
    values = {
        "CURRENT_START": _format_date(request.start),
        "CURRENT_END": _format_date(request.end),
        "LAST_YEAR_START": _format_date(request.last_year_start),
        "LAST_YEAR_END": _format_date(request.last_year_end),
        "TARGET": _format_target(request.target_amount),
    }

    optional_windows = (
        (
            "DEPOSIT_SOURCE",
            "定金策略来源日期",
            request.deposit_source_start,
            request.deposit_source_end,
        ),
        (
            "RESERVOIR_SOURCE",
            "蓄水策略来源日期",
            request.reservoir_source_start,
            request.reservoir_source_end,
        ),
    )
    for prefix, label, start, end in optional_windows:
        referenced = f"{{{{{prefix}_START}}}}" in sql or f"{{{{{prefix}_END}}}}" in sql
        if referenced and (start is None or end is None):
            raise NotApplicableError(f"缺少{label}，该查询不适用")
        if start is not None and end is not None:
            values[f"{prefix}_START"] = _format_date(start)
            values[f"{prefix}_END"] = _format_date(end)

    for token, value in values.items():
        sql = sql.replace(f"{{{{{token}}}}}", value)

    unresolved = _UNRESOLVED_TOKEN.findall(sql)
    if unresolved or "{{" in sql or "}}" in sql:
        detail = ", ".join(unresolved) if unresolved else "存在不完整模板标记"
        raise ValueError(f"未解析模板参数: {detail}")

    ok, message, normalized_sql = validate_sql(sql, max_limit=10000)
    if not ok:
        raise ValueError(f"SQL 安全检查失败: {message}")
    return normalized_sql
