"""Create a type-faithful Lark review workbook and verify it by reading it back."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
import math
from numbers import Integral, Real
import os
import re
import shutil
import subprocess
from typing import Any

from .catalog import SHEET_ORDER
from .models import ReviewPackResult


CommandRunner = Callable[[list[str], str | None], dict[str, Any]]

_BUSINESS_COLUMNS = (
    "channel",
    "dimension_type",
    "dimension_value",
    "metric",
    "current_value",
    "last_year_value",
    "absolute_change",
    "relative_change",
    "period_status",
    "current_date_range",
    "last_year_date_range",
    "source_version",
    "data_updated_at",
    "definition_id",
)
_CHECK_COLUMNS = (
    "check_id",
    "level",
    "status",
    "module",
    "message",
    "actual",
    "expected",
    "difference",
)
_MODULE_SHEETS = {
    "overview": ("经营总览",),
    "active_efficiency": ("活跃效率",),
    "user_stage": ("用户分层", "学段表现"),
    "product_structure": ("商品结构",),
    "deposit": ("定金策略",),
    "reservoir": ("蓄水策略",),
    "high_value": ("高净值策略",),
    "sales_funnel": ("销售承接",),
}


class LarkWorkbookWriter:
    """Write one new workbook and return its URL only after successful readback."""

    def __init__(self, command_runner: CommandRunner | None = None) -> None:
        if command_runner is None:
            if shutil.which("lark-cli") is None:
                raise RuntimeError("未找到 lark-cli，无法创建飞书表格")
            command_runner = _run_command
        self.command_runner = command_runner

    def write(self, result: ReviewPackResult) -> str:
        self._require_verified_user()
        payload = _workbook_payload(result)
        styles = _workbook_styles(payload)
        title = (
            f"{result.request.name}_复盘数据包_"
            f"{result.request.start.isoformat()}_{result.request.end.isoformat()}"
        )
        created = self.command_runner(
            [
                "lark-cli",
                "sheets",
                "+workbook-create",
                "--title",
                title,
                "--sheets",
                "-",
                "--styles",
                json.dumps(styles, ensure_ascii=False, allow_nan=False),
                "--as",
                "user",
                "--format",
                "json",
            ],
            json.dumps(payload, ensure_ascii=False, allow_nan=False),
        )
        if created.get("ok") is not True:
            raise RuntimeError("飞书工作簿创建失败，本地快照已保留")
        url = _created_url(created)
        if not url:
            raise RuntimeError("飞书工作簿创建失败，本地快照已保留")

        # The workbook already exists at this point. Preserve its address even
        # when readback fails so callers can recover instead of creating a copy.
        result.lark_url = url
        self.verify(url, payload)
        return url

    def verify(
        self,
        url: str,
        result_or_payload: ReviewPackResult | Mapping[str, Any],
    ) -> str:
        """Verify an existing workbook without creating or changing it."""

        is_result = isinstance(result_or_payload, ReviewPackResult)
        payload = (
            _workbook_payload(result_or_payload)
            if is_result
            else result_or_payload
        )
        readback = self.command_runner(
            [
                "lark-cli",
                "sheets",
                "+table-get",
                "--url",
                url,
                "--as",
                "user",
                "--format",
                "json",
            ],
            None,
        )
        if readback.get("ok") is not True or not _readback_structure_matches(
            payload, readback.get("data")
        ):
            raise RuntimeError("回读验证失败，本地快照已保留")

        for expected_sheet, row_index in _sentinel_rows(payload):
            if not self._targeted_row_matches(url, expected_sheet, row_index):
                raise RuntimeError("回读验证失败，本地快照已保留")

        if is_result:
            result_or_payload.lark_url = url
        return url

    def _targeted_row_matches(
        self,
        url: str,
        expected_sheet: Mapping[str, Any],
        row_index: int,
    ) -> bool:
        sheet_row = row_index + 2
        last_column = _column_letter(len(expected_sheet["columns"]))
        requested_range = f"A{sheet_row}:{last_column}{sheet_row}"
        response = self.command_runner(
            [
                "lark-cli",
                "sheets",
                "+table-get",
                "--url",
                url,
                "--sheet-name",
                expected_sheet["name"],
                "--range",
                requested_range,
                "--no-header",
                "--as",
                "user",
                "--format",
                "json",
            ],
            None,
        )
        if response.get("ok") is not True:
            return False
        data = response.get("data")
        if not isinstance(data, Mapping):
            return False
        sheets = data.get("sheets")
        if not isinstance(sheets, list) or len(sheets) != 1:
            return False
        actual_sheet = sheets[0]
        if not isinstance(actual_sheet, Mapping):
            return False
        if actual_sheet.get("name") != expected_sheet["name"]:
            return False
        if _parse_a1_range(actual_sheet.get("range")) != (
            1,
            sheet_row,
            len(expected_sheet["columns"]),
            sheet_row,
        ):
            return False
        rows = actual_sheet.get("data")
        if not isinstance(rows, list) or len(rows) != 1:
            return False
        return _sentinel_matches(
            expected_sheet, expected_sheet["data"][row_index], rows[0]
        )

    def _require_verified_user(self) -> None:
        status = self.command_runner(
            ["lark-cli", "auth", "status", "--json", "--verify"], None
        )
        user = status.get("identities", {}).get("user")
        user_ready = (
            isinstance(user, Mapping)
            and user.get("verified") is True
            and user.get("available") is True
            and user.get("status") in {"ready", "active"}
            and bool(user.get("tokenStatus"))
            and user.get("tokenStatus") != "invalid"
        )
        if not user_ready:
            raise RuntimeError("飞书用户认证不可用，请先完成用户认证")


def _run_command(argv: list[str], stdin: str | None = None) -> dict[str, Any]:
    env = os.environ.copy()
    env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    completed = subprocess.run(
        argv,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    output = completed.stdout if completed.returncode == 0 else completed.stderr
    try:
        response = json.loads(output)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("lark-cli 返回了无法识别的结果") from exc
    if not isinstance(response, dict):
        raise RuntimeError("lark-cli 返回了无法识别的结果")
    return response


def _workbook_payload(result: ReviewPackResult) -> dict[str, list[dict[str, Any]]]:
    records: dict[str, list[dict[str, Any]]] = {name: [] for name in SHEET_ORDER}

    ordered_checks = sorted(
        (asdict(check) for check in result.checks),
        key=lambda row: {"failed": 0, "warning": 1, "passed": 2}.get(
            str(row.get("status")), 3
        ),
    )
    records["检查结果"] = ordered_checks

    for module_name, module in result.modules.items():
        targets = _MODULE_SHEETS.get(module_name, ())
        for source_row in module.rows:
            row = dict(source_row)
            if module_name == "user_stage" and len(targets) == 2:
                target = (
                    "学段表现"
                    if "学段" in str(row.get("dimension_type", ""))
                    else "用户分层"
                )
            elif targets:
                target = targets[0]
            else:
                continue
            records[target].append(row)

    definitions: list[dict[str, Any]] = []
    seen_definitions: set[tuple[Any, ...]] = set()
    for module_name, module in result.modules.items():
        for row in module.rows:
            key = (
                module_name,
                row.get("metric"),
                row.get("definition_id"),
                row.get("source_version", module.source_version),
            )
            if key in seen_definitions:
                continue
            seen_definitions.add(key)
            definitions.append(
                {
                    "module": module_name,
                    "metric": row.get("metric"),
                    **_definition_details(
                        module_name,
                        str(row.get("metric", "")),
                        module.rows,
                        str(row.get("definition_id", "")),
                    ),
                    "definition_id": row.get("definition_id"),
                    "source_version": row.get("source_version", module.source_version),
                }
            )
    records["指标口径"] = definitions

    request = result.request
    executed_at = datetime.now().astimezone().replace(microsecond=0).isoformat()
    records["运行记录"] = [
        {
            "activity": request.name,
            "current_date_range": f"{request.start.isoformat()}/{request.end.isoformat()}",
            "last_year_date_range": (
                f"{request.last_year_start.isoformat()}/{request.last_year_end.isoformat()}"
            ),
            "period_days": request.period_days,
            "target_amount": request.target_amount,
            "deposit_source_range": _date_range(
                request.deposit_source_start, request.deposit_source_end
            ),
            "reservoir_source_range": _date_range(
                request.reservoir_source_start, request.reservoir_source_end
            ),
            "executed_at": executed_at,
            "module": module_name,
            "module_status": module.status,
            "row_count": len(module.rows),
            "data_updated_at": _module_updated_at(module.rows),
            "source_version": module.source_version,
            "result_source": result.local_snapshot or "本次运行内存结果",
        }
        for module_name, module in result.modules.items()
    ]

    sheets = []
    for name in SHEET_ORDER:
        if name == "检查结果":
            preferred = _CHECK_COLUMNS
        elif name == "指标口径":
            preferred = (
                "module", "metric", "business_definition", "numerator",
                "denominator", "source_table", "filter_rules",
                "supported_dimensions", "definition_id", "source_version",
            )
        elif name == "运行记录":
            preferred = (
                "activity",
                "current_date_range",
                "last_year_date_range",
                "period_days",
                "target_amount",
                "deposit_source_range",
                "reservoir_source_range",
                "executed_at",
                "module",
                "module_status",
                "row_count",
                "data_updated_at",
                "source_version",
                "result_source",
            )
        else:
            preferred = _BUSINESS_COLUMNS
        sheets.append(_typed_sheet(name, records[name], preferred))
    return {"sheets": sheets}


_MODULE_CONTEXT = {
    "overview": (
        "dws.topic_order_detail",
        "活动期内有效订单；用户编号非空；排除测试用户；APP/销售按业绩归因；服务期另要求原价不低于39元且团队归属有效",
    ),
    "active_efficiency": (
        "aws.business_active_user_last_14_day",
        "活动期内用户编号非空的活跃记录；APP/销售按业绩归因，私域整体保留全部活跃用户",
    ),
    "user_stage": (
        "aws.business_active_user_last_14_day；dws.topic_order_detail",
        "活动期活跃用户保留未知层级和未知学段；组合品订单要求用户非空、排除测试用户、原价不低于39元且属于APP/销售",
    ),
    "product_structure": (
        "aws.business_active_user_last_14_day；dws.topic_order_detail",
        "活动期活跃人群与订单同渠道匹配；订单要求用户非空、排除测试用户、原价不低于39元且属于APP/销售",
    ),
    "deposit": (
        "dws.topic_order_detail；aws.business_active_user_last_14_day",
        "定金来源期按最早来源时间识别、按最后来源单确定渠道；尾款严格晚于来源时间并排除全部来源单；订单排除测试用户",
    ),
    "reservoir": (
        "dws.topic_order_detail；aws.business_active_user_last_14_day",
        "蓄水来源期按最早来源时间识别、按最后来源单确定渠道；转大订单位于活动观察期且晚于来源时间；订单排除测试用户",
    ),
    "high_value": (
        "dws.topic_user_active_detail_month；aws.business_active_user_last_14_day；dws.topic_order_detail",
        "活动首月高净值标签形成来源池；活动前最近合规订单确定APP/销售归因和学段；活动期订单排除测试用户",
    ),
    "sales_funnel": (
        "aws.crm_active_data_pool_day；tmp.niyiqiao_crm_clue_call_record；aws.business_active_user_last_14_day；dws.topic_order_detail",
        "领取后才计入拨打和接通；转化订单晚于领取或对应通话事件；订单排除测试用户；企微来源未接入时明确留空",
    ),
}

_MODULE_FORMULA_PARTS: dict[tuple[str, str], tuple[str, str]] = {
    ("overview", "目标完成率"): ("私域整体目标完成额", "活动目标"),
    ("overview", "目标差额"): ("活动目标－私域整体目标完成额", "不适用"),
    ("overview", "时间进度"): ("活动开始日至当前日期的已过天数（含首日，最高为活动总天数）", "活动总天数"),
    ("overview", "营收进度与时间进度差"): ("目标完成率－时间进度", "不适用"),
    ("overview", "业务营收与服务期营收差额"): ("同渠道业务营收－同渠道服务期营收", "不适用"),
    ("active_efficiency", "付费转化率"): ("同渠道付费人数", "同渠道活跃人数"),
    ("active_efficiency", "客单价"): ("同渠道付费金额", "同渠道付费人数"),
    ("active_efficiency", "ARPU"): ("同渠道付费金额", "同渠道活跃人数"),
    ("active_efficiency", "活跃人数占比"): ("同渠道活跃人数", "私域整体活跃人数"),
    ("active_efficiency", "付费人数占比"): ("同渠道付费人数", "私域整体付费人数"),
    ("active_efficiency", "营收占比"): ("同渠道付费金额", "私域整体付费金额"),
    ("user_stage", "付费转化率"): ("同渠道同切面付费人数", "同渠道同切面活跃人数"),
    ("user_stage", "客单价"): ("同渠道同切面付费金额", "同渠道同切面付费人数"),
    ("user_stage", "ARPU"): ("同渠道同切面付费金额", "同渠道同切面活跃人数"),
    ("user_stage", "活跃人数占比"): ("同渠道同切面活跃人数", "同渠道活跃人数总量"),
    ("user_stage", "付费人数占比"): ("同渠道同切面付费人数", "同渠道付费人数总量"),
    ("user_stage", "营收占比"): ("同渠道同切面付费金额", "同渠道付费金额总量"),
    ("user_stage", "组合品转化率"): ("同渠道同切面组合品付费人数", "同渠道同切面活跃人数"),
    ("user_stage", "组合品客单价"): ("同渠道同切面组合品营收", "同渠道同切面组合品付费人数"),
    ("user_stage", "组合品ARPU"): ("同渠道同切面组合品营收", "同渠道同切面活跃人数"),
    ("product_structure", "订单占比"): ("同渠道同切面商品订单量", "同渠道同切面订单量总量"),
    ("product_structure", "付费人数占比"): ("同渠道同切面商品付费人数", "同渠道同切面付费人数总量"),
    ("product_structure", "营收占比"): ("同渠道同切面商品营收", "同渠道同切面营收总量"),
    ("product_structure", "转化率"): ("同渠道同切面的活跃付费人数", "同渠道同切面的活跃人数"),
    ("product_structure", "客单价"): ("同渠道同切面商品营收", "同渠道同切面商品付费人数"),
    ("product_structure", "ARPU"): ("同渠道同切面商品营收", "同渠道同切面活跃人数"),
    ("deposit", "尾款率"): ("同渠道同层级学段的尾款人数", "同渠道同层级学段的定金来源用户数"),
    ("deposit", "尾款营收占整体营收比例"): ("同渠道同层级学段的尾款营收", "私域整体营收"),
    ("reservoir", "转大率"): ("同渠道同层级学段的转大人数", "同渠道同层级学段的蓄水来源用户数"),
    ("reservoir", "活跃蓄水用户转大率"): ("同渠道同层级学段的活跃蓄水转大人数", "同渠道同层级学段的活跃蓄水用户数"),
    ("reservoir", "非活跃蓄水用户转大率"): ("同渠道同层级学段的非活跃蓄水转大人数", "同渠道同层级学段的非活跃蓄水用户数"),
    ("high_value", "付费转化率"): ("同渠道同切面付费人数", "同渠道同切面活跃人数"),
    ("high_value", "客单价"): ("同渠道同切面营收", "同渠道同切面付费人数"),
    ("high_value", "ARPU"): ("同渠道同切面营收", "同渠道同切面活跃人数"),
    ("high_value", "组合品转化率"): ("同渠道同切面组合品付费人数", "同渠道同切面活跃人数"),
    ("high_value", "高净值营收占私域营收比例"): ("同渠道同切面高净值营收", "私域整体营收"),
    ("sales_funnel", "线索领取率"): ("同渠道同层级学段的线索领取人数", "同渠道同层级学段的活跃人数"),
    ("sales_funnel", "有效接通率"): ("同渠道同层级学段的有效接通人数", "同渠道同层级学段的电话拨打人数"),
    ("sales_funnel", "企微添加率"): ("同渠道同层级学段的企微添加人数", "同渠道同层级学段的线索领取人数"),
    ("sales_funnel", "转化率"): ("同渠道同层级学段的转化人数", "同渠道同层级学段的线索领取人数"),
    ("sales_funnel", "客单价"): ("同渠道同层级学段的转化营收", "同渠道同层级学段的转化人数"),
    ("sales_funnel", "ARPU"): ("同渠道同层级学段的转化营收", "同渠道同层级学段的线索领取人数"),
    ("sales_funnel", "有效接通后转化率"): ("同渠道同层级学段的有效接通后转化人数", "同渠道同层级学段的有效接通人数"),
    ("sales_funnel", "有效接通后客单价"): ("同渠道同层级学段的有效接通后营收", "同渠道同层级学段的有效接通后转化人数"),
    ("sales_funnel", "有效接通后ARPU"): ("同渠道同层级学段的有效接通后营收", "同渠道同层级学段的有效接通人数"),
    ("sales_funnel", "未有效接通后转化率"): ("同渠道同层级学段的未有效接通后转化人数", "同渠道同层级学段的未有效接通人数"),
    ("sales_funnel", "未有效接通后客单价"): ("同渠道同层级学段的未有效接通后营收", "同渠道同层级学段的未有效接通后转化人数"),
    ("sales_funnel", "未有效接通后ARPU"): ("同渠道同层级学段的未有效接通后营收", "同渠道同层级学段的未有效接通人数"),
}


def _definition_details(
    module: str,
    metric: str,
    rows: Sequence[Mapping[str, Any]],
    definition_id: str,
) -> dict[str, str]:
    numerator, denominator = _MODULE_FORMULA_PARTS.get(
        (module, metric), ("指标对应去重或汇总结果", "不适用")
    )
    dimensions = sorted(
        {
            str(row.get("dimension_type"))
            for row in rows
            if row.get("metric") == metric and row.get("dimension_type")
        }
    )
    source_table, filter_rules = _MODULE_CONTEXT.get(
        module, ("固定模块查询来源", "按该模块固定业务规则筛选")
    )
    return {
        "business_definition": _business_definition(metric, numerator, denominator),
        "numerator": numerator,
        "denominator": denominator,
        "source_table": source_table,
        "filter_rules": f"{filter_rules}；口径ID：{definition_id}",
        "supported_dimensions": "、".join(dimensions) or "总览",
    }


def _business_definition(metric: str, numerator: str, denominator: str) -> str:
    if denominator != "不适用":
        return f"{numerator} ÷ {denominator}"
    if "差额" in metric or metric.endswith("差"):
        return numerator
    if metric.endswith("人数") or metric.endswith("用户数"):
        return f"满足固定条件的去重用户数（{metric}）"
    if metric.endswith("订单量"):
        return f"满足固定条件的去重订单数（{metric}）"
    if any(marker in metric for marker in ("营收", "金额", "完成额", "目标")):
        return f"满足固定条件的金额汇总（{metric}）"
    return f"按该指标固定业务规则统计（{metric}）"


def _date_range(start: date | None, end: date | None) -> str | None:
    if start is None or end is None:
        return None
    return f"{start.isoformat()}/{end.isoformat()}"


def _module_updated_at(rows: Sequence[Mapping[str, Any]]) -> str | None:
    values = [row.get("data_updated_at") for row in rows if row.get("data_updated_at")]
    return max((str(value) for value in values), default=None)


def _typed_sheet(
    name: str,
    records: Sequence[Mapping[str, Any]],
    preferred_columns: Sequence[str],
) -> dict[str, Any]:
    columns = list(preferred_columns)
    for row in records:
        for column in row:
            if column not in columns:
                columns.append(column)
    dtypes = {
        column: _dtype([row.get(column) for row in records]) for column in columns
    }
    formats = {
        column: number_format
        for column in columns
        if (number_format := _number_format(column, dtypes[column])) is not None
    }
    return {
        "name": name,
        "columns": columns,
        "data": [[_json_value(row.get(column)) for column in columns] for row in records],
        "dtypes": dtypes,
        "formats": formats,
    }


def _workbook_styles(payload: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    styles = []
    business_sheets = set(SHEET_ORDER[1:10])
    for sheet in payload["sheets"]:
        columns = sheet["columns"]
        last_column = _column_letter(len(columns))
        cell_styles = [
            {
                "range": f"A1:{last_column}1",
                "font_weight": "bold",
                "background_color": "#DDEBF7",
                "horizontal_alignment": "center",
                "vertical_alignment": "middle",
            }
        ]
        if sheet["name"] in business_sheets:
            metric_index = columns.index("metric")
            for row_number, row in enumerate(sheet["data"], start=2):
                metric = str(row[metric_index] or "")
                if _percentage_metric(metric):
                    value_format = "0.00%"
                    value_range = f"E{row_number}:H{row_number}"
                elif _integer_metric(metric):
                    value_format = "#,##0"
                    value_range = f"E{row_number}:G{row_number}"
                else:
                    value_format = "#,##0.00"
                    value_range = f"E{row_number}:G{row_number}"
                cell_styles.append(
                    {"range": value_range, "number_format": value_format}
                )
        styles.append({"name": sheet["name"], "cell_styles": cell_styles})
    return {"styles": styles}


def _percentage_metric(metric: str) -> bool:
    return any(marker in metric for marker in ("率", "占比", "比例", "进度"))


def _integer_metric(metric: str) -> bool:
    return any(marker in metric for marker in ("人数", "用户数", "订单量"))


def _column_letter(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _dtype(values: Sequence[Any]) -> str:
    non_null = [_scalar(value) for value in values if value is not None]
    if not non_null:
        return "object"
    if all(isinstance(value, bool) for value in non_null):
        return "bool"
    if all(isinstance(value, Integral) and not isinstance(value, bool) for value in non_null):
        return "int64" if len(non_null) == len(values) else "Int64"
    if all(
        isinstance(value, (Real, Decimal)) and not isinstance(value, bool)
        for value in non_null
    ):
        return "float64"
    if all(isinstance(value, (date, datetime)) for value in non_null):
        return "datetime64[ns]"
    return "object"


def _number_format(column: str, dtype: str) -> str | None:
    if column == "relative_change" or column.endswith("_rate"):
        return "0.00%"
    if dtype in {"int64", "Int64"}:
        return "#,##0"
    if dtype == "float64":
        return "#,##0.00"
    return None


def _scalar(value: Any) -> Any:
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    return value


def _json_value(value: Any) -> Any:
    value = _scalar(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"无法写入飞书的数据类型: {type(value).__name__}")


def _created_url(response: Mapping[str, Any]) -> str:
    data = response.get("data")
    if not isinstance(data, Mapping):
        return ""
    spreadsheet = data.get("spreadsheet")
    if isinstance(spreadsheet, Mapping) and isinstance(spreadsheet.get("url"), str):
        return spreadsheet["url"]
    return data.get("url") if isinstance(data.get("url"), str) else ""


def _readback_structure_matches(expected: Mapping[str, Any], actual: Any) -> bool:
    if not isinstance(actual, Mapping) or not isinstance(actual.get("sheets"), list):
        return False
    expected_sheets = expected["sheets"]
    actual_sheets = actual["sheets"]
    if not all(isinstance(sheet, Mapping) for sheet in actual_sheets):
        return False
    if [sheet.get("name") for sheet in actual_sheets] != list(SHEET_ORDER):
        return False
    if len(expected_sheets) != len(actual_sheets):
        return False

    actual_by_name = {sheet.get("name"): sheet for sheet in actual_sheets}
    for expected_sheet in expected_sheets:
        actual_sheet = actual_by_name.get(expected_sheet["name"])
        if not isinstance(actual_sheet, Mapping):
            return False
        if actual_sheet.get("columns") != expected_sheet["columns"]:
            return False
        used_range = _parse_a1_range(actual_sheet.get("range"))
        if used_range != (
            1,
            1,
            len(expected_sheet["columns"]),
            len(expected_sheet["data"]) + 1,
        ):
            return False
    return True


def _sentinel_rows(
    expected: Mapping[str, Any],
) -> list[tuple[Mapping[str, Any], int]]:
    expected_by_name = {sheet["name"]: sheet for sheet in expected["sheets"]}
    names = ["检查结果", "经营总览"]
    detail_names: list[str] = []
    for name in ("用户分层", "销售承接"):
        sheet = expected_by_name[name]
        if sheet["data"]:
            detail_names.append(name)
    if len(detail_names) < 2:
        for name in SHEET_ORDER[2:10]:
            if name not in detail_names and expected_by_name[name]["data"]:
                detail_names.append(name)
                if len(detail_names) == 2:
                    break
    names.extend(detail_names)

    sentinels: list[tuple[Mapping[str, Any], int]] = []
    for name in names:
        sheet = expected_by_name[name]
        row_count = len(sheet["data"])
        if not row_count:
            continue
        for row_index in sorted({0, row_count // 2, row_count - 1}):
            sentinels.append((sheet, row_index))
    return sentinels


_A1_RANGE = re.compile(r"^([A-Z]+)([1-9]\d*):([A-Z]+)([1-9]\d*)$")


def _parse_a1_range(value: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(value, str):
        return None
    match = _A1_RANGE.fullmatch(value)
    if match is None:
        return None
    start_column, start_row, end_column, end_row = match.groups()
    return (
        _column_number(start_column),
        int(start_row),
        _column_number(end_column),
        int(end_row),
    )


def _column_number(letters: str) -> int:
    number = 0
    for letter in letters:
        number = number * 26 + ord(letter) - ord("A") + 1
    return number


def _sentinel_matches(
    expected_sheet: Mapping[str, Any], expected_row: Sequence[Any], actual_row: Any
) -> bool:
    if not isinstance(actual_row, list) or len(actual_row) != len(expected_row):
        return False
    dtypes = expected_sheet.get("dtypes", {})
    for column, expected, actual in zip(
        expected_sheet["columns"], expected_row, actual_row, strict=True
    ):
        if dtypes.get(column) == "datetime64[ns]" or column == "data_updated_at":
            if expected is None or actual is None:
                if expected != actual:
                    return False
                continue
            expected_date = _iso_date(expected)
            actual_date = _iso_date(actual)
            if (
                expected_date is None
                or actual_date is None
                or expected_date != actual_date
            ):
                return False
        elif isinstance(expected, bool) or isinstance(actual, bool):
            if (
                type(expected) is not bool
                or type(actual) is not bool
                or expected != actual
            ):
                return False
        elif (
            dtypes.get(column) == "object"
            and isinstance(expected, (Integral, Real, Decimal))
            and not isinstance(expected, bool)
            and isinstance(actual, str)
        ):
            if not _finite_numeric_string_matches(expected, actual):
                return False
        elif (
            isinstance(expected, (Real, Decimal))
            and not isinstance(expected, bool)
            and isinstance(actual, (Real, Decimal))
            and not isinstance(actual, bool)
        ):
            if not _numeric_values_match(expected, actual):
                return False
        elif expected != actual:
            return False
    return True


_JSON_NUMBER = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$")


def _numeric_values_match(
    expected: Real | Decimal, actual: Real | Decimal
) -> bool:
    if isinstance(expected, Decimal) or isinstance(actual, Decimal):
        expected_decimal = _exact_decimal(expected)
        actual_decimal = _exact_decimal(actual)
        return (
            expected_decimal is not None
            and actual_decimal is not None
            and expected_decimal == actual_decimal
        )
    if isinstance(expected, Integral) or isinstance(actual, Integral):
        if (
            isinstance(expected, Real)
            and not isinstance(expected, Integral)
            and not math.isfinite(float(expected))
        ):
            return False
        if (
            isinstance(actual, Real)
            and not isinstance(actual, Integral)
            and not math.isfinite(float(actual))
        ):
            return False
        return expected == actual
    return (
        math.isfinite(float(expected))
        and math.isfinite(float(actual))
        and math.isclose(
            float(expected),
            float(actual),
            rel_tol=0.0,
            abs_tol=1e-12,
        )
    )


def _exact_decimal(value: Real | Decimal) -> Decimal | None:
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, Integral):
        return Decimal(int(value))
    numeric = float(value)
    if not math.isfinite(numeric):
        return None
    return Decimal.from_float(numeric)


def _finite_numeric_string_matches(expected: Real | Decimal, actual: str) -> bool:
    if _JSON_NUMBER.fullmatch(actual) is None:
        return False
    try:
        if isinstance(expected, Decimal):
            expected_number = expected
        elif isinstance(expected, Integral):
            expected_number = Decimal(int(expected))
        else:
            expected_number = Decimal(str(float(expected)))
        actual_number = Decimal(actual)
    except (InvalidOperation, OverflowError, ValueError):
        return False
    return (
        expected_number.is_finite()
        and actual_number.is_finite()
        and expected_number == actual_number
    )


def _iso_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    timestamp = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(timestamp).date()
    except ValueError:
        return None


__all__ = ["LarkWorkbookWriter"]
