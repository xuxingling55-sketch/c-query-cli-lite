"""Input and result models shared by review-pack modules."""

from dataclasses import dataclass, field
from datetime import date
from math import isfinite
from typing import Any


def parse_target(value: str | int | float) -> float:
    """Parse a positive target amount, including Chinese 万/亿 units."""
    text = str(value).strip()
    multiplier = 1
    if text.endswith("亿"):
        text = text[:-1].strip()
        multiplier = 100_000_000
    elif text.endswith("万"):
        text = text[:-1].strip()
        multiplier = 10_000

    try:
        amount = float(text) * multiplier
    except ValueError as exc:
        raise ValueError("目标金额格式不正确") from exc
    if not isfinite(amount):
        raise ValueError("目标金额必须是有限正数")
    if amount <= 0:
        raise ValueError("目标金额必须大于零")
    return amount


def _parse_optional_window(
    label: str,
    start: str | date | None,
    end: str | date | None,
) -> tuple[date | None, date | None]:
    if (start is None) != (end is None):
        raise ValueError(f"{label}策略来源日期必须同时提供开始和结束日期")
    if start is None:
        return None, None
    parsed_start = _parse_date(start)
    parsed_end = _parse_date(end)
    if parsed_end < parsed_start:
        raise ValueError(f"{label}策略来源截止日期不能早于开始日期")
    return parsed_start, parsed_end


def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


@dataclass(frozen=True)
class ReviewRequest:
    name: str
    start: date
    end: date
    last_year_start: date
    last_year_end: date
    target_amount: float
    deposit_source_start: date | None = None
    deposit_source_end: date | None = None
    reservoir_source_start: date | None = None
    reservoir_source_end: date | None = None

    @property
    def period_days(self) -> int:
        return (self.end - self.start).days + 1

    @classmethod
    def create(
        cls,
        name: str,
        start: str | date,
        end: str | date,
        target_amount: str | int | float,
        *,
        deposit_source_start: str | date | None = None,
        deposit_source_end: str | date | None = None,
        reservoir_source_start: str | date | None = None,
        reservoir_source_end: str | date | None = None,
    ) -> "ReviewRequest":
        parsed_start = _parse_date(start)
        parsed_end = _parse_date(end)
        if parsed_end < parsed_start:
            raise ValueError("截止日期不能早于开始日期")

        try:
            last_year_start = parsed_start.replace(year=parsed_start.year - 1)
            last_year_end = parsed_end.replace(year=parsed_end.year - 1)
        except ValueError as exc:
            raise ValueError("去年同期无法保持相同月日") from exc
        if (last_year_end - last_year_start) != (parsed_end - parsed_start):
            raise ValueError("去年同期无法同时保持相同月日和天数")

        parsed_deposit_start, parsed_deposit_end = _parse_optional_window(
            "定金", deposit_source_start, deposit_source_end
        )
        parsed_reservoir_start, parsed_reservoir_end = _parse_optional_window(
            "蓄水", reservoir_source_start, reservoir_source_end
        )

        return cls(
            name=name,
            start=parsed_start,
            end=parsed_end,
            last_year_start=last_year_start,
            last_year_end=last_year_end,
            target_amount=parse_target(target_amount),
            deposit_source_start=parsed_deposit_start,
            deposit_source_end=parsed_deposit_end,
            reservoir_source_start=parsed_reservoir_start,
            reservoir_source_end=parsed_reservoir_end,
        )


@dataclass
class ModuleResult:
    module: str
    status: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    source_version: str = "v1"


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    level: str
    status: str
    module: str
    message: str
    actual: float | str | None = None
    expected: float | str | None = None
    difference: float | None = None


@dataclass
class ReviewPackResult:
    request: ReviewRequest
    modules: dict[str, ModuleResult]
    checks: list[CheckResult] = field(default_factory=list)
    local_snapshot: str = ""
    lark_url: str = ""
