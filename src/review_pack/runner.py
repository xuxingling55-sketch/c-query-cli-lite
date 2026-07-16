"""Execute review-pack modules independently and save a local snapshot."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from .catalog import MODULE_SPECS
from .models import ModuleResult, ReviewPackResult, ReviewRequest
from .normalize import pair_periods
from .sql_loader import NotApplicableError, render_sql


QueryRunner = Callable[[str, str], Sequence[dict[str, Any]]]


def sql_executor_query_runner(executor: Any) -> QueryRunner:
    """Adapt the existing SQLExecutor.execute result to review-pack rows."""

    def query_runner(_module: str, sql: str) -> list[dict[str, Any]]:
        frame, _engine, _elapsed = executor.execute(sql)
        return frame.to_dict(orient="records")

    return query_runner


class ReviewPackRunner:
    """Run all fixed review modules without letting one failure stop the pack."""

    def __init__(
        self,
        query_runner: QueryRunner,
        query_root: str | Path,
        output_root: str | Path,
    ) -> None:
        self.query_runner = query_runner
        self.query_root = Path(query_root)
        self.output_root = Path(output_root)

    def run(self, request: ReviewRequest) -> ReviewPackResult:
        modules: dict[str, ModuleResult] = {}
        for module in MODULE_SPECS:
            try:
                sql = render_sql(self.query_root / module.sql_file, request)
                raw_rows = self.query_runner(module.name, sql)
                rows = pair_periods(raw_rows, request)
                modules[module.name] = ModuleResult(
                    module=module.name,
                    status="success",
                    rows=rows,
                )
            except NotApplicableError as exc:
                modules[module.name] = ModuleResult(
                    module=module.name,
                    status="not_applicable",
                    error=str(exc),
                )
            except Exception:
                modules[module.name] = ModuleResult(
                    module=module.name,
                    status="failed",
                    error="query_failed: 模块执行失败",
                )

        result = ReviewPackResult(request=request, modules=modules)
        result.local_snapshot = self._write_snapshot(result)
        return result

    def _write_snapshot(self, result: ReviewPackResult) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        snapshot_dir = self.output_root / "review_pack" / (
            f"{timestamp}_{_safe_name(result.request.name)}"
        )
        snapshot_dir.mkdir(parents=True, exist_ok=False)
        final_path = snapshot_dir / "review_pack.json"
        result.local_snapshot = str(final_path)

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=snapshot_dir,
                prefix=".review_pack.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(
                    asdict(result),
                    temporary_file,
                    ensure_ascii=False,
                    allow_nan=False,
                    indent=2,
                    default=_json_default,
                )
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, final_path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

        return str(final_path)


def _safe_name(name: str) -> str:
    safe = re.sub(r"[^\w.-]+", "_", name, flags=re.UNICODE).strip("._")
    return safe or "review"


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    raise TypeError(f"无法写入 JSON 的数据类型: {type(value).__name__}")
