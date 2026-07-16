"""Observe review-pack output and report consistency checks."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from math import isfinite
from numbers import Number
from typing import Any

from .catalog import MODULE_SPECS
from .models import CheckResult, ReviewPackResult


_OPTIONAL_MODULES = {"deposit", "reservoir"}
_MODULE_SPEC_BY_NAME = {spec.name: spec for spec in MODULE_SPECS}
_KEY_COLUMNS = (
    "channel",
    "dimension_type",
    "dimension_value",
    "metric",
    "source_version",
    "definition_id",
)
_REQUIRED_COLUMNS = _KEY_COLUMNS + (
    "current_value",
    "last_year_value",
    "period_status",
    "current_date_range",
    "last_year_date_range",
    "data_updated_at",
)
_GROUP_COLUMNS = ("channel", "dimension_type", "dimension_value", "source_version")
_PERIOD_VALUE_COLUMNS = ("last_year_value", "current_value")
_UNKNOWN_VALUES = {"未知", "未知学段", "未映射", "unknown", "UNKNOWN", ""}
_ADDITIVE_MARKERS = ("营收", "金额", "订单量")
_NON_ADDITIVE_MARKERS = ("率", "占比", "差", "客单价", "ARPU")
_OVERLAP_MARKERS = ("人数", "用户数")


def _result(
    check_id: str,
    status: str,
    module: str,
    message: str,
    *,
    actual: float | str | None = None,
    expected: float | str | None = None,
    difference: float | None = None,
) -> CheckResult:
    level = {"passed": "info", "warning": "warning", "failed": "error"}[status]
    return CheckResult(
        check_id,
        level,
        status,
        module,
        message,
        actual,
        expected,
        difference,
    )


def _number(value: Any) -> bool:
    if not isinstance(value, Number) or isinstance(value, bool):
        return False
    try:
        return isfinite(value)
    except (TypeError, OverflowError):
        finite = getattr(value, "is_finite", None)
        return bool(finite()) if callable(finite) else False


def _group_key(row: Mapping[str, Any], fields: Sequence[str]) -> tuple[Any, ...]:
    return tuple(row.get(field) for field in fields)


def _metric_rows(
    rows: Iterable[Mapping[str, Any]],
) -> dict[tuple, dict[str, Mapping[str, Any]]]:
    groups: dict[tuple, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        groups[_group_key(row, _GROUP_COLUMNS)][str(row.get("metric"))] = row
    return groups


def check_channel_sum(
    module: str, rows: list[dict], tolerance: float
) -> list[CheckResult]:
    """Check only additive channel totals; report user overlap as a warning."""
    grouped: dict[tuple[Any, ...], dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        metric = str(row.get("metric", ""))
        dimension_type = row.get("dimension_type")
        dimension_value = row.get("dimension_value")
        if dimension_type in {"渠道", "经营总览"}:
            dimension_value = None
        key = (
            metric,
            dimension_type,
            dimension_value,
            row.get("source_version"),
            row.get("definition_id"),
        )
        grouped[key][str(row.get("channel"))] = row

    checks: list[CheckResult] = []
    for (metric, *_), channels in grouped.items():
        if not {"私域整体", "APP", "销售"}.issubset(channels):
            continue
        additive = any(marker in metric for marker in _ADDITIVE_MARKERS) and not any(
            marker in metric for marker in _NON_ADDITIVE_MARKERS
        )
        overlapping = any(marker in metric for marker in _OVERLAP_MARKERS)
        if not additive and not overlapping:
            continue
        for value_column in _PERIOD_VALUE_COLUMNS:
            private = channels["私域整体"].get(value_column)
            app = channels["APP"].get(value_column)
            sales = channels["销售"].get(value_column)
            if not all(_number(value) for value in (private, app, sales)):
                continue
            expected = app + sales
            difference = abs(private - expected)
            if additive:
                status = "failed" if difference > tolerance else "passed"
                check_id = "channel_sum"
                message = f"{metric}的 APP 与销售之和应等于私域整体"
            else:
                status = "warning" if difference > tolerance else "passed"
                check_id = "channel_overlap"
                message = f"{metric}是用户口径，渠道可能重叠，不强制相加"
            checks.append(
                _result(
                    check_id,
                    status,
                    module,
                    message,
                    actual=private,
                    expected=expected,
                    difference=difference,
                )
            )
    return checks


def _formula_spec(
    metrics: Mapping[str, Mapping[str, Any]],
) -> list[tuple[str, str, str, str]]:
    specs: list[tuple[str, str, str, str]] = []

    def add(
        targets: Sequence[str],
        numerators: Sequence[str],
        denominators: Sequence[str],
        check_id: str,
    ) -> None:
        target = next((name for name in targets if name in metrics), None)
        numerator = next((name for name in numerators if name in metrics), None)
        denominator = next((name for name in denominators if name in metrics), None)
        if target and numerator and denominator:
            specs.append((target, numerator, denominator, check_id))

    add(
        ("付费转化率", "转化率"),
        ("付费人数", "支付用户", "转化人数"),
        ("活跃人数", "活跃用户", "线索领取人数"),
        "formula_conversion",
    )
    add(
        ("组合品转化率",),
        ("组合品付费人数",),
        ("活跃人数", "活跃用户"),
        "formula_conversion",
    )
    add(("尾款率",), ("尾款人数",), ("定金来源用户数",), "formula_conversion")
    add(("转大率",), ("转大人数",), ("蓄水来源用户数",), "formula_conversion")
    add(
        ("有效接通率",),
        ("有效接通人数",),
        ("电话拨打人数",),
        "formula_conversion",
    )
    add(
        ("客单价",),
        ("付费金额", "营收", "转化营收"),
        ("付费人数", "支付用户", "转化人数"),
        "formula_aov",
    )
    add(
        ("ARPU",),
        ("付费金额", "营收", "转化营收"),
        ("活跃人数", "活跃用户", "线索领取人数"),
        "formula_arpu",
    )
    add(
        ("组合品客单价",),
        ("组合品营收",),
        ("组合品付费人数",),
        "formula_aov",
    )
    add(
        ("组合品ARPU",),
        ("组合品营收",),
        ("活跃人数", "活跃用户"),
        "formula_arpu",
    )
    for prefix, population in (
        ("有效接通后", "有效接通人数"),
        ("未有效接通后", "未有效接通人数"),
    ):
        add(
            (f"{prefix}转化率",),
            (f"{prefix}转化人数",),
            (population,),
            "formula_conversion",
        )
        add(
            (f"{prefix}客单价",),
            (f"{prefix}营收",),
            (f"{prefix}转化人数",),
            "formula_aov",
        )
        add(
            (f"{prefix}ARPU",),
            (f"{prefix}营收",),
            (population,),
            "formula_arpu",
        )
    return specs


def check_formula(
    module: str, rows: list[dict], tolerance: float
) -> list[CheckResult]:
    """Check deterministic conversion, AOV, and ARPU formulas."""
    checks: list[CheckResult] = []
    for metrics in _metric_rows(rows).values():
        for target, numerator, denominator, check_id in _formula_spec(metrics):
            for value_column in _PERIOD_VALUE_COLUMNS:
                actual = metrics[target].get(value_column)
                top = metrics[numerator].get(value_column)
                bottom = metrics[denominator].get(value_column)
                if not all(_number(value) for value in (actual, top, bottom)):
                    continue
                if bottom == 0:
                    if actual not in (0, None):
                        checks.append(
                            _result(
                                check_id,
                                "failed",
                                module,
                                f"{target}分母为零时必须为零",
                                actual=actual,
                                expected=0,
                                difference=abs(actual),
                            )
                        )
                    continue
                expected = top / bottom
                difference = abs(actual - expected)
                checks.append(
                    _result(
                        check_id,
                        "failed" if difference > tolerance else "passed",
                        module,
                        f"{target}应等于{numerator}除以{denominator}",
                        actual=actual,
                        expected=expected,
                        difference=difference,
                    )
                )
    return checks


def _check_keys(module: str, rows: list[dict]) -> list[CheckResult]:
    checks: list[CheckResult] = []
    seen: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for row in rows:
        key = _group_key(row, _KEY_COLUMNS)
        previous = seen.get(key)
        if previous is None:
            seen[key] = row
            continue
        relevant = tuple(previous.get(field) for field in _REQUIRED_COLUMNS)
        current = tuple(row.get(field) for field in _REQUIRED_COLUMNS)
        check_id = "duplicate_key" if current == relevant else "conflicting_key"
        checks.append(
            _result(
                check_id,
                "failed",
                module,
                (
                    "同一业务键出现重复数据"
                    if check_id == "duplicate_key"
                    else "同一业务键出现冲突数据"
                ),
                actual=str(key),
            )
        )
    return checks


def _check_rows(module: str, rows: list[dict], request_end: date) -> list[CheckResult]:
    checks: list[CheckResult] = []
    for row in rows:
        missing = [column for column in _REQUIRED_COLUMNS if column not in row]
        if missing:
            checks.append(
                _result(
                    "required_columns",
                    "failed",
                    module,
                    f"缺少必需列：{', '.join(missing)}",
                    actual=", ".join(missing),
                )
            )
        if row.get("period_status") != "complete":
            checks.append(
                _result(
                    "period_complete", "failed", module, "本期与去年同期必须同时存在"
                )
            )

        metric = str(row.get("metric", ""))
        for column in _PERIOD_VALUE_COLUMNS:
            value = row.get(column)
            if (
                value is not None
                and not _number(value)
                and row.get("source_version") != "data_source_missing"
            ):
                checks.append(
                    _result(
                        "numeric_value",
                        "failed",
                        module,
                        f"{metric}必须是数值",
                        actual=str(value),
                        expected="numeric",
                    )
                )
            if not _number(value):
                continue
            if value < 0 and "差" not in metric:
                checks.append(
                    _result(
                        "non_negative",
                        "failed",
                        module,
                        f"{metric}不能为负数",
                        actual=value,
                        expected=0,
                        difference=abs(value),
                    )
                )
            if ("率" in metric or "占比" in metric or metric == "时间进度") and not (
                0 <= value <= 1
            ):
                checks.append(
                    _result(
                        "percentage_range",
                        "failed",
                        module,
                        f"{metric}必须在 0 到 1 之间",
                        actual=value,
                        expected="0..1",
                    )
                )

        updated = row.get("data_updated_at")
        updated_date: date | None = None
        if isinstance(updated, datetime):
            updated_date = updated.date()
        elif isinstance(updated, date):
            updated_date = updated
        elif isinstance(updated, str):
            try:
                updated_date = datetime.fromisoformat(updated).date()
            except ValueError:
                updated_date = None
        if updated_date is None or updated_date < request_end:
            checks.append(
                _result(
                    "update_freshness",
                    "failed",
                    module,
                    "数据更新时间缺失或早于本期结束日",
                    actual=str(updated) if updated is not None else None,
                    expected=request_end.isoformat(),
                )
            )

        dimension_type = str(row.get("dimension_type", ""))
        dimension_value = row.get("dimension_value")
        if dimension_value in _UNKNOWN_VALUES and dimension_type == "学段" and any(
            _number(row.get(column)) and row.get(column) > 0
            for column in _PERIOD_VALUE_COLUMNS
        ):
            checks.append(_result("stage_unknown", "failed", module, "存在未识别学段"))
        if dimension_value in _UNKNOWN_VALUES and dimension_type in {
            "用户分层",
            "用户层级",
        } and any(
            _number(row.get(column)) and row.get(column) > 0
            for column in _PERIOD_VALUE_COLUMNS
        ):
            checks.append(_result("user_unknown", "failed", module, "存在未识别用户分层"))
    return checks


def _check_dimension_sums(
    module: str, rows: list[dict], tolerance: float
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    totals: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    dimensions: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        base = (row.get("channel"), row.get("metric"), row.get("source_version"))
        dimension_type = row.get("dimension_type")
        if dimension_type == "总览":
            totals[base] = row
        elif dimension_type in {"学段", "用户分层", "用户层级"}:
            dimensions[base + (dimension_type,)].append(row)

    high_value_children = {
        "高净值－当年毕业",
        "高净值－历史大会员可续购",
        "高净值－历史大会员不可续购",
        "高净值－其他组合品",
    }
    for (*base, dimension_type), parts in dimensions.items():
        total = totals.get(tuple(base))
        if total is None:
            continue
        metric = str(base[1])
        if any(marker in metric for marker in _NON_ADDITIVE_MARKERS):
            continue
        if dimension_type in {"用户分层", "用户层级"} and any(
            part.get("dimension_value") == "高净值汇总" for part in parts
        ):
            parts = [
                part
                for part in parts
                if part.get("dimension_value") not in high_value_children
            ]
        for column in _PERIOD_VALUE_COLUMNS:
            total_value = total.get(column)
            part_values = [part.get(column) for part in parts]
            if not _number(total_value) or not all(_number(value) for value in part_values):
                continue
            expected = sum(part_values)
            difference = abs(total_value - expected)
            checks.append(
                _result(
                    "dimension_sum",
                    "failed" if difference > tolerance else "passed",
                    module,
                    f"{dimension_type}明细（含未知）应与总览一致",
                    actual=total_value,
                    expected=expected,
                    difference=difference,
                )
            )
    return checks


def _check_conservation(
    module: str,
    rows: list[dict],
    tolerance: float,
    total_metric: str,
    part_metrics: Sequence[str],
    check_id: str,
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    for metrics in _metric_rows(rows).values():
        if total_metric not in metrics or not all(
            metric in metrics for metric in part_metrics
        ):
            continue
        for column in _PERIOD_VALUE_COLUMNS:
            actual = metrics[total_metric].get(column)
            values = [metrics[metric].get(column) for metric in part_metrics]
            if not _number(actual) or not all(_number(value) for value in values):
                continue
            expected = sum(values)
            difference = abs(actual - expected)
            checks.append(
                _result(
                    check_id,
                    "failed" if difference > tolerance else "passed",
                    module,
                    f"{total_metric}应等于各去向之和",
                    actual=actual,
                    expected=expected,
                    difference=difference,
                )
            )
    return checks


def _check_cross_module_dimensions(
    result: ReviewPackResult, tolerance: float
) -> list[CheckResult]:
    total_module = result.modules.get("active_efficiency")
    detail_module = result.modules.get("user_stage")
    if (
        total_module is None
        or detail_module is None
        or total_module.status != "success"
        or detail_module.status != "success"
    ):
        return []

    totals = {
        (row.get("channel"), row.get("metric")): row for row in total_module.rows
    }
    grouped: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in detail_module.rows:
        if row.get("dimension_type") in {"用户分层", "用户层级", "学段"}:
            grouped[
                (row.get("channel"), row.get("metric"), row.get("dimension_type"))
            ].append(row)

    high_value_children = {
        "高净值－当年毕业",
        "高净值－历史大会员可续购",
        "高净值－历史大会员不可续购",
        "高净值－其他组合品",
    }
    checks: list[CheckResult] = []
    for (channel, metric, dimension_type), parts in grouped.items():
        total = totals.get((channel, metric))
        if total is None:
            continue
        if any(marker in str(metric) for marker in _NON_ADDITIVE_MARKERS):
            continue
        if dimension_type in {"用户分层", "用户层级"} and any(
            part.get("dimension_value") == "高净值汇总" for part in parts
        ):
            parts = [
                part
                for part in parts
                if part.get("dimension_value") not in high_value_children
            ]
        for column in _PERIOD_VALUE_COLUMNS:
            actual = total.get(column)
            values = [part.get(column) for part in parts]
            if not _number(actual) or not all(_number(value) for value in values):
                continue
            expected = sum(values)
            difference = abs(actual - expected)
            checks.append(
                _result(
                    "dimension_sum",
                    "failed" if difference > tolerance else "passed",
                    "user_stage",
                    f"{dimension_type}明细（含未知）应与活跃效率总量一致",
                    actual=actual,
                    expected=expected,
                    difference=difference,
                )
            )
    return checks


def validate_pack(
    result: ReviewPackResult, tolerance: float = 0.01
) -> list[CheckResult]:
    """Return observational consistency results for a review pack."""
    checks: list[CheckResult] = []
    expected_modules = {spec.name for spec in MODULE_SPECS}
    for module_name in sorted(expected_modules | set(result.modules)):
        module = result.modules.get(module_name)
        optional = module_name in _OPTIONAL_MODULES
        if module is None:
            checks.append(
                _result(
                    "module_status",
                    "warning" if optional else "failed",
                    module_name,
                    "可选模块未提供" if optional else "必需模块缺失",
                )
            )
            continue
        if module.status != "success":
            checks.append(
                _result(
                    "module_status",
                    (
                        "warning"
                        if optional and module.status == "not_applicable"
                        else "failed"
                    ),
                    module_name,
                    (
                        "可选来源不可用"
                        if optional and module.status == "not_applicable"
                        else "模块执行失败"
                    ),
                    actual=module.status,
                    expected="success",
                )
            )
            continue
        checks.append(_result("module_status", "passed", module_name, "模块成功"))
        if not module.rows:
            checks.append(
                _result(
                    "required_results", "failed", module_name, "模块没有必需结果"
                )
            )
            continue
        rows = module.rows
        spec = _MODULE_SPEC_BY_NAME.get(module_name)
        if spec is not None:
            available_metrics = {row.get("metric") for row in rows}
            missing_metrics = [
                metric for metric in spec.metrics if metric not in available_metrics
            ]
            if missing_metrics:
                checks.append(
                    _result(
                        "required_results",
                        "failed",
                        module_name,
                        f"缺少必需指标：{', '.join(missing_metrics)}",
                        actual=", ".join(missing_metrics),
                    )
                )
        if any(row.get("source_version") == "data_source_missing" for row in rows):
            checks.append(
                _result(
                    "optional_source",
                    "warning",
                    module_name,
                    "可选指标数据源未接入",
                )
            )
        checks.extend(_check_rows(module_name, rows, result.request.end))
        checks.extend(_check_keys(module_name, rows))
        checks.extend(check_channel_sum(module_name, rows, tolerance))
        checks.extend(_check_dimension_sums(module_name, rows, tolerance))
        checks.extend(check_formula(module_name, rows, tolerance))
        if module_name == "deposit":
            checks.extend(
                _check_conservation(
                    module_name,
                    rows,
                    tolerance,
                    "定金来源用户数",
                    (
                        "转组合品人数",
                        "转498人数",
                        "转其他商品人数",
                        "未转化人数",
                    ),
                    "deposit_conservation",
                )
            )
        if module_name == "sales_funnel":
            checks.extend(
                _check_conservation(
                    module_name,
                    rows,
                    tolerance,
                    "电话拨打人数",
                    ("有效接通人数", "未有效接通人数"),
                    "sales_conservation",
                )
            )
    checks.extend(_check_cross_module_dimensions(result, tolerance))
    return checks
