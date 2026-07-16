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
_OVERVIEW_CURRENT_ONLY_METRICS = {
    "活动目标",
    "目标完成额",
    "目标完成率",
    "目标差额",
    "时间进度",
    "营收进度与时间进度差",
}
_NULLABLE_FORMULA_METRICS = {
    "付费转化率",
    "转化率",
    "组合品转化率",
    "目标完成率",
    "尾款率",
    "转大率",
    "活跃蓄水用户转大率",
    "非活跃蓄水用户转大率",
    "有效接通率",
    "线索领取率",
    "企微添加率",
    "客单价",
    "ARPU",
    "组合品客单价",
    "组合品ARPU",
    "有效接通后转化率",
    "有效接通后客单价",
    "有效接通后ARPU",
    "未有效接通后转化率",
    "未有效接通后客单价",
    "未有效接通后ARPU",
}
_BOUNDED_RATE_MARKERS = (
    "转化率",
    "占比",
    "比例",
    "尾款率",
    "转大率",
    "领取率",
    "接通率",
    "添加率",
)
_OPTIONAL_SOURCE_METRICS = {"企微添加人数", "企微添加率"}
_STRONG_CHANNEL_SUM_DIMENSIONS = {
    "overview": {None, "渠道", "经营总览"},
    "active_efficiency": {"渠道"},
    "product_structure": {"商品"},
    "deposit": {"用户层级×学段"},
    "reservoir": {"用户层级×学段"},
}
_UNIQUE_CHANNEL_PEOPLE_MODULES = {"deposit", "reservoir"}
_DEFAULT_STAGE_COVERAGE_METRICS = (
    "活跃人数", "活跃用户", "来源用户数", "付费人数", "订单量", "营收", "付费金额"
)
_STAGE_COVERAGE_METRICS_BY_MODULE = {
    "user_stage": ("活跃人数",),
    "product_structure": ("活跃人数",),
    "deposit": ("定金来源用户数",),
    "reservoir": ("蓄水来源用户数",),
    "high_value": ("来源用户数",),
    "sales_funnel": ("线索领取人数",),
}
_HIGH_VALUE_CHILDREN = {
    "高净值－当年毕业",
    "高净值－历史大会员可续购",
    "高净值－历史大会员不可续购",
    "高净值－其他组合品",
}


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


def _optional_source_missing(row: Mapping[str, Any]) -> bool:
    return (
        row.get("metric") in _OPTIONAL_SOURCE_METRICS
        and row.get("source_version") == "data_source_missing"
        and "data_source_missing" in str(row.get("definition_id", ""))
        and "数据源未接入" in str(row.get("dimension_value", ""))
    )


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
    """Strong-check only channel partitions proven mutually exclusive and complete."""
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
    summarized: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
    strong_dimensions = _STRONG_CHANNEL_SUM_DIMENSIONS.get(module, set())
    for (metric, dimension_type, *_), channels in grouped.items():
        if not {"私域整体", "APP", "销售"}.issubset(channels):
            continue
        additive = any(marker in metric for marker in _ADDITIVE_MARKERS) and not any(
            marker in metric for marker in _NON_ADDITIVE_MARKERS
        )
        overlapping = any(marker in metric for marker in _OVERLAP_MARKERS)
        if module in _UNIQUE_CHANNEL_PEOPLE_MODULES and overlapping:
            additive = True
            overlapping = False
        if not additive and not overlapping:
            continue
        strong = dimension_type in strong_dimensions
        if not strong:
            if additive:
                compared, mismatched = summarized[str(dimension_type)]
                for value_column in _PERIOD_VALUE_COLUMNS:
                    values = [
                        channels[channel].get(value_column)
                        for channel in ("私域整体", "APP", "销售")
                    ]
                    if not all(_number(value) for value in values):
                        continue
                    compared += 1
                    mismatched += abs(values[0] - values[1] - values[2]) > tolerance
                summarized[str(dimension_type)] = compared, mismatched
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
    for dimension_type, (compared, mismatched) in summarized.items():
        checks.append(
            _result(
                "channel_sum_unverifiable",
                "warning",
                module,
                (
                    f"{dimension_type}不是互斥完备渠道分区，比例不加总；"
                    f"金额和订单仅汇总提示（{mismatched}/{compared} 项存在差异）"
                ),
                actual=mismatched,
                expected=compared,
            )
        )
    return checks


def _check_unknown_stage_coverage(
    module: str, rows: list[dict]
) -> list[CheckResult]:
    """Summarize retained unknown-stage buckets as coverage warnings."""
    grouped: dict[tuple[Any, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        dimension_type = str(row.get("dimension_type", ""))
        if "学段" in dimension_type:
            grouped[(row.get("channel"), dimension_type)].append(row)

    checks: list[CheckResult] = []
    for (channel, dimension_type), group_rows in grouped.items():
        by_metric: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in group_rows:
            by_metric[str(row.get("metric"))].append(row)
        metric_priority = _STAGE_COVERAGE_METRICS_BY_MODULE.get(
            module, _DEFAULT_STAGE_COVERAGE_METRICS
        )
        metric = next(
            (
                candidate
                for candidate in metric_priority
                if candidate in by_metric
                and any(
                    _unknown_stage_component(
                        dimension_type, row.get("dimension_value")
                    )
                    for row in by_metric[candidate]
                )
            ),
            None,
        )
        if metric is None:
            continue

        denominator_rows = _independent_stage_rows(
            dimension_type, by_metric[metric]
        )
        coverage_by_period: list[float | None] = []
        unknown_present = False
        for column in _PERIOD_VALUE_COLUMNS:
            total, unknown = _stage_population_values(
                dimension_type, denominator_rows, column
            )
            unknown_present = unknown_present or unknown > 0
            coverage_by_period.append(
                None if total <= 0 else (total - unknown) / total
            )
        if not unknown_present:
            continue

        last_year_coverage, current_coverage = coverage_by_period

        def display(value: float | None) -> str:
            return "无可用分母" if value is None else f"{value:.2%}"

        available = [value for value in coverage_by_period if value is not None]
        difference = max((1 - value for value in available), default=None)
        checks.append(
            _result(
                "stage_unknown_coverage",
                "warning",
                module,
                (
                    f"{channel}{dimension_type}保留未知桶；识别覆盖率："
                    f"分母口径：{metric}；"
                    f"本期 {display(current_coverage)}，"
                    f"去年同期 {display(last_year_coverage)}"
                ),
                actual=(
                    f"本期 {display(current_coverage)}；"
                    f"去年同期 {display(last_year_coverage)}"
                ),
                expected="100%",
                difference=difference,
            )
        )
    return checks


def _dimension_component(
    dimension_type: str, dimension_value: Any, component: str
) -> str | None:
    labels = dimension_type.split("×")
    values = str(dimension_value).split("×")
    try:
        index = labels.index(component)
    except ValueError:
        return None
    return values[index].strip() if index < len(values) else None


def _unknown_stage_component(dimension_type: str, dimension_value: Any) -> bool:
    return _dimension_component(dimension_type, dimension_value, "学段") in _UNKNOWN_VALUES


def _independent_stage_rows(
    dimension_type: str, rows: Sequence[Mapping[str, Any]]
) -> list[Mapping[str, Any]]:
    if "用户层级" not in dimension_type:
        return list(rows)
    return [
        row
        for row in rows
        if _dimension_component(
            dimension_type, row.get("dimension_value"), "用户层级"
        )
        not in _HIGH_VALUE_CHILDREN
    ]


def _stage_population_values(
    dimension_type: str,
    rows: Sequence[Mapping[str, Any]],
    value_column: str,
) -> tuple[float, float]:
    if "商品" not in dimension_type:
        total = sum(
            row.get(value_column)
            for row in rows
            if _number(row.get(value_column))
        )
        unknown = sum(
            row.get(value_column)
            for row in rows
            if _unknown_stage_component(dimension_type, row.get("dimension_value"))
            and _number(row.get(value_column))
        )
        return total, unknown

    by_stage: dict[str | None, list[float]] = defaultdict(list)
    for row in rows:
        value = row.get(value_column)
        if _number(value):
            stage = _dimension_component(
                dimension_type, row.get("dimension_value"), "学段"
            )
            by_stage[stage].append(value)
    collapsed = {stage: max(values) for stage, values in by_stage.items()}
    total = sum(collapsed.values())
    unknown = sum(
        value for stage, value in collapsed.items() if stage in _UNKNOWN_VALUES
    )
    return total, unknown


def _formula_spec(
    metrics: Mapping[str, Mapping[str, Any]],
) -> list[tuple[str, str | None, str | None, str, tuple[str, ...], tuple[str, ...]]]:
    specs: list[
        tuple[str, str | None, str | None, str, tuple[str, ...], tuple[str, ...]]
    ] = []

    def add(
        targets: Sequence[str],
        numerators: Sequence[str],
        denominators: Sequence[str],
        check_id: str,
    ) -> None:
        target_options = tuple(targets)
        numerator_options = tuple(numerators)
        denominator_options = tuple(denominators)
        target = next((name for name in target_options if name in metrics), None)
        if target is None:
            return
        numerator = next((name for name in numerator_options if name in metrics), None)
        denominator = next((name for name in denominator_options if name in metrics), None)
        specs.append(
            (
                target,
                numerator,
                denominator,
                check_id,
                numerator_options,
                denominator_options,
            )
        )

    add(
        ("付费转化率", "转化率"),
        ("活跃付费人数", "付费人数", "支付用户", "转化人数"),
        ("活跃人数", "活跃用户", "线索领取人数"),
        "formula_conversion",
    )
    add(
        ("目标完成率",),
        ("目标完成额",),
        ("活动目标",),
        "formula_completion",
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
        ("活跃蓄水用户转大率",),
        ("活跃蓄水转大人数",),
        ("活跃蓄水用户数",),
        "formula_conversion",
    )
    add(
        ("非活跃蓄水用户转大率",),
        ("非活跃蓄水转大人数",),
        ("非活跃蓄水用户数",),
        "formula_conversion",
    )
    add(
        ("有效接通率",),
        ("有效接通人数",),
        ("电话拨打人数",),
        "formula_conversion",
    )
    add(
        ("线索领取率",),
        ("线索领取人数",),
        ("活跃人数", "活跃用户"),
        "formula_conversion",
    )
    add(
        ("企微添加率",),
        ("企微添加人数",),
        ("线索领取人数",),
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
    for target, numerators, denominators in (
        ("活跃人数占比", ("活跃人数",), ("渠道活跃人数总量",)),
        ("付费人数占比", ("付费人数",), ("渠道付费人数总量",)),
        ("订单占比", ("订单量",), ("渠道订单量总量",)),
        ("营收占比", ("付费金额", "营收"), ("渠道营收总量",)),
        ("尾款营收占整体营收比例", ("尾款营收",), ("整体营收",)),
        ("高净值营收占私域营收比例", ("营收",), ("私域营收",)),
    ):
        add((target,), numerators, denominators, "formula_ratio")
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
        for (
            target,
            numerator,
            denominator,
            check_id,
            numerator_options,
            denominator_options,
        ) in _formula_spec(metrics):
            if numerator is None or denominator is None:
                if denominator is not None:
                    for value_column in _PERIOD_VALUE_COLUMNS:
                        if (
                            module == "overview"
                            and target in _OVERVIEW_CURRENT_ONLY_METRICS
                            and value_column == "last_year_value"
                        ):
                            continue
                        actual = metrics[target].get(value_column)
                        bottom = metrics[denominator].get(value_column)
                        if _number(bottom) and bottom != 0 and not _number(actual):
                            checks.append(
                                _result(
                                    check_id,
                                    "failed",
                                    module,
                                    f"{target}分母非零时必须是有效数值",
                                    actual=(
                                        str(actual) if actual is not None else None
                                    ),
                                    expected="finite numeric result",
                                )
                            )
                missing = []
                if numerator is None:
                    missing.append("/".join(numerator_options))
                if denominator is None:
                    missing.append("/".join(denominator_options))
                checks.append(
                    _result(
                        "formula_unverifiable",
                        "warning",
                        module,
                        f"{target}缺少公式操作数，无法验证：{', '.join(missing)}",
                        expected=", ".join(missing),
                    )
                )
                continue
            for value_column in _PERIOD_VALUE_COLUMNS:
                if (
                    module == "overview"
                    and target in _OVERVIEW_CURRENT_ONLY_METRICS
                    and value_column == "last_year_value"
                ):
                    continue
                actual = metrics[target].get(value_column)
                top = metrics[numerator].get(value_column)
                bottom = metrics[denominator].get(value_column)
                if not _number(top) or not _number(bottom):
                    checks.append(
                        _result(
                            "formula_unverifiable",
                            "failed",
                            module,
                            f"{target}的公式操作数不是有效数值",
                            actual=str((top, bottom)),
                            expected="finite numeric operands",
                        )
                    )
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
                if not _number(actual):
                    checks.append(
                        _result(
                            check_id,
                            "failed",
                            module,
                            f"{target}分母非零时必须是有效数值",
                            actual=str(actual) if actual is not None else None,
                            expected=expected,
                        )
                    )
                    continue
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
        metric = str(row.get("metric", ""))
        current_only = (
            module == "overview" and metric in _OVERVIEW_CURRENT_ONLY_METRICS
        )
        period_status = row.get("period_status")
        if period_status != "complete" and not (
            current_only and period_status == "missing_last_year"
        ):
            checks.append(
                _result(
                    "period_complete",
                    "failed",
                    module,
                    f"{metric}的本期与去年同期必须同时存在",
                )
            )

        for column in _PERIOD_VALUE_COLUMNS:
            value = row.get(column)
            allowed_current_only_missing = (
                current_only
                and period_status == "missing_last_year"
                and column == "last_year_value"
                and value is None
            )
            allowed_formula_null = value is None and (
                metric in _NULLABLE_FORMULA_METRICS
                or "占比" in metric
                or "比例" in metric
            )
            if (
                not allowed_current_only_missing
                and not allowed_formula_null
                and not _number(value)
                and not (_optional_source_missing(row) and value is None)
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
            bounded_rate = metric == "时间进度" or any(
                marker in metric for marker in _BOUNDED_RATE_MARKERS
            )
            if bounded_rate and not (0 <= value <= 1):
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
        if dimension_value in _UNKNOWN_VALUES and dimension_type in {
            "用户分层",
            "用户层级",
        } and any(
            _number(row.get(column)) and row.get(column) > 0
            for column in _PERIOD_VALUE_COLUMNS
        ):
            checks.append(_result("user_unknown", "failed", module, "存在未识别用户分层"))
    return checks


def _independent_dimension_parts(
    dimension_type: str, parts: Sequence[Mapping[str, Any]]
) -> list[Mapping[str, Any]]:
    """Exclude nested high-value children when their parent aggregate is present."""
    if dimension_type not in {"用户分层", "用户层级"} or not any(
        part.get("dimension_value") == "高净值汇总" for part in parts
    ):
        return list(parts)
    return [
        part
        for part in parts
        if part.get("dimension_value") not in _HIGH_VALUE_CHILDREN
    ]


def _check_dimension_groups(
    module: str,
    totals: Mapping[tuple[Any, Any], Mapping[str, Any]],
    grouped: Mapping[tuple[Any, Any, str], Sequence[Mapping[str, Any]]],
    tolerance: float,
) -> list[CheckResult]:
    """Compare real detail dimensions with their channel-level module totals."""
    checks: list[CheckResult] = []
    for (channel, metric, dimension_type), raw_parts in grouped.items():
        total = totals.get((channel, metric))
        if total is None or any(
            marker in str(metric) for marker in _NON_ADDITIVE_MARKERS
        ):
            continue
        parts = _independent_dimension_parts(dimension_type, raw_parts)
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
                    module,
                    f"{dimension_type}明细（含未知）应与活跃效率总量一致",
                    actual=actual,
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

    return _check_dimension_groups("user_stage", totals, grouped, tolerance)


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
        if any(_optional_source_missing(row) for row in rows):
            checks.append(
                _result(
                    "optional_source",
                    "warning",
                    module_name,
                    "可选指标数据源未接入",
                )
            )
        checks.extend(_check_rows(module_name, rows, result.request.end))
        checks.extend(_check_unknown_stage_coverage(module_name, rows))
        checks.extend(_check_keys(module_name, rows))
        checks.extend(check_channel_sum(module_name, rows, tolerance))
        checks.extend(check_formula(module_name, rows, tolerance))
        if module_name == "deposit":
            checks.extend(
                _check_conservation(
                    module_name,
                    rows,
                    tolerance,
                    "定金来源用户数",
                    ("尾款人数", "未转化人数"),
                    "deposit_conservation",
                )
            )
            for metrics in _metric_rows(rows).values():
                destinations = (
                    "转组合品人数",
                    "转498人数",
                    "转其他商品人数",
                )
                if "尾款人数" not in metrics or not all(
                    metric in metrics for metric in destinations
                ):
                    continue
                for column in _PERIOD_VALUE_COLUMNS:
                    tail = metrics["尾款人数"].get(column)
                    values = [metrics[metric].get(column) for metric in destinations]
                    if not _number(tail) or not all(_number(value) for value in values):
                        continue
                    destination_sum = sum(values)
                    if abs(destination_sum - tail) > tolerance:
                        checks.append(
                            _result(
                                "deposit_destination_overlap",
                                "warning",
                                module_name,
                                "商品去向按用户可能跨品类重叠，不做相加守恒",
                                actual=destination_sum,
                                expected=tail,
                                difference=abs(destination_sum - tail),
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
