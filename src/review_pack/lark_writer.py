"""Create a type-faithful Lark review workbook and verify it by reading it back."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
import json
from numbers import Integral, Real
import os
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

        readback = self.command_runner(
            [
                "lark-cli",
                "sheets",
                "+table-get",
                "--url",
                url,
                "--format",
                "json",
            ],
            None,
        )
        if readback.get("ok") is not True or not _readback_matches(
            payload, readback.get("data")
        ):
            raise RuntimeError("回读验证失败，本地快照已保留")

        result.lark_url = url
        return url

    def _require_verified_user(self) -> None:
        status = self.command_runner(
            ["lark-cli", "auth", "status", "--json", "--verify"], None
        )
        user = status.get("identities", {}).get("user", {})
        user_verified = user.get("verified") is True or (
            user.get("status") == "active" and user.get("tokenStatus") != "invalid"
        )
        if status.get("verified") is not True or not (
            status.get("identity") == "user" or user_verified
        ):
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


def _readback_matches(expected: Mapping[str, Any], actual: Any) -> bool:
    if not isinstance(actual, Mapping) or not isinstance(actual.get("sheets"), list):
        return False
    expected_sheets = expected["sheets"]
    actual_sheets = actual["sheets"]
    if [sheet.get("name") for sheet in actual_sheets] != list(SHEET_ORDER):
        return False
    if len(expected_sheets) != len(actual_sheets):
        return False

    actual_by_name = {sheet.get("name"): sheet for sheet in actual_sheets}
    for expected_sheet in expected_sheets:
        actual_sheet = actual_by_name.get(expected_sheet["name"])
        if not isinstance(actual_sheet, Mapping):
            return False
        actual_rows = actual_sheet.get("data")
        if not isinstance(actual_rows, list) or len(actual_rows) != len(
            expected_sheet["data"]
        ):
            return False

    sentinel_names = ["检查结果", "经营总览"]
    detail_candidates = [
        sheet["name"]
        for sheet in expected_sheets
        if sheet["name"] not in {"检查结果", "经营总览", "指标口径", "运行记录"}
        and sheet["data"]
    ]
    sentinel_names.extend(detail_candidates[:2])
    expected_by_name = {sheet["name"]: sheet for sheet in expected_sheets}
    for name in sentinel_names:
        expected_rows = expected_by_name[name]["data"]
        if expected_rows and actual_by_name[name].get("data", [None])[0] != expected_rows[0]:
            return False
    return True


__all__ = ["LarkWorkbookWriter"]
