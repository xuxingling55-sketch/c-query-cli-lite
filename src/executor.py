# -*- coding: utf-8 -*-
"""SQL 执行器：StarRocks 优先，超时或失败后切换 SparkSQL。"""

from __future__ import annotations

import os
import re
import time

import pandas as pd

DANGEROUS_KEYWORDS = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|TRUNCATE|REPLACE|MERGE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)
PARTITION_FILTER = re.compile(
    r"\b(dt|p_date|pt|day|paid_time_sk)\b\s*(between|=|>=|<=|>|<|in\b)",
    re.IGNORECASE,
)
DEFAULT_TIMEOUT = 900
DEFAULT_MAX_LIMIT = 10000


def validate_sql(sql: str, max_limit: int = DEFAULT_MAX_LIMIT) -> tuple[bool, str, str]:
    """安全校验：只允许 SELECT / WITH 查询，并强制时间过滤和 LIMIT 上限。"""
    stripped = sql.strip().rstrip(";")

    danger = DANGEROUS_KEYWORDS.search(stripped)
    if danger:
        return False, f"检测到危险关键字: {danger.group()}", sql

    check = re.sub(r"--[^\n]*\n?", "", stripped).strip().upper()
    if not (check.startswith("SELECT") or check.startswith("WITH")):
        return False, "仅支持 SELECT / WITH 查询语句", sql

    if re.search(r"\bSELECT\s+\*", stripped, re.IGNORECASE):
        return False, "禁止 SELECT *，请列出具体字段", sql

    if not PARTITION_FILTER.search(stripped):
        return False, "SQL 必须包含明确的时间或分区过滤", sql

    if re.search(r"\bJOIN\b", stripped, re.IGNORECASE) and not re.search(
        r"\bON\b", stripped, re.IGNORECASE
    ):
        return False, "SQL 使用 JOIN 时必须显式 ON 条件", sql

    limit_match = re.search(r"\bLIMIT\s+(\d+)\b", stripped, re.IGNORECASE)
    if not limit_match:
        stripped += f"\nLIMIT {max_limit}"
    elif int(limit_match.group(1)) > max_limit:
        return False, f"LIMIT 不能超过 {max_limit}", sql

    return True, "校验通过", stripped


class SQLExecutor:
    def __init__(self, config: dict):
        self.sr_config = config.get("starrocks", {})
        self.spark_config = config.get("sparksql", {})
        self.timeout = int(config.get("engine_timeout_seconds", DEFAULT_TIMEOUT))

    def execute(self, sql: str) -> tuple[pd.DataFrame, str, float]:
        """执行 SQL，返回 DataFrame、实际引擎、耗时秒数。"""
        start = time.time()
        try:
            df = self._execute_starrocks(sql)
            return df, "StarRocks", time.time() - start
        except _TimeoutError:
            print(f"[引擎切换] StarRocks 超时（>{self.timeout}s），切换到 SparkSQL...")
            start = time.time()
            df = self._execute_sparksql("-- Engine: Spark\n" + sql)
            return df, "SparkSQL", time.time() - start
        except Exception as exc:
            print(f"[引擎切换] StarRocks 执行失败（{exc}），尝试 SparkSQL...")
            start = time.time()
            df = self._execute_sparksql("-- Engine: Spark\n" + sql)
            return df, "SparkSQL", time.time() - start

    def _execute_starrocks(self, sql: str) -> pd.DataFrame:
        import pymysql

        cfg = self.sr_config
        conn = pymysql.connect(
            host=cfg["host"],
            port=cfg.get("port", 9030),
            user=cfg["user"],
            password=cfg["password"],
            database=cfg.get("database", "hive.aws"),
            charset="utf8mb4",
            read_timeout=self.timeout,
            connect_timeout=30,
        )
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        except pymysql.err.OperationalError as exc:
            if "timed out" in str(exc).lower() or exc.args[0] in (2013, 2006):
                raise _TimeoutError(str(exc)) from exc
            raise
        finally:
            conn.close()

        return pd.DataFrame(rows) if rows else pd.DataFrame()

    def _execute_sparksql(self, sql: str) -> pd.DataFrame:
        from impala.dbapi import connect as impala_connect

        cfg = self.spark_config
        conn = impala_connect(
            host=cfg["host"],
            port=cfg.get("port", 10010),
            auth_mechanism="PLAIN",
            user=cfg.get("user", ""),
            password=cfg.get("password", ""),
            database=cfg.get("database", "tmp"),
        )
        try:
            cur = conn.cursor(dictify=True)
            cur.execute(sql)
            rows = cur.fetchall()
        finally:
            conn.close()

        return pd.DataFrame(rows) if rows else pd.DataFrame()


def export_excel(df: pd.DataFrame, output_path: str) -> str:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    df.to_excel(output_path, index=False, engine="openpyxl")
    return output_path


class _TimeoutError(Exception):
    """StarRocks 超时标记，用于触发引擎切换。"""
