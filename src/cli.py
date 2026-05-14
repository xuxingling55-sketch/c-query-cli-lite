# -*- coding: utf-8 -*-
"""轻量 SQL 执行 CLI：读取 SQL 文件，校验，执行，导出 Excel。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

try:
    from rich.console import Console
    from rich.table import Table
except ModuleNotFoundError:
    Console = None
    Table = None

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

console = Console() if Console else None


def print_msg(message: str) -> None:
    if console:
        console.print(message)
    else:
        print(re.sub(r"\[[a-zA-Z/ ]+\]", "", message))


def load_config() -> dict:
    config_path = os.path.join(PROJECT_ROOT, "config.json")
    if not os.path.isfile(config_path):
        print_msg(
            f"[red]配置文件不存在: {config_path}[/red]\n"
            "请先复制 config.example.json 为 config.json，并填入数据库账号密码。"
        )
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def cmd_run(args) -> None:
    sql_path = args.sql_file
    if not os.path.isabs(sql_path):
        sql_path = os.path.join(os.getcwd(), sql_path)
    if not os.path.isfile(sql_path):
        print_msg(f"[red]SQL 文件不存在: {sql_path}[/red]")
        sys.exit(1)

    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()

    from executor import SQLExecutor, export_excel, validate_sql

    config = load_config()
    max_limit = int(config.get("max_limit", 10000))
    is_valid, msg, sanitized_sql = validate_sql(sql, max_limit=max_limit)
    if not is_valid:
        print_msg(f"[red]安全校验未通过: {msg}[/red]")
        sys.exit(1)

    executor = SQLExecutor(config)
    if args.engine == "spark":
        print_msg("[dim]强制使用 SparkSQL[/dim]")
        start = time.time()
        with _status("正在执行 SQL（SparkSQL）..."):
            df = executor._execute_sparksql("-- Engine: Spark\n" + sanitized_sql)
        elapsed = time.time() - start
        engine = "SparkSQL"
    elif args.engine == "starrocks":
        print_msg("[dim]强制使用 StarRocks[/dim]")
        start = time.time()
        with _status("正在执行 SQL（StarRocks）..."):
            df = executor._execute_starrocks(sanitized_sql)
        elapsed = time.time() - start
        engine = "StarRocks"
    else:
        with _status("正在执行 SQL..."):
            df, engine, elapsed = executor.execute(sanitized_sql)

    print_msg(
        f"  引擎: [cyan]{engine}[/cyan]  "
        f"行数: [cyan]{len(df)}[/cyan]  "
        f"耗时: [cyan]{elapsed:.1f}s[/cyan]"
    )
    _print_preview(df)

    query_dir = _create_query_dir(config, sql_path, args.output)
    with open(os.path.join(query_dir, "query.sql"), "w", encoding="utf-8") as f:
        f.write(sanitized_sql)
    excel_path = os.path.join(query_dir, "result.xlsx")
    export_excel(df, excel_path)
    _write_metadata(query_dir, sql_path, engine, elapsed, len(df), args.output)
    print_msg(f"\n[green]结果已保存到: {query_dir}[/green]")


def cmd_history(args) -> None:
    config = load_config()
    queries_dir = os.path.join(PROJECT_ROOT, config.get("queries_dir", "./queries"))
    if not os.path.isdir(queries_dir):
        print_msg("[yellow]暂无执行记录[/yellow]")
        return

    dirs = sorted(
        [d for d in os.listdir(queries_dir) if os.path.isdir(os.path.join(queries_dir, d))],
        reverse=True,
    )[:20]
    if not dirs:
        print_msg("[yellow]暂无执行记录[/yellow]")
        return

    if Table is None or console is None:
        for dirname in dirs:
            meta_path = os.path.join(queries_dir, dirname, "query.json")
            if os.path.isfile(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    print(json.dumps(json.load(f), ensure_ascii=False))
        return

    table = Table(title="最近执行记录", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("时间", width=18)
    table.add_column("SQL 文件", min_width=20)
    table.add_column("引擎", width=12)
    table.add_column("行数", width=8, justify="right")
    table.add_column("耗时", width=8, justify="right")
    for i, dirname in enumerate(dirs, 1):
        meta_path = os.path.join(queries_dir, dirname, "query.json")
        if not os.path.isfile(meta_path):
            continue
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        table.add_row(
            str(i),
            meta.get("timestamp", "")[:16],
            meta.get("sql_file", ""),
            meta.get("engine", "-"),
            str(meta.get("rows", "-")),
            f"{meta.get('elapsed_seconds', 0)}s",
        )
    console.print(table)


def cmd_knowledge(args) -> None:
    from knowledge import get_knowledge_info, list_domains

    config = load_config() if os.path.isfile(os.path.join(PROJECT_ROOT, "config.json")) else {}
    info = get_knowledge_info(config)
    print_msg(json.dumps({**info, "available_domains": list_domains(config)}, ensure_ascii=False, indent=2))


def _print_preview(df) -> None:
    if df.empty or Table is None or console is None:
        return
    preview = Table(title=f"前 {min(10, len(df))} 行预览", show_lines=True)
    for col in df.columns:
        preview.add_column(str(col))
    for _, row in df.head(10).iterrows():
        preview.add_row(*[str(v) for v in row.values])
    console.print(preview)


class _PlainStatus:
    def __init__(self, message: str):
        self.message = message

    def __enter__(self):
        print(self.message)

    def __exit__(self, exc_type, exc, traceback):
        return False


def _status(message: str):
    if console:
        return console.status(f"[bold green]{message}")
    return _PlainStatus(message)


def _create_query_dir(config: dict, sql_path: str, output_name: str) -> str:
    queries_dir = os.path.join(PROJECT_ROOT, config.get("queries_dir", "./queries"))
    timestamp = time.strftime("%Y-%m-%d_%H-%M")
    name = output_name or os.path.splitext(os.path.basename(sql_path))[0]
    name = re.sub(r'[\\/:*?"<>|]', "", name)[:30]
    query_dir = os.path.join(queries_dir, f"{timestamp}_{name}")
    os.makedirs(query_dir, exist_ok=True)
    return query_dir


def _write_metadata(query_dir: str, sql_path: str, engine: str, elapsed: float, rows: int, output: str) -> None:
    meta = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sql_file": os.path.basename(sql_path),
        "engine": engine,
        "rows": rows,
        "elapsed_seconds": round(elapsed, 2),
        "output": output or os.path.splitext(os.path.basename(sql_path))[0],
    }
    with open(os.path.join(query_dir, "query.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="C端轻量 SQL 执行工具")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="执行 SQL 文件")
    run_parser.add_argument("sql_file", help="SQL 文件路径")
    run_parser.add_argument("-o", "--output", default="", help="输出名称，默认取 SQL 文件名")
    run_parser.add_argument("--engine", choices=["auto", "starrocks", "spark"], default="auto", help="指定执行引擎")

    subparsers.add_parser("history", help="查看执行记录")
    subparsers.add_parser("knowledge", help="查看知识库信息")

    args = parser.parse_args()
    if args.command == "run":
        cmd_run(args)
    elif args.command == "history":
        cmd_history(args)
    elif args.command == "knowledge":
        cmd_knowledge(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
