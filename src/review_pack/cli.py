"""One-command orchestration for review data packs."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Callable, Sequence, TextIO

from executor import SQLExecutor

from .catalog import MODULE_SPECS, campaign_defaults
from .lark_writer import LarkWorkbookWriter
from .models import CheckResult, ReviewPackResult, ReviewRequest
from .runner import ReviewPackRunner, sql_executor_query_runner
from .validation import validate_pack


PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUERY_ROOT = PROJECT_ROOT / "queries" / "review_pack"
OUTPUT_ROOT = PROJECT_ROOT / "outputs"

RunnerFactory = Callable[[bool], ReviewPackRunner]
WriterFactory = Callable[[], LarkWorkbookWriter]


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(f"命令参数不正确: {message}")


def build_parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(description="生成一键复盘数据包")
    parser.add_argument("--name", required=True, help="活动名称")
    parser.add_argument("--start", required=True, help="活动开始日期 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="活动截止日期 YYYY-MM-DD")
    parser.add_argument("--target", required=True, help="活动目标，例如 1.2亿")
    parser.add_argument("--deposit-source-start")
    parser.add_argument("--deposit-source-end")
    parser.add_argument("--reservoir-source-start")
    parser.add_argument("--reservoir-source-end")
    parser.add_argument("--sample", action="store_true", help="使用示例数据且不写飞书")
    parser.add_argument("--dry-run", action="store_true", help="只生成并检查本地快照")
    return parser


def _request_from_args(args: argparse.Namespace) -> ReviewRequest:
    defaults = campaign_defaults(args.name)
    deposit = _source_window(
        args.deposit_source_start,
        args.deposit_source_end,
        defaults.get("deposit_source"),
    )
    reservoir = _source_window(
        args.reservoir_source_start,
        args.reservoir_source_end,
        defaults.get("reservoir_source"),
    )
    return ReviewRequest.create(
        args.name,
        args.start,
        args.end,
        args.target,
        deposit_source_start=deposit[0],
        deposit_source_end=deposit[1],
        reservoir_source_start=reservoir[0],
        reservoir_source_end=reservoir[1],
    )


def _source_window(
    explicit_start: str | None,
    explicit_end: str | None,
    configured: Sequence[str] | None,
) -> tuple[str | None, str | None]:
    if explicit_start is not None or explicit_end is not None:
        return explicit_start, explicit_end
    if configured is None:
        return None, None
    if len(configured) != 2:
        raise ValueError("活动策略来源日期配置格式不正确")
    return configured[0], configured[1]


def _production_runner() -> ReviewPackRunner:
    config_path = PROJECT_ROOT / "config.json"
    if not config_path.is_file():
        raise ValueError("数据库配置不存在，请先准备 config.json")
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("数据库配置无法读取") from exc
    executor = SQLExecutor(config)
    return ReviewPackRunner(sql_executor_query_runner(executor), QUERY_ROOT, OUTPUT_ROOT)


def _sample_runner() -> ReviewPackRunner:
    def query(module_name: str, _sql: str) -> list[dict[str, Any]]:
        spec = next(spec for spec in MODULE_SPECS if spec.name == module_name)
        rows = []
        for metric in spec.metrics:
            value = _sample_value(module_name, metric)
            for period, updated_at in (
                ("本期", "2026-07-15"),
                ("去年同期", "2025-07-15"),
            ):
                rows.append(
                    {
                        "period": period,
                        "channel": "私域整体",
                        "dimension_type": "总览",
                        "dimension_value": "全部",
                        "metric": metric,
                        "value": value,
                        "source_version": "sample-v1",
                        "data_updated_at": updated_at,
                        "definition_id": f"sample-{module_name}-{metric}",
                    }
                )
        return rows

    return ReviewPackRunner(query, QUERY_ROOT, OUTPUT_ROOT)


def _sample_value(module: str, metric: str) -> float:
    values = {
        "overview": {
            "营收": 100,
            "活动目标": 100,
            "目标完成额": 100,
            "目标完成率": 1,
            "目标差额": 0,
            "时间进度": 0.5,
            "营收进度与时间进度差": 0.5,
            "服务期营收": 100,
            "业务营收与服务期营收差额": 0,
        },
        "active_efficiency": {
            "活跃人数": 100,
            "付费人数": 50,
            "付费金额": 5000,
            "付费转化率": 0.5,
            "客单价": 100,
            "ARPU": 50,
            "活跃人数占比": 1,
            "付费人数占比": 1,
            "营收占比": 1,
        },
        "user_stage": {
            "活跃人数": 100,
            "付费人数": 50,
            "付费金额": 5000,
            "付费转化率": 0.5,
            "客单价": 100,
            "ARPU": 50,
            "活跃人数占比": 1,
            "付费人数占比": 1,
            "营收占比": 1,
            "组合品付费人数": 25,
            "组合品订单量": 25,
            "组合品营收": 2500,
            "组合品转化率": 0.25,
            "组合品客单价": 100,
            "组合品ARPU": 25,
        },
        "product_structure": {
            "订单量": 50,
            "付费人数": 50,
            "营收": 5000,
            "订单占比": 1,
            "付费人数占比": 1,
            "营收占比": 1,
            "转化率": 0.5,
            "客单价": 100,
            "ARPU": 50,
        },
        "deposit": {
            "定金来源用户数": 100,
            "定金订单量": 100,
            "定金金额": 1000,
            "尾款人数": 50,
            "尾款订单量": 50,
            "尾款营收": 5000,
            "尾款率": 0.5,
            "尾款营收占整体营收比例": 0.5,
            "转组合品人数": 50,
            "转组合品订单量": 50,
            "转组合品营收": 5000,
            "转498人数": 0,
            "转498订单量": 0,
            "转498营收": 0,
            "转其他商品人数": 0,
            "转其他商品订单量": 0,
            "转其他商品营收": 0,
            "未转化人数": 50,
        },
        "reservoir": {
            "蓄水来源用户数": 100,
            "蓄水订单量": 100,
            "蓄水金额": 1000,
            "转大人数": 50,
            "转大订单量": 50,
            "转大营收": 5000,
            "转大率": 0.5,
            "活跃蓄水用户数": 50,
            "非活跃蓄水用户数": 50,
            "活跃蓄水用户转大率": 0.5,
            "非活跃蓄水用户转大率": 0.5,
            "转化商品流向": 50,
        },
        "high_value": {
            "来源用户数": 100,
            "活跃人数": 100,
            "付费人数": 50,
            "订单量": 50,
            "营收": 5000,
            "付费转化率": 0.5,
            "客单价": 100,
            "ARPU": 50,
            "组合品付费人数": 25,
            "组合品订单量": 25,
            "组合品营收": 2500,
            "组合品转化率": 0.25,
            "高净值营收占私域营收比例": 0.5,
        },
        "sales_funnel": {
            "线索领取人数": 100,
            "线索领取率": 0.5,
            "电话拨打人数": 80,
            "有效接通人数": 60,
            "有效接通率": 0.75,
            "未有效接通人数": 20,
            "企微添加人数": 50,
            "企微添加率": 0.5,
            "转化人数": 50,
            "转化率": 0.5,
            "转化营收": 5000,
            "客单价": 100,
            "ARPU": 50,
            "有效接通后转化人数": 30,
            "有效接通后转化率": 0.5,
            "有效接通后营收": 3000,
            "有效接通后客单价": 100,
            "有效接通后ARPU": 50,
            "未有效接通后转化人数": 20,
            "未有效接通后转化率": 1,
            "未有效接通后营收": 2000,
            "未有效接通后客单价": 100,
            "未有效接通后ARPU": 100,
        },
    }
    return values[module][metric]


def _default_runner_factory(sample: bool) -> ReviewPackRunner:
    return _sample_runner() if sample else _production_runner()


def _configuration_checks(request: ReviewRequest) -> list[CheckResult]:
    checks = []
    if request.deposit_source_start is None:
        checks.append(
            CheckResult(
                "strategy_window_config",
                "error",
                "failed",
                "deposit",
                "未配置定金来源期；请提供 --deposit-source-start 和 --deposit-source-end",
            )
        )
    if request.reservoir_source_start is None:
        checks.append(
            CheckResult(
                "strategy_window_config",
                "error",
                "failed",
                "reservoir",
                "未配置蓄水来源期；请提供 --reservoir-source-start 和 --reservoir-source-end",
            )
        )
    return checks


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    raise TypeError(f"无法写入 JSON 的数据类型: {type(value).__name__}")


def _update_snapshot(result: ReviewPackResult) -> None:
    if not result.local_snapshot:
        return
    path = Path(result.local_snapshot)
    if not path.is_file():
        return
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".review_pack.cli.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary_path = Path(output.name)
            json.dump(
                asdict(result),
                output,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                default=_json_default,
            )
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _try_update_snapshot(result: ReviewPackResult) -> str | None:
    try:
        _update_snapshot(result)
    except Exception:
        return "本地快照更新失败；飞书表格状态不受影响，请勿因此重复创建"
    return None


def _summary(
    result: ReviewPackResult,
    ok: bool = True,
    snapshot_warnings: Sequence[str] = (),
) -> dict[str, Any]:
    check_summary = {"passed": 0, "warning": 0, "failed": 0}
    for check in result.checks:
        if check.status in check_summary:
            check_summary[check.status] += 1
    configuration_errors = [
        check.message
        for check in result.checks
        if check.check_id == "strategy_window_config" and check.status == "failed"
    ]
    failed_modules = {
        name for name, module in result.modules.items() if module.status == "failed"
    }
    failed_modules.update(
        check.module
        for check in result.checks
        if check.status == "failed" and check.check_id == "strategy_window_config"
    )
    request = result.request
    payload: dict[str, Any] = {
        "ok": ok,
        "activity": request.name,
        "current_period": f"{request.start.isoformat()}~{request.end.isoformat()}",
        "last_year_period": (
            f"{request.last_year_start.isoformat()}~{request.last_year_end.isoformat()}"
        ),
        "source_windows": {
            "deposit": _format_window(
                request.deposit_source_start, request.deposit_source_end
            ),
            "reservoir": _format_window(
                request.reservoir_source_start, request.reservoir_source_end
            ),
        },
        "modules": {name: module.status for name, module in result.modules.items()},
        "check_summary": check_summary,
        "failed_modules": sorted(failed_modules),
        "configuration_errors": configuration_errors,
        "snapshot_warnings": list(snapshot_warnings),
        "local_snapshot": result.local_snapshot,
    }
    if result.lark_url:
        payload["lark_url"] = result.lark_url
    return payload


def _format_window(start: date | None, end: date | None) -> str | None:
    if start is None or end is None:
        return None
    return f"{start.isoformat()}~{end.isoformat()}"


def _emit(payload: dict[str, Any], stdout: TextIO) -> None:
    stdout.write(json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n")


def main(
    argv: Sequence[str] | None = None,
    *,
    runner_factory: RunnerFactory | None = None,
    writer_factory: WriterFactory | None = None,
    stdout: TextIO | None = None,
) -> int:
    stdout = stdout or sys.stdout
    try:
        args = build_parser().parse_args(argv)
        request = _request_from_args(args)
        runner = (runner_factory or _default_runner_factory)(args.sample)
    except (TypeError, ValueError) as exc:
        _emit({"ok": False, "error_type": "invalid_input", "message": str(exc)}, stdout)
        return 2

    runner_output = io.StringIO()
    try:
        with redirect_stdout(runner_output), redirect_stderr(runner_output):
            result = runner.run(request)
    except Exception:
        _emit(
            {
                "ok": False,
                "error_type": "runner_failed",
                "message": "数据模块执行失败，未生成可用结果",
            },
            stdout,
        )
        return 3
    result.checks = validate_pack(result)
    result.checks.extend(_configuration_checks(request))
    snapshot_warnings = []
    if warning := _try_update_snapshot(result):
        snapshot_warnings.append(warning)

    if not any(module.status == "success" for module in result.modules.values()):
        payload = _summary(result, ok=False, snapshot_warnings=snapshot_warnings)
        payload["error_type"] = "all_modules_failed"
        _emit(payload, stdout)
        return 3

    if not args.dry_run and not args.sample:
        try:
            writer = (writer_factory or LarkWorkbookWriter)()
            result.lark_url = writer.write(result)
        except Exception:
            payload = _summary(
                result, ok=False, snapshot_warnings=snapshot_warnings
            )
            payload["error_type"] = "lark_write_failed"
            payload["message"] = "飞书写入或回读失败，本地快照已保留"
            _emit(payload, stdout)
            return 4
        if warning := _try_update_snapshot(result):
            snapshot_warnings.append(warning)

    _emit(_summary(result, snapshot_warnings=snapshot_warnings), stdout)
    return 0


__all__ = ["build_parser", "main"]
