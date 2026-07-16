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

        self.verify(url, payload)

        result.lark_url = url
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
                target = "学段表现" if row.get("dimension_type") == "学段" else "用户分层"
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
                    "definition_id": row.get("definition_id"),
                    "source_version": row.get("source_version", module.source_version),
                }
            )
    records["指标口径"] = definitions

    request = result.request
    records["运行记录"] = [
        {
            "activity": request.name,
            "current_date_range": f"{request.start.isoformat()}/{request.end.isoformat()}",
            "last_year_date_range": (
                f"{request.last_year_start.isoformat()}/{request.last_year_end.isoformat()}"
            ),
            "period_days": request.period_days,
            "target_amount": request.target_amount,
            "module": module_name,
            "module_status": module.status,
            "row_count": len(module.rows),
            "source_version": module.source_version,
        }
        for module_name, module in result.modules.items()
    ]

    sheets = []
    for name in SHEET_ORDER:
        if name == "检查结果":
            preferred = _CHECK_COLUMNS
        elif name == "指标口径":
            preferred = ("module", "metric", "definition_id", "source_version")
        elif name == "运行记录":
            preferred = (
                "activity",
                "current_date_range",
                "last_year_date_range",
                "period_days",
                "target_amount",
                "module",
                "module_status",
                "row_count",
                "source_version",
            )
        else:
            preferred = _BUSINESS_COLUMNS
        sheets.append(_typed_sheet(name, records[name], preferred))
    return {"sheets": sheets}


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
            if not (
                math.isfinite(float(expected))
                and math.isfinite(float(actual))
                and math.isclose(
                    float(expected),
                    float(actual),
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                )
            ):
                return False
        elif expected != actual:
            return False
    return True


_JSON_NUMBER = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$")


def _finite_numeric_string_matches(expected: Real | Decimal, actual: str) -> bool:
    if _JSON_NUMBER.fullmatch(actual) is None:
        return False
    try:
        expected_number = Decimal(str(_json_value(expected)))
        actual_number = Decimal(actual)
    except (InvalidOperation, ValueError):
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
