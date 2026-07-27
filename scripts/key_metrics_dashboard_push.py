#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C端私域关键指标 HTML 看板 + 飞书卡片推送脚本。"""

import argparse
import base64
import html
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zlib
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


# DolphinScheduler 会把脚本复制到临时任务目录执行，当前工作目录才是可写目录。
PROJECT_ROOT = Path.cwd()
OUTPUT_DIR = Path("/tmp/key_metrics_dashboard")
HTML_FILE = OUTPUT_DIR / "index.html"

WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/b693a9df-1207-4daf-af50-6770dba158ed"
MIAODA_APP_ID = "app_1794hcc7266"
KEY_METRICS_DETAIL_URL = "https://guanghe.aiforce.cloud/app/app_1794hcc7266"

REPORT_START = date(2026, 7, 1)
REPORT_END = date(2026, 7, 31)
REPORT_WINDOW_LABEL = "7月"
DEPOSIT_START = date(2026, 6, 24)
DEPOSIT_END = date(2026, 6, 30)
RESERVOIR_START = date(2026, 5, 22)
LAST_YEAR_DEPOSIT_START = date(2025, 6, 25)
LAST_YEAR_DEPOSIT_END = date(2025, 6, 30)

REVENUE_TARGET_WAN = 11306
APP_FLOW_TARGET_USERS = 2300000
DEPOSIT_TARGET_USERS = 12400
RESERVOIR_TARGET_USERS = 40000
FAMILY_ORDER_SHARE_TARGET = 0.20
FROM_PRIMARY_ORDER_SHARE_TARGET = 0.50

DEPOSIT_SKU_GROUP_ID = "74ec057c-4a49-45aa-a0ee-0fd2a410989a"
LAST_YEAR_DEPOSIT_GOOD_KIND_ID_LEVEL_2 = "ee74d649-8e32-452a-a461-65de25560440"

Number = Union[float, int, None]


def yyyymmdd(d: date) -> int:
    return int(d.strftime("%Y%m%d"))


def ymd(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def date_from_int(value: int) -> date:
    return datetime.strptime(str(int(value)), "%Y%m%d").date()


def default_report_day(today: Optional[date] = None) -> date:
    return (today or date.today()) - timedelta(days=1)


def report_start_for(_report_day: date) -> date:
    if _report_day < REPORT_START:
        return _report_day
    return REPORT_START


def report_window_label_for(report_day: date) -> str:
    if report_day < REPORT_START:
        return f"{report_day.month}月{report_day.day}日"
    return REPORT_WINDOW_LABEL


def effective_report_day(report_day: date) -> date:
    return min(report_day, REPORT_END)


def safe_div(numerator: Number, denominator: Number) -> float:
    denominator = float(denominator or 0)
    if denominator == 0:
        return 0
    return float(numerator or 0) / denominator


def days_in_month(d: date) -> int:
    next_month = date(d.year + (1 if d.month == 12 else 0), 1 if d.month == 12 else d.month + 1, 1)
    return (next_month - timedelta(days=1)).day


def format_int(value: Number) -> str:
    return f"{int(round(float(value or 0))):,}"


def format_users(value: Number) -> str:
    return f"{format_int(value)}人"


def format_orders(value: Number) -> str:
    return f"{format_int(value)}单"


def format_wan(value: Number) -> str:
    return f"{float(value or 0) / 10000:.2f}万"


def format_money_wan(value: Number) -> str:
    return f"¥ {float(value or 0) / 10000:.2f}万"


def format_money_yuan(value: Number) -> str:
    return f"¥ {int(round(float(value or 0))):,}"


def format_pct(value: Number) -> str:
    return f"{float(value or 0) * 100:.2f}%"


def load_db_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    path = config_path or PROJECT_ROOT / "config.json"
    if path.is_file():
        config = json.loads(path.read_text(encoding="utf-8"))
    else:
        config = {
            "starrocks": {
                "host": os.environ.get("SR_HOST", ""),
                "port": int(os.environ.get("SR_PORT", "9030")),
                "user": os.environ.get("SR_USER", ""),
                "password": os.environ.get("SR_PASSWORD", ""),
                "database": os.environ.get("SR_DATABASE", ""),
            }
        }

    starrocks = config.get("starrocks", {})
    missing = [key for key in ("host", "user", "password", "database") if not starrocks.get(key)]
    if missing:
        raise RuntimeError("缺少 StarRocks 配置：" + "、".join(missing))
    return config


def format_money_yoy(current: Number, last_year: Number) -> str:
    current_value = float(current or 0)
    last_year_value = float(last_year or 0)
    gap = current_value - last_year_value
    sign = "+" if gap >= 0 else "-"
    gap_text = f"{sign}{abs(gap) / 10000:,.2f}万"
    if last_year_value == 0:
        return f"较去年同比 {gap_text}"
    return f"较去年同比 {gap_text} {gap / last_year_value * 100:+.2f}%"


def format_rate_yoy(current: Number, last_year: Number) -> str:
    current_value = float(current or 0)
    last_year_value = float(last_year or 0)
    gap = current_value - last_year_value
    sign = "+" if gap >= 0 else "-"
    gap_text = f"{sign}{abs(gap) * 100:.2f}pct"
    if last_year_value == 0:
        return f"较去年同比 {gap_text}"
    return f"较去年同比 {gap_text} {gap / last_year_value * 100:+.2f}%"


def format_yuan_yoy(current: Number, last_year: Number) -> str:
    current_value = float(current or 0)
    last_year_value = float(last_year or 0)
    gap = current_value - last_year_value
    sign = "+" if gap >= 0 else "-"
    gap_text = f"{sign}{int(round(abs(gap))):,}元"
    if last_year_value == 0:
        return f"较去年同比 {gap_text}"
    return f"较去年同比 {gap_text} {gap / last_year_value * 100:+.2f}%"


def grey(text: str) -> str:
    return f"<font color='grey'>{text}</font>"


def format_users_yoy(current: Number, last_year: Number) -> str:
    current_value = float(current or 0)
    last_year_value = float(last_year or 0)
    gap = current_value - last_year_value
    sign = "+" if gap >= 0 else "-"
    gap_text = f"{sign}{format_int(abs(gap))}人"
    if last_year_value == 0:
        return f"较去年同比 {gap_text}"
    return f"较去年同比 {gap_text} {gap / last_year_value * 100:+.2f}%"


def progress_bar(value: float, width: int = 36) -> str:
    safe_value = max(0, min(1, float(value or 0)))
    filled = int(round(safe_value * width))
    return "█" * filled + "░" * (width - filled)


def validate_select_sql(sql: str) -> str:
    stripped = sql.strip().rstrip(";")
    check = stripped.lstrip().upper()
    if not (check.startswith("SELECT") or check.startswith("WITH")):
        raise ValueError("仅支持 SELECT / WITH 查询")
    dangerous = ("DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE", "REPLACE", "MERGE")
    for word in dangerous:
        if f" {word} " in f" {check} ":
            raise ValueError(f"检测到危险关键字: {word}")
    return stripped


def _reservoir_condition() -> str:
    return """
good_kind_name_level_2 = '同步课加培优课'
AND good_kind_name_level_3 = '同步课加培优课流量品'
""".strip()


def _from_primary_condition() -> str:
    return "business_good_kind_name_level_3 = '小学品加拓展'"


def _other_goods_condition(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return f"{prefix}sub_amount > 500"


def _reservoir_tail_condition(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return f"{prefix}order_amount >= 500 AND {prefix}business_gmv_attribution IN ('商业化', '电销')"


def key_metrics_sql(report_day: date) -> str:
    start_day_int = yyyymmdd(report_start_for(report_day))
    report_day_int = yyyymmdd(effective_report_day(report_day))
    deposit_start_int = yyyymmdd(DEPOSIT_START)
    deposit_end_int = yyyymmdd(min(DEPOSIT_END, effective_report_day(report_day)))
    reservoir_start_int = yyyymmdd(RESERVOIR_START)
    reservoir_end_int = yyyymmdd(min(DEPOSIT_END, effective_report_day(report_day)))
    reservoir_condition = _reservoir_condition()
    from_primary_condition = _from_primary_condition()
    crm_start = ymd(report_start_for(report_day))
    crm_end = ymd(effective_report_day(report_day))

    return f"""
WITH deposit_channel_users AS (
    SELECT
        TRIM(CAST(u_user AS STRING)) AS u_user,
        CASE
            WHEN business_gmv_attribution = '商业化' THEN 'APP'
            WHEN business_gmv_attribution = '电销' THEN '电销'
            ELSE '其他'
        END AS channel
    FROM dws.topic_order_detail
    WHERE paid_time_sk BETWEEN {deposit_start_int} AND {deposit_end_int}
      AND sku_group_good_id = '{DEPOSIT_SKU_GROUP_ID}'
      AND business_gmv_attribution IN ('商业化', '电销')
    AND u_user IS NOT NULL
    GROUP BY
        TRIM(CAST(u_user AS STRING)),
        CASE
            WHEN business_gmv_attribution = '商业化' THEN 'APP'
            WHEN business_gmv_attribution = '电销' THEN '电销'
            ELSE '其他'
        END
),
deposit_source AS (
    SELECT
        CAST(order_id AS STRING) AS order_id,
        TRIM(CAST(u_user AS STRING)) AS u_user,
        COALESCE(MAX(business_user_pay_status_business_month), '未知') AS user_layer,
        MIN(paid_time) AS source_paid_time,
        SUM(sub_amount) AS source_amount
    FROM dws.topic_order_detail
    WHERE paid_time_sk BETWEEN {deposit_start_int} AND {deposit_end_int}
      AND u_user IS NOT NULL
      AND sku_group_good_id = '{DEPOSIT_SKU_GROUP_ID}'
      AND business_gmv_attribution IN ('商业化', '电销')
    GROUP BY CAST(order_id AS STRING), TRIM(CAST(u_user AS STRING))
),
deposit_user_flags AS (
    SELECT
        u_user,
        MAX(CASE WHEN channel = 'APP' THEN 1 ELSE 0 END) AS is_app_deposit,
        MAX(CASE WHEN channel = '电销' THEN 1 ELSE 0 END) AS is_tele_deposit
    FROM deposit_channel_users
    GROUP BY u_user
),
tele_zhike_double_users AS (
    SELECT DISTINCT
        TRIM(CAST(a.user_id AS STRING)) AS user_id
    FROM aws.crm_order_info a
    LEFT JOIN (
        SELECT
            TRIM(CAST(u_user AS STRING)) AS u_user,
            team_names
        FROM dws.topic_order_detail
        WHERE paid_time_sk BETWEEN {deposit_start_int} AND {deposit_end_int}
          AND sku_group_good_id = '{DEPOSIT_SKU_GROUP_ID}'
          AND u_user IS NOT NULL
        GROUP BY 1, 2
    ) b
      ON TRIM(CAST(a.user_id AS STRING)) = b.u_user
    WHERE SUBSTR(a.pay_time, 1, 10) BETWEEN '{ymd(DEPOSIT_START)}' AND '{ymd(min(DEPOSIT_END, effective_report_day(report_day)))}'
      AND a.good_kind_name_level_3 = '活动定金'
      AND a.workplace_id IN (4, 400, 702)
      AND a.regiment_id NOT IN (303, 0, 546)
      AND a.worker_id <> 0
      AND a.is_test = false
      AND array_contains(b.team_names, '入校')
      AND array_contains(b.team_names, '电销/网销')
),
reservoir_source AS (
    SELECT
        CAST(order_id AS STRING) AS order_id,
        TRIM(CAST(u_user AS STRING)) AS u_user,
        COALESCE(MAX(business_user_pay_status_business_month), '未知') AS user_layer,
        MIN(paid_time) AS source_paid_time,
        SUM(sub_amount) AS source_amount
    FROM dws.topic_order_detail
    WHERE paid_time_sk BETWEEN {reservoir_start_int} AND {reservoir_end_int}
      AND u_user IS NOT NULL
      AND {reservoir_condition}
      AND business_gmv_attribution IN ('商业化', '电销')
    GROUP BY CAST(order_id AS STRING), TRIM(CAST(u_user AS STRING))
),
reservoir_users AS (
    SELECT
        u_user,
        MIN(source_paid_time) AS first_source_paid_time
    FROM reservoir_source
    GROUP BY u_user
),
reservoir_users_total AS (
    SELECT COUNT(DISTINCT u_user) AS total_reservoir_users
    FROM reservoir_users
),
high_value_active_users AS (
    SELECT DISTINCT
        CAST(day AS INT) AS day,
        TRIM(CAST(u_user AS STRING)) AS u_user
    FROM aws.business_active_user_last_14_day
    WHERE day BETWEEN {start_day_int} AND {report_day_int}
      AND business_user_pay_status_business_day = '高净值用户'
      AND u_user IS NOT NULL
),
high_value_active_total AS (
    SELECT COUNT(DISTINCT u_user) AS total_high_value_users
    FROM high_value_active_users
),
deposit_channel_totals AS (
    SELECT
        COUNT(DISTINCT CASE WHEN channel = 'APP' THEN u_user END) AS app_deposit_users,
        COUNT(DISTINCT CASE WHEN channel = '电销' THEN u_user END) AS tele_deposit_users
    FROM deposit_channel_users
),
deposit_double_total AS (
    SELECT COUNT(DISTINCT user_id) AS double_deposit_users
    FROM tele_zhike_double_users
),
deposit_users_total AS (
    SELECT
        dct.app_deposit_users + dct.tele_deposit_users + ddt.double_deposit_users AS total_deposit_users,
        dct.app_deposit_users AS app_deposit_users,
        dct.tele_deposit_users + ddt.double_deposit_users AS tele_deposit_users,
        ddt.double_deposit_users AS tele_zhike_double_deposit_users
    FROM deposit_channel_totals dct
    CROSS JOIN deposit_double_total ddt
),
org_team_dim AS (
    SELECT
        team_id,
        MAX(department_name) AS department_name
    FROM dw.dim_crm_organization
    GROUP BY team_id
),
orders_window AS (
    SELECT
        paid_time_sk,
        paid_time,
        TRIM(CAST(u_user AS STRING)) AS u_user,
        order_id,
        sub_amount,
        original_amount,
        order_amount,
        is_normal_price,
        is_test_user,
        sku_group_good_id,
        good_kind_name_level_1,
        business_good_kind_name_level_1,
        good_kind_name_level_2,
        good_kind_name_level_3,
        business_good_kind_name_level_3,
        good_stage_subject_cnt,
        good_stage_subject,
        business_user_pay_status_business,
        business_gmv_attribution,
        team_id
    FROM dws.topic_order_detail
    WHERE paid_time_sk BETWEEN {start_day_int} AND {report_day_int}
      AND business_gmv_attribution IN ('商业化', '电销')
),
big_order AS (
    SELECT
        TRIM(CAST(u_user AS STRING)) AS u_user,
        MIN(paid_time) AS first_big_paid_time,
        COUNT(DISTINCT order_id) AS big_order_cnt,
        SUM(sub_amount) AS big_amount
    FROM dws.topic_order_detail
    WHERE paid_time_sk BETWEEN {start_day_int} AND {report_day_int}
      AND u_user IS NOT NULL
      AND is_normal_price = 1
      AND original_amount >= 39
      AND business_good_kind_name_level_1 = '组合品'
      AND business_gmv_attribution IN ('商业化', '电销')
    GROUP BY TRIM(CAST(u_user AS STRING))
),
reservoir_big_order AS (
    SELECT
        TRIM(CAST(u_user AS STRING)) AS u_user,
        paid_time_sk,
        MIN(paid_time) AS paid_time,
        CAST(order_id AS STRING) AS order_id,
        SUM(sub_amount) AS big_amount
    FROM dws.topic_order_detail
    WHERE paid_time_sk BETWEEN 20260522 AND {report_day_int}
      AND u_user IS NOT NULL
      AND is_normal_price = 1
      AND original_amount >= 39
      AND business_good_kind_name_level_1 = '组合品'
      AND business_gmv_attribution IN ('商业化', '电销')
    GROUP BY TRIM(CAST(u_user AS STRING)), paid_time_sk, CAST(order_id AS STRING)
),
reservoir_conversion_order AS (
    SELECT
        TRIM(CAST(o.u_user AS STRING)) AS u_user,
        o.paid_time_sk,
        MIN(o.paid_time) AS paid_time,
        CAST(o.order_id AS STRING) AS order_id,
        SUM(o.sub_amount) AS conversion_amount
    FROM dws.topic_order_detail o
    LEFT JOIN reservoir_source rs
      ON TRIM(CAST(o.u_user AS STRING)) = rs.u_user
     AND CAST(o.order_id AS STRING) = rs.order_id
    WHERE o.paid_time_sk BETWEEN 20260522 AND {report_day_int}
      AND o.u_user IS NOT NULL
      AND o.business_gmv_attribution IN ('商业化', '电销')
      AND rs.order_id IS NULL
    GROUP BY TRIM(CAST(o.u_user AS STRING)), o.paid_time_sk, CAST(o.order_id AS STRING)
),
deposit_tail_total AS (
    SELECT
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN d.u_user END) AS total_deposit_tail_users,
        SUM(CASE WHEN b.u_user IS NOT NULL THEN b.big_amount ELSE 0 END) AS total_deposit_tail_revenue
    FROM deposit_source d
    LEFT JOIN big_order b
      ON d.u_user = b.u_user
     AND b.first_big_paid_time >= d.source_paid_time
),
reservoir_tail_total AS (
    SELECT
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN r.u_user END) AS total_reservoir_tail_users,
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN b.order_id END) AS total_reservoir_tail_orders,
        SUM(CASE WHEN b.u_user IS NOT NULL THEN b.big_amount ELSE 0 END) AS total_reservoir_tail_revenue
    FROM reservoir_users r
    LEFT JOIN reservoir_big_order b
      ON r.u_user = b.u_user
     AND b.paid_time_sk BETWEEN {start_day_int} AND {report_day_int}
     AND b.paid_time >= r.first_source_paid_time
),
reservoir_june_tail_total AS (
    SELECT
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN r.u_user END) AS total_reservoir_june_tail_users,
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN b.order_id END) AS total_reservoir_june_tail_orders,
        SUM(CASE WHEN b.u_user IS NOT NULL THEN b.big_amount ELSE 0 END) AS total_reservoir_june_tail_revenue
    FROM reservoir_users r
    LEFT JOIN reservoir_big_order b
      ON r.u_user = b.u_user
     AND b.paid_time_sk BETWEEN 20260601 AND 20260630
     AND b.paid_time >= r.first_source_paid_time
),
reservoir_may_tail_total AS (
    SELECT
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN r.u_user END) AS total_reservoir_may_tail_users,
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN b.order_id END) AS total_reservoir_may_tail_orders,
        SUM(CASE WHEN b.u_user IS NOT NULL THEN b.big_amount ELSE 0 END) AS total_reservoir_may_tail_revenue
    FROM reservoir_users r
    LEFT JOIN reservoir_big_order b
      ON r.u_user = b.u_user
     AND b.paid_time_sk BETWEEN 20260522 AND 20260531
     AND b.paid_time >= r.first_source_paid_time
),
reservoir_total_tail_total AS (
    SELECT
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN r.u_user END) AS total_reservoir_total_tail_users,
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN b.order_id END) AS total_reservoir_total_tail_orders,
        SUM(CASE WHEN b.u_user IS NOT NULL THEN b.big_amount ELSE 0 END) AS total_reservoir_total_tail_revenue
    FROM reservoir_users r
    LEFT JOIN reservoir_big_order b
     ON r.u_user = b.u_user
     AND b.paid_time_sk BETWEEN 20260522 AND {report_day_int}
     AND b.paid_time >= r.first_source_paid_time
),
reservoir_conversion_total AS (
    SELECT
        COUNT(DISTINCT CASE WHEN c.u_user IS NOT NULL THEN r.u_user END) AS total_reservoir_conversion_users,
        COUNT(DISTINCT CASE WHEN c.u_user IS NOT NULL THEN c.order_id END) AS total_reservoir_conversion_orders,
        SUM(CASE WHEN c.u_user IS NOT NULL THEN c.conversion_amount ELSE 0 END) AS total_reservoir_conversion_revenue
    FROM reservoir_users r
    LEFT JOIN reservoir_conversion_order c
      ON r.u_user = c.u_user
     AND c.paid_time_sk BETWEEN 20260522 AND {report_day_int}
     AND c.paid_time >= r.first_source_paid_time
),
reservoir_july_conversion_total AS (
    SELECT
        COUNT(DISTINCT CASE WHEN c.u_user IS NOT NULL THEN r.u_user END) AS total_reservoir_july_conversion_users,
        COUNT(DISTINCT CASE WHEN c.u_user IS NOT NULL THEN c.order_id END) AS total_reservoir_july_conversion_orders,
        SUM(CASE WHEN c.u_user IS NOT NULL THEN c.conversion_amount ELSE 0 END) AS total_reservoir_july_conversion_revenue
    FROM reservoir_users r
    LEFT JOIN reservoir_conversion_order c
      ON r.u_user = c.u_user
     AND c.paid_time_sk BETWEEN {start_day_int} AND {report_day_int}
     AND c.paid_time >= r.first_source_paid_time
),
high_value_renew_total AS (
    SELECT
        COUNT(DISTINCT CASE WHEN o.u_user IS NOT NULL THEN hv.u_user END) AS total_high_value_renew_users,
        SUM(CASE WHEN o.u_user IS NOT NULL THEN o.sub_amount ELSE 0 END) AS total_high_value_renew_revenue
    FROM high_value_active_users hv
    LEFT JOIN orders_window o
      ON hv.u_user = o.u_user
     AND hv.day = o.paid_time_sk
     AND o.business_good_kind_name_level_1 = '组合品'
),
crm_tele_daily AS (
    SELECT
        CAST(REGEXP_REPLACE(SUBSTR(a.pay_time, 1, 10), '-', '') AS INT) AS day,
        SUM(a.amount) AS crm_tele_revenue
    FROM aws.crm_order_info a
    LEFT JOIN dw.dim_crm_organization b
        ON a.workplace_id = b.id
    LEFT JOIN dw.dim_crm_organization c
        ON a.department_id = c.id
    LEFT JOIN dw.dim_crm_organization d
        ON a.regiment_id = d.id
    LEFT JOIN dw.dim_crm_organization e
        ON a.heads_id = e.id
    LEFT JOIN dw.dim_crm_organization f
        ON a.team_id = f.id
    WHERE SUBSTR(a.pay_time, 1, 10) BETWEEN '{crm_start}' AND '{crm_end}'
      AND a.workplace_id IN (4, 400, 702)
      AND a.regiment_id NOT IN (303, 0, 546)
      AND a.worker_id <> 0
      AND a.is_test = false
    GROUP BY CAST(REGEXP_REPLACE(SUBSTR(a.pay_time, 1, 10), '-', '') AS INT)
),
day_base AS (
    SELECT paid_time_sk AS day FROM orders_window
    UNION
    SELECT day FROM crm_tele_daily
    UNION
    SELECT day FROM high_value_active_users
),
deposit_tail_cumulative_by_day AS (
    SELECT
        db.day,
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN d.u_user END) AS cumulative_deposit_tail_users,
        SUM(CASE WHEN b.u_user IS NOT NULL THEN b.big_amount ELSE 0 END) AS cumulative_deposit_tail_revenue
    FROM day_base db
    LEFT JOIN deposit_source d
      ON 1 = 1
    LEFT JOIN big_order b
      ON d.u_user = b.u_user
     AND b.first_big_paid_time >= d.source_paid_time
     AND CAST(REGEXP_REPLACE(SUBSTR(b.first_big_paid_time, 1, 10), '-', '') AS INT) <= db.day
    GROUP BY db.day
),
reservoir_tail_cumulative_by_day AS (
    SELECT
        db.day,
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN r.u_user END) AS cumulative_reservoir_tail_users,
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN b.order_id END) AS cumulative_reservoir_tail_orders,
        SUM(CASE WHEN b.u_user IS NOT NULL THEN b.big_amount ELSE 0 END) AS cumulative_reservoir_tail_revenue
    FROM day_base db
    LEFT JOIN reservoir_users r
      ON 1 = 1
    LEFT JOIN reservoir_big_order b
      ON r.u_user = b.u_user
     AND b.paid_time_sk BETWEEN {start_day_int} AND db.day
     AND b.paid_time >= r.first_source_paid_time
    GROUP BY db.day
),
reservoir_conversion_cumulative_by_day AS (
    SELECT
        db.day,
        COUNT(DISTINCT CASE WHEN c.u_user IS NOT NULL THEN r.u_user END) AS cumulative_reservoir_conversion_users,
        COUNT(DISTINCT CASE WHEN c.u_user IS NOT NULL THEN c.order_id END) AS cumulative_reservoir_conversion_orders,
        SUM(CASE WHEN c.u_user IS NOT NULL THEN c.conversion_amount ELSE 0 END) AS cumulative_reservoir_conversion_revenue,
        COUNT(DISTINCT CASE WHEN c.u_user IS NOT NULL AND c.paid_time_sk >= {start_day_int} THEN r.u_user END) AS cumulative_reservoir_july_conversion_users,
        COUNT(DISTINCT CASE WHEN c.u_user IS NOT NULL AND c.paid_time_sk >= {start_day_int} THEN c.order_id END) AS cumulative_reservoir_july_conversion_orders,
        SUM(CASE WHEN c.u_user IS NOT NULL AND c.paid_time_sk >= {start_day_int} THEN c.conversion_amount ELSE 0 END) AS cumulative_reservoir_july_conversion_revenue
    FROM day_base db
    LEFT JOIN reservoir_users r
      ON 1 = 1
    LEFT JOIN reservoir_conversion_order c
      ON r.u_user = c.u_user
     AND c.paid_time_sk BETWEEN 20260522 AND db.day
     AND c.paid_time >= r.first_source_paid_time
    GROUP BY db.day
),
daily AS (
    SELECT
        db.day AS day,
        SUM(CASE WHEN business_gmv_attribution = '商业化' THEN o.sub_amount ELSE 0 END) + MAX(COALESCE(ctd.crm_tele_revenue, 0)) AS revenue_amount,
        MAX(COALESCE(ctd.crm_tele_revenue, 0)) AS revenue_telesale_amount,
        SUM(CASE WHEN business_gmv_attribution = '商业化' THEN sub_amount ELSE 0 END) AS revenue_app_amount,
        COUNT(DISTINCT o.order_id) AS total_orders,
        SUM(o.sub_amount) AS total_revenue_amount,
        MAX(dut.total_deposit_users) AS deposit_users,
        MAX(dtc.cumulative_deposit_tail_users) AS deposit_tail_users,
        MAX(dtc.cumulative_deposit_tail_revenue) AS deposit_tail_revenue,
        MAX(dtt.total_deposit_tail_users) AS deposit_tail_total_users,
        MAX(dtt.total_deposit_tail_revenue) AS deposit_tail_total_revenue,
        MAX(dtc.cumulative_deposit_tail_users) AS deposit_tail_cumulative_users,
        MAX(dtc.cumulative_deposit_tail_revenue) AS deposit_tail_cumulative_revenue,
        MAX(rut.total_reservoir_users) AS reservoir_users,
        MAX(rtc.cumulative_reservoir_tail_users) AS reservoir_tail_users,
        MAX(rtc.cumulative_reservoir_tail_orders) AS reservoir_tail_orders,
        MAX(rtc.cumulative_reservoir_tail_revenue) AS reservoir_tail_revenue,
        MAX(rtt.total_reservoir_tail_users) AS reservoir_tail_total_users,
        MAX(rtt.total_reservoir_tail_orders) AS reservoir_tail_total_orders,
        MAX(rtt.total_reservoir_tail_revenue) AS reservoir_tail_total_revenue,
        MAX(rjt.total_reservoir_june_tail_users) AS reservoir_june_tail_users,
        MAX(rjt.total_reservoir_june_tail_orders) AS reservoir_june_tail_orders,
        MAX(rjt.total_reservoir_june_tail_revenue) AS reservoir_june_tail_revenue,
        MAX(rmt.total_reservoir_may_tail_users) AS reservoir_may_tail_users,
        MAX(rmt.total_reservoir_may_tail_orders) AS reservoir_may_tail_orders,
        MAX(rmt.total_reservoir_may_tail_revenue) AS reservoir_may_tail_revenue,
        MAX(ratt.total_reservoir_total_tail_users) AS reservoir_total_tail_users,
        MAX(ratt.total_reservoir_total_tail_orders) AS reservoir_total_tail_orders,
        MAX(ratt.total_reservoir_total_tail_revenue) AS reservoir_total_tail_revenue,
        MAX(rct.total_reservoir_conversion_users) AS reservoir_conversion_users,
        MAX(rct.total_reservoir_conversion_orders) AS reservoir_conversion_orders,
        MAX(rct.total_reservoir_conversion_revenue) AS reservoir_conversion_revenue,
        MAX(rjct.total_reservoir_july_conversion_users) AS reservoir_july_conversion_users,
        MAX(rjct.total_reservoir_july_conversion_orders) AS reservoir_july_conversion_orders,
        MAX(rjct.total_reservoir_july_conversion_revenue) AS reservoir_july_conversion_revenue,
        MAX(rtc.cumulative_reservoir_tail_users) AS reservoir_tail_cumulative_users,
        MAX(rtc.cumulative_reservoir_tail_orders) AS reservoir_tail_cumulative_orders,
        MAX(rtc.cumulative_reservoir_tail_revenue) AS reservoir_tail_cumulative_revenue,
        MAX(rcc.cumulative_reservoir_conversion_users) AS reservoir_conversion_cumulative_users,
        MAX(rcc.cumulative_reservoir_conversion_orders) AS reservoir_conversion_cumulative_orders,
        MAX(rcc.cumulative_reservoir_conversion_revenue) AS reservoir_conversion_cumulative_revenue,
        MAX(rcc.cumulative_reservoir_july_conversion_users) AS reservoir_july_conversion_cumulative_users,
        MAX(rcc.cumulative_reservoir_july_conversion_orders) AS reservoir_july_conversion_cumulative_orders,
        MAX(rcc.cumulative_reservoir_july_conversion_revenue) AS reservoir_july_conversion_cumulative_revenue,
       COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_3 = '小初高品' THEN o.order_id END) AS family_orders,
       COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_1 = '组合品' THEN o.order_id END) AS family_base_orders,
       SUM(CASE WHEN o.business_good_kind_name_level_3 = '小初高品' AND o.u_user IS NOT NULL AND o.is_test_user = 0 AND o.original_amount >= 39 THEN o.sub_amount ELSE 0 END) AS family_revenue,
        COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_3 = '小初高品' AND org.department_name LIKE '%小学%' THEN o.order_id END) AS family_primary_orders,
        COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_1 = '组合品' AND org.department_name LIKE '%小学%' THEN o.order_id END) AS family_primary_base_orders,
        COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_3 = '小初高品' AND org.department_name LIKE '%初中%' THEN o.order_id END) AS family_middle_orders,
        COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_1 = '组合品' AND org.department_name LIKE '%初中%' THEN o.order_id END) AS family_middle_base_orders,
        COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_3 = '小初高品' AND org.department_name LIKE '%高中%' THEN o.order_id END) AS family_high_orders,
        COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_1 = '组合品' AND org.department_name LIKE '%高中%' THEN o.order_id END) AS family_high_base_orders,
        COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_3 = '小学品加拓展' THEN o.order_id END) AS from_primary_orders,
        COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_3 IN ('小学品', '小学品加拓展') THEN o.order_id END) AS from_primary_base_orders,
        SUM(CASE WHEN o.u_user IS NOT NULL AND o.is_test_user = 0 AND o.original_amount >= 39 AND (
              (o.good_kind_name_level_3 = '拓展课' AND o.good_stage_subject_cnt = 1 AND o.good_stage_subject REGEXP '1-2-specialCourse')
           OR (o.good_kind_name_level_3 = '拓展课' AND o.good_stage_subject_cnt = 1 AND o.good_stage_subject REGEXP '1-6-specialCourse')
           OR (o.good_kind_name_level_3 = '拓展课' AND o.good_stage_subject_cnt = 1 AND o.good_stage_subject REGEXP '1-7-specialCourse')
           OR (o.good_kind_name_level_3 = '拓展课' AND o.good_stage_subject_cnt = 3 AND o.good_stage_subject REGEXP '1-2-specialCourse' AND o.good_stage_subject REGEXP '1-6-specialCourse' AND o.good_stage_subject REGEXP '1-7-specialCourse')
           OR o.business_good_kind_name_level_3 IN ('小学品加拓展')
        ) THEN o.sub_amount ELSE 0 END) AS from_primary_revenue,
        COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_3 = '小学品加拓展' AND org.department_name LIKE '%小学%' THEN o.order_id END) AS from_primary_primary_orders
        ,COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_3 IN ('小学品', '小学品加拓展') AND org.department_name LIKE '%小学%' THEN o.order_id END) AS from_primary_primary_base_orders,
        MAX(hvbt.total_high_value_users) AS high_value_users,
        MAX(hvrt.total_high_value_renew_users) AS high_value_renew_users,
        MAX(hvrt.total_high_value_renew_revenue) AS high_value_renew_revenue
    FROM day_base db
    LEFT JOIN orders_window o
      ON db.day = o.paid_time_sk
    LEFT JOIN crm_tele_daily ctd
      ON db.day = ctd.day
    CROSS JOIN deposit_users_total dut
    CROSS JOIN deposit_tail_total dtt
    CROSS JOIN reservoir_users_total rut
    CROSS JOIN reservoir_tail_total rtt
    CROSS JOIN reservoir_june_tail_total rjt
    CROSS JOIN reservoir_may_tail_total rmt
    CROSS JOIN reservoir_total_tail_total ratt
    CROSS JOIN reservoir_conversion_total rct
    CROSS JOIN reservoir_july_conversion_total rjct
    CROSS JOIN high_value_active_total hvbt
    CROSS JOIN high_value_renew_total hvrt
    LEFT JOIN deposit_tail_cumulative_by_day dtc
      ON db.day = dtc.day
    LEFT JOIN reservoir_tail_cumulative_by_day rtc
      ON db.day = rtc.day
    LEFT JOIN reservoir_conversion_cumulative_by_day rcc
      ON db.day = rcc.day
    LEFT JOIN high_value_active_users hv
      ON o.u_user = hv.u_user
     AND hv.day = o.paid_time_sk
    LEFT JOIN org_team_dim org
      ON o.team_id = org.team_id
    GROUP BY db.day
)
SELECT *
FROM daily
ORDER BY day
""".strip()


def last_year_revenue_sql(report_day: date) -> str:
    start_day = report_start_for(report_day).replace(year=report_start_for(report_day).year - 1)
    end_day = effective_report_day(report_day).replace(year=effective_report_day(report_day).year - 1)
    return f"""
WITH dws_app AS (
    SELECT
        SUM(sub_amount) AS app_revenue
    FROM dws.topic_order_detail
    WHERE paid_time_sk BETWEEN {yyyymmdd(start_day)} AND {yyyymmdd(end_day)}
      AND business_gmv_attribution = '商业化'
),
crm_tele AS (
    SELECT
        SUM(a.amount) AS tele_revenue
    FROM aws.crm_order_info a
    LEFT JOIN dw.dim_crm_organization b
        ON a.workplace_id = b.id
    LEFT JOIN dw.dim_crm_organization c
        ON a.department_id = c.id
    LEFT JOIN dw.dim_crm_organization d
        ON a.regiment_id = d.id
    LEFT JOIN dw.dim_crm_organization e
        ON a.heads_id = e.id
    LEFT JOIN dw.dim_crm_organization f
        ON a.team_id = f.id
    WHERE SUBSTR(a.pay_time, 1, 10) BETWEEN '{ymd(start_day)}' AND '{ymd(end_day)}'
      AND a.workplace_id IN (4, 400, 702)
      AND a.regiment_id NOT IN (303, 0, 546)
      AND a.worker_id <> 0
      AND a.is_test = false
)
SELECT
    COALESCE(dws.app_revenue, 0) + COALESCE(crm.tele_revenue, 0) AS last_year_revenue_amount
FROM dws_app dws
CROSS JOIN crm_tele crm
	""".strip()


def last_year_deposit_tail_share_sql(report_day: date) -> str:
    start_day = report_start_for(report_day).replace(year=report_start_for(report_day).year - 1)
    end_day = effective_report_day(report_day).replace(year=effective_report_day(report_day).year - 1)
    return f"""
WITH last_year_deposit_users AS (
    SELECT DISTINCT
        TRIM(CAST(u_user AS STRING)) AS u_user
    FROM dws.topic_order_detail
    WHERE paid_time_sk BETWEEN {yyyymmdd(LAST_YEAR_DEPOSIT_START)} AND {yyyymmdd(LAST_YEAR_DEPOSIT_END)}
      AND good_kind_id_level_2 = '{LAST_YEAR_DEPOSIT_GOOD_KIND_ID_LEVEL_2}'
      AND business_gmv_attribution IN ('商业化', '电销')
      AND u_user IS NOT NULL
),
dws_app AS (
    SELECT
        SUM(sub_amount) AS app_revenue
    FROM dws.topic_order_detail
    WHERE paid_time_sk BETWEEN {yyyymmdd(start_day)} AND {yyyymmdd(end_day)}
      AND business_gmv_attribution = '商业化'
),
crm_tele AS (
    SELECT
        SUM(a.amount) AS tele_revenue
    FROM aws.crm_order_info a
    WHERE SUBSTR(a.pay_time, 1, 10) BETWEEN '{ymd(start_day)}' AND '{ymd(end_day)}'
      AND a.workplace_id IN (4, 400, 702)
      AND a.regiment_id NOT IN (303, 0, 546)
      AND a.worker_id <> 0
      AND a.is_test = false
),
last_year_revenue AS (
    SELECT
        COALESCE(dws.app_revenue, 0) + COALESCE(crm.tele_revenue, 0) AS last_year_revenue_amount
    FROM dws_app dws
    CROSS JOIN crm_tele crm
),
last_year_tail AS (
    SELECT
        SUM(CASE WHEN du.u_user IS NOT NULL AND o.sub_amount > 500 THEN o.sub_amount ELSE 0 END) AS last_year_deposit_tail_revenue
    FROM dws.topic_order_detail o
    LEFT JOIN last_year_deposit_users du
      ON TRIM(CAST(o.u_user AS STRING)) = du.u_user
    WHERE o.paid_time_sk BETWEEN {yyyymmdd(start_day)} AND {yyyymmdd(end_day)}
      AND o.business_gmv_attribution IN ('商业化', '电销')
)
SELECT
    COALESCE(t.last_year_deposit_tail_revenue, 0) AS last_year_deposit_tail_revenue,
    CASE
        WHEN r.last_year_revenue_amount = 0 THEN 0
        ELSE COALESCE(t.last_year_deposit_tail_revenue, 0) / r.last_year_revenue_amount
    END AS last_year_deposit_tail_revenue_share
FROM last_year_tail t
CROSS JOIN last_year_revenue r
	""".strip()


def last_year_high_value_sql(report_day: date) -> str:
    start_day = report_start_for(report_day).replace(year=report_start_for(report_day).year - 1)
    end_day = effective_report_day(report_day).replace(year=effective_report_day(report_day).year - 1)
    return f"""
WITH high_value_active_users AS (
    SELECT DISTINCT
        CAST(day AS INT) AS day,
        TRIM(CAST(u_user AS STRING)) AS u_user
    FROM aws.business_active_user_last_14_day
    WHERE day BETWEEN {yyyymmdd(start_day)} AND {yyyymmdd(end_day)}
      AND business_user_pay_status_business_day = '高净值用户'
      AND u_user IS NOT NULL
),
period_orders AS (
    SELECT
        paid_time_sk,
        TRIM(CAST(u_user AS STRING)) AS u_user,
        sub_amount
    FROM dws.topic_order_detail
    WHERE paid_time_sk BETWEEN {yyyymmdd(start_day)} AND {yyyymmdd(end_day)}
      AND business_gmv_attribution IN ('商业化', '电销')
      AND business_good_kind_name_level_1 IN ('组合品', '续购')
      AND u_user IS NOT NULL
)
SELECT
    COUNT(DISTINCT hv.u_user) AS last_year_high_value_users,
    COUNT(DISTINCT CASE WHEN po.u_user IS NOT NULL THEN hv.u_user END) AS last_year_high_value_renew_users,
    SUM(CASE WHEN po.u_user IS NOT NULL THEN po.sub_amount ELSE 0 END) AS last_year_high_value_renew_revenue
FROM high_value_active_users hv
LEFT JOIN period_orders po
  ON hv.u_user = po.u_user
 AND hv.day = po.paid_time_sk
	""".strip()


def app_flow_sql(report_day: date) -> str:
    start_day_int = yyyymmdd(report_start_for(report_day))
    report_day_int = yyyymmdd(effective_report_day(report_day))
    return f"""
WITH user_base AS (
    SELECT
        a.u_user,
        a.u_from AS os,
        c.regist_channel_label1,
        c.regist_channel_label2,
        a.day
    FROM aws.user_increase_new_add_day a
    LEFT JOIN aws.user_increase_channel_label_day c
      ON a.u_user = c.u_user
     AND a.day = c.day
    WHERE a.day BETWEEN {start_day_int} AND {report_day_int}
      AND a.u_from IN ('android', 'ios', 'harmony')
      AND a.user_sk > 0
),
daily AS (
    SELECT
        day,
        os,
        regist_channel_label1,
        regist_channel_label2,
        COUNT(u_user) AS install_users
    FROM user_base
    GROUP BY 1, 2, 3, 4
)
SELECT
    day,
    SUM(install_users) AS app_new_users
FROM daily
GROUP BY day
ORDER BY day
	""".strip()


def last_year_app_flow_sql(report_day: date) -> str:
    start_day_int = yyyymmdd(report_start_for(report_day).replace(year=report_start_for(report_day).year - 1))
    report_day_int = yyyymmdd(effective_report_day(report_day).replace(year=effective_report_day(report_day).year - 1))
    return f"""
WITH user_base AS (
    SELECT
        a.u_user,
        a.u_from AS os,
        c.regist_channel_label1,
        c.regist_channel_label2,
        a.day
    FROM aws.user_increase_new_add_day a
    LEFT JOIN aws.user_increase_channel_label_day c
      ON a.u_user = c.u_user
     AND a.day = c.day
    WHERE a.day BETWEEN {start_day_int} AND {report_day_int}
      AND a.u_from IN ('android', 'ios', 'harmony')
      AND a.user_sk > 0
),
daily AS (
    SELECT
        day,
        os,
        regist_channel_label1,
        regist_channel_label2,
        COUNT(u_user) AS install_users
    FROM user_base
    GROUP BY 1, 2, 3, 4
)
SELECT
    SUM(install_users) AS last_year_app_new_users
FROM daily
""".strip()


def chongding_revenue_progress_sql(report_day: date) -> str:
    report_day_int = min(max(yyyymmdd(report_day), 20260701), 20260731)
    return f"""
WITH ranked AS (
    SELECT
        channel,
        date_sk,
        target_revenue,
        real_revenue,
        month_total_target,
        cumulative_target_revenue,
        cumulative_real_revenue,
        time_progress,
        predicted_target_progress,
        actual_completion_progress,
        forecast_completion_progress,
        actual_vs_cumulative_target_progress,
        row_number() OVER (
            PARTITION BY channel
            ORDER BY date_sk DESC
        ) AS rn
    FROM tmp.xuxingling_202607_chongding_fine_summary
    WHERE date_sk <= {report_day_int}
      AND channel IN ('整体', 'APP', '电销')
)
SELECT
    channel,
    date_sk,
    target_revenue,
    real_revenue,
    month_total_target,
    cumulative_target_revenue,
    cumulative_real_revenue,
    time_progress,
    predicted_target_progress,
    actual_completion_progress,
    forecast_completion_progress,
    actual_vs_cumulative_target_progress
FROM ranked
WHERE rn = 1
ORDER BY CASE channel WHEN '整体' THEN 1 WHEN 'APP' THEN 2 WHEN '电销' THEN 3 ELSE 9 END
LIMIT 10000
""".strip()


def run_starrocks_query(sql: str, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    import pymysql

    conn = pymysql.connect(
        host=cfg["host"],
        port=cfg.get("port", 9030),
        user=cfg["user"],
        password=cfg["password"],
        database=cfg.get("database", "hive.aws"),
        charset="utf8mb4",
        connect_timeout=30,
        read_timeout=900,
    )
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql)
            return list(cur.fetchall())
    finally:
        conn.close()


def run_sparksql_query(sql: str, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    from impala.dbapi import connect

    conn = connect(
        host=cfg["host"],
        port=cfg.get("port", 10010),
        auth_mechanism="PLAIN",
        user=cfg.get("user", ""),
        password=cfg.get("password", ""),
        database=cfg.get("database", "default"),
    )
    try:
        cur = conn.cursor(dictify=True)
        cur.execute(sql)
        return list(cur.fetchall())
    finally:
        conn.close()


def run_query(sql: str, db_config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    effective_db_config = db_config or load_db_config()
    sanitized_sql = validate_select_sql(sql)
    if effective_db_config.get("sparksql"):
        return run_sparksql_query(sanitized_sql, effective_db_config["sparksql"])
    return run_starrocks_query(sanitized_sql, effective_db_config["starrocks"])


def complete_daily_series(rows: List[Dict[str, Any]], start_day: date, end_day: date, fields: List[str]) -> List[Dict[str, Any]]:
    row_by_day = {}
    for row in rows:
        raw_day = row.get("day")
        if raw_day is None:
            continue
        day = date_from_int(int(raw_day)) if isinstance(raw_day, int) or str(raw_day).isdigit() else date.fromisoformat(str(raw_day)[:10])
        row_by_day[ymd(day)] = row

    result = []
    current = start_day
    while current <= end_day:
        key = ymd(current)
        source = row_by_day.get(key, {})
        item = {"day": key}
        for field in fields:
            item[field] = float(source.get(field) or 0)
        result.append(item)
        current += timedelta(days=1)
    return result


def carry_forward_fields(rows: List[Dict[str, Any]], fields: List[str]) -> None:
    latest_values = {field: 0.0 for field in fields}
    for row in rows:
        for field in fields:
            value = float(row.get(field) or 0)
            if value:
                latest_values[field] = value
            elif latest_values[field]:
                row[field] = latest_values[field]


def _sum_field(rows: List[Dict[str, Any]], field: str) -> float:
    return sum(float(row.get(field) or 0) for row in rows)


def _last_field(rows: List[Dict[str, Any]], field: str) -> float:
    return float(rows[-1].get(field) or 0) if rows else 0


def _float_or_none(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    return float(value)


def normalize_revenue_progress_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for row in rows:
        channel = row.get("channel")
        if channel not in ("整体", "APP", "电销"):
            continue
        result.append(
            {
                "channel": channel,
                "date_sk": row.get("date_sk"),
                "target_revenue": _float_or_none(row.get("target_revenue")),
                "real_revenue": _float_or_none(row.get("real_revenue")),
                "month_total_target": _float_or_none(row.get("month_total_target")),
                "cumulative_target_revenue": _float_or_none(row.get("cumulative_target_revenue")),
                "cumulative_real_revenue": _float_or_none(row.get("cumulative_real_revenue")),
                "time_progress": _float_or_none(row.get("time_progress")),
                "predicted_target_progress": _float_or_none(row.get("predicted_target_progress")),
                "actual_completion_progress": _float_or_none(row.get("actual_completion_progress")),
                "forecast_completion_progress": _float_or_none(row.get("forecast_completion_progress")),
                "actual_vs_cumulative_target_progress": _float_or_none(row.get("actual_vs_cumulative_target_progress")),
            }
        )
    order = {"整体": 1, "APP": 2, "电销": 3}
    return sorted(result, key=lambda item: order.get(str(item.get("channel")), 9))


def fallback_revenue_progress_rows(metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    report_day = metrics["report_day"]
    july_start = date(2026, 7, 1)
    july_end = date(2026, 7, 31)
    if report_day < july_start:
        month_day = 0
    else:
        month_day = min((min(report_day, july_end) - july_start).days + 1, 31)
    time_progress = safe_div(month_day, 31)
    target = metrics["revenue"]["target"]
    actual = metrics["revenue"]["amount"]
    return [
        {
            "channel": "整体",
            "date_sk": yyyymmdd(report_day),
            "target_revenue": None,
            "real_revenue": None,
            "month_total_target": target,
            "cumulative_target_revenue": None,
            "cumulative_real_revenue": actual,
            "time_progress": time_progress,
            "predicted_target_progress": time_progress,
            "actual_completion_progress": metrics["revenue"]["progress"],
            "actual_vs_cumulative_target_progress": None,
        },
        {
            "channel": "APP",
            "date_sk": yyyymmdd(report_day),
            "target_revenue": None,
            "real_revenue": None,
            "month_total_target": None,
            "cumulative_target_revenue": None,
            "cumulative_real_revenue": metrics["revenue"]["app_amount"],
            "time_progress": time_progress,
            "predicted_target_progress": None,
            "actual_completion_progress": None,
            "forecast_completion_progress": None,
            "actual_vs_cumulative_target_progress": None,
        },
        {
            "channel": "电销",
            "date_sk": yyyymmdd(report_day),
            "target_revenue": None,
            "real_revenue": None,
            "month_total_target": None,
            "cumulative_target_revenue": None,
            "cumulative_real_revenue": metrics["revenue"]["telesale_amount"],
            "time_progress": time_progress,
            "predicted_target_progress": None,
            "actual_completion_progress": None,
            "forecast_completion_progress": None,
            "actual_vs_cumulative_target_progress": None,
        },
    ]


def format_optional_money_wan(value: Number) -> str:
    return "-" if value is None else format_money_wan(value)


def format_optional_wan(value: Number) -> str:
    return "-" if value is None else format_wan(value)


def format_optional_pct(value: Number) -> str:
    return "-" if value is None else format_pct(value)


def _css_pct(value: Number) -> str:
    return f"{max(0, min(1, float(value or 0))) * 100:.2f}%"


def revenue_progress_payload_rows(metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = normalize_revenue_progress_rows(metrics.get("revenue_progress", []))
    if not rows:
        rows = fallback_revenue_progress_rows(metrics)
    actual_by_channel = {
        "整体": metrics["revenue"]["amount"],
        "APP": metrics["revenue"]["app_amount"],
        "电销": metrics["revenue"]["telesale_amount"],
    }
    for row in rows:
        actual_value = float(actual_by_channel.get(str(row.get("channel")), 0) or 0)
        if actual_value <= 0:
            continue
        row["cumulative_real_revenue"] = actual_value
        month_target = row.get("month_total_target")
        if row.get("channel") == "整体" and not month_target:
            month_target = metrics["revenue"]["target"]
            row["month_total_target"] = month_target
        if month_target:
            row["actual_completion_progress"] = safe_div(actual_value, month_target)
    channel_actual_total = sum(
        float(row.get("cumulative_real_revenue") or 0)
        for row in rows
        if row.get("channel") in ("APP", "电销")
    )
    result = [
        {
            "channel": str(row.get("channel") or "-"),
            "month_target": format_optional_money_wan(row.get("month_total_target")),
            "month_target_short": format_optional_wan(row.get("month_total_target")),
            "cumulative_target": format_optional_money_wan(row.get("cumulative_target_revenue")),
            "cumulative_actual": format_optional_money_wan(row.get("cumulative_real_revenue")),
            "cumulative_actual_short": format_optional_wan(row.get("cumulative_real_revenue")),
            "time_progress": format_optional_pct(row.get("time_progress")),
            "target_progress": format_optional_pct(row.get("predicted_target_progress")),
            "actual_progress": format_optional_pct(row.get("actual_completion_progress")),
            "current_pace": format_optional_pct(row.get("actual_vs_cumulative_target_progress")),
            "time_progress_value": float(row.get("time_progress") or 0),
            "target_progress_value": float(row.get("predicted_target_progress") or 0),
            "actual_progress_value": float(row.get("actual_completion_progress") or 0),
            "current_pace_value": float(row.get("actual_vs_cumulative_target_progress") or 0),
            "mix_share": format_optional_pct(
                safe_div(row.get("cumulative_real_revenue"), channel_actual_total)
                if row.get("channel") in ("APP", "电销")
                else None
            ),
            "mix_share_value": (
                safe_div(row.get("cumulative_real_revenue"), channel_actual_total)
                if row.get("channel") in ("APP", "电销")
                else 0
            ),
        }
        for row in rows
    ]
    return result


def fetch_metrics(
    report_day: date,
    db_config: Optional[Dict[str, Any]] = None,
    query_runner=run_query,
) -> Dict[str, Any]:
    effective_day = effective_report_day(report_day)
    start_day = report_start_for(effective_day)
    effective_db_config = db_config or (load_db_config() if query_runner is run_query else {})
    metric_rows = query_runner(key_metrics_sql(effective_day), effective_db_config)
    app_rows = query_runner(app_flow_sql(effective_day), effective_db_config)
    last_year_rows = query_runner(last_year_revenue_sql(effective_day), effective_db_config)
    last_year_deposit_tail_rows = query_runner(last_year_deposit_tail_share_sql(effective_day), effective_db_config)
    last_year_high_value_rows = query_runner(last_year_high_value_sql(effective_day), effective_db_config)
    last_year_app_rows = query_runner(last_year_app_flow_sql(effective_day), effective_db_config)
    try:
        revenue_progress_rows = query_runner(chongding_revenue_progress_sql(report_day), effective_db_config)
    except Exception as exc:
        print(f"[营收进度] 冲顶汇总表查询失败，使用日推营收数据兜底：{exc}", file=sys.stderr)
        revenue_progress_rows = []

    metric_fields = [
        "revenue_amount",
        "revenue_telesale_amount",
        "revenue_app_amount",
        "total_orders",
        "total_revenue_amount",
        "deposit_users",
        "deposit_tail_users",
        "deposit_tail_revenue",
        "deposit_tail_total_users",
        "deposit_tail_total_revenue",
        "deposit_tail_cumulative_users",
        "deposit_tail_cumulative_revenue",
        "reservoir_users",
        "reservoir_tail_users",
        "reservoir_tail_orders",
        "reservoir_tail_revenue",
        "reservoir_tail_total_users",
        "reservoir_tail_total_orders",
        "reservoir_tail_total_revenue",
        "reservoir_june_tail_users",
        "reservoir_june_tail_orders",
        "reservoir_june_tail_revenue",
        "reservoir_may_tail_users",
        "reservoir_may_tail_orders",
        "reservoir_may_tail_revenue",
        "reservoir_total_tail_users",
        "reservoir_total_tail_orders",
        "reservoir_total_tail_revenue",
        "reservoir_conversion_users",
        "reservoir_conversion_orders",
        "reservoir_conversion_revenue",
        "reservoir_july_conversion_users",
        "reservoir_july_conversion_orders",
        "reservoir_july_conversion_revenue",
        "reservoir_tail_cumulative_users",
        "reservoir_tail_cumulative_orders",
        "reservoir_tail_cumulative_revenue",
        "reservoir_conversion_cumulative_users",
        "reservoir_conversion_cumulative_orders",
        "reservoir_conversion_cumulative_revenue",
        "reservoir_july_conversion_cumulative_users",
        "reservoir_july_conversion_cumulative_orders",
        "reservoir_july_conversion_cumulative_revenue",
       "family_orders",
       "family_base_orders",
        "family_revenue",
        "family_primary_orders",
        "family_primary_base_orders",
        "family_middle_orders",
        "family_middle_base_orders",
        "family_high_orders",
        "family_high_base_orders",
       "from_primary_orders",
       "from_primary_base_orders",
        "from_primary_revenue",
        "from_primary_primary_orders",
        "from_primary_primary_base_orders",
        "high_value_users",
        "high_value_renew_users",
        "high_value_renew_revenue",
   ]
    daily = complete_daily_series(metric_rows, start_day, effective_day, metric_fields)
    carry_forward_fields(
        daily,
        [
            "deposit_users",
            "deposit_tail_cumulative_users",
            "deposit_tail_cumulative_revenue",
            "reservoir_users",
            "reservoir_june_tail_users",
            "reservoir_june_tail_orders",
            "reservoir_june_tail_revenue",
            "reservoir_may_tail_users",
            "reservoir_may_tail_orders",
            "reservoir_may_tail_revenue",
            "reservoir_total_tail_users",
            "reservoir_total_tail_orders",
            "reservoir_total_tail_revenue",
            "reservoir_conversion_users",
            "reservoir_conversion_orders",
            "reservoir_conversion_revenue",
            "reservoir_july_conversion_users",
            "reservoir_july_conversion_orders",
            "reservoir_july_conversion_revenue",
            "reservoir_tail_cumulative_users",
            "reservoir_tail_cumulative_orders",
            "reservoir_tail_cumulative_revenue",
            "reservoir_conversion_cumulative_users",
            "reservoir_conversion_cumulative_orders",
            "reservoir_conversion_cumulative_revenue",
            "reservoir_july_conversion_cumulative_users",
            "reservoir_july_conversion_cumulative_orders",
            "reservoir_july_conversion_cumulative_revenue",
            "high_value_users",
            "high_value_renew_users",
            "high_value_renew_revenue",
        ],
    )
    app_daily = complete_daily_series(app_rows, start_day, effective_day, ["app_new_users"])
    for item, app_item in zip(daily, app_daily):
        item["app_new_users"] = app_item["app_new_users"]

    revenue_amount = _sum_field(daily, "revenue_amount")
    revenue_telesale_amount = _sum_field(daily, "revenue_telesale_amount")
    revenue_app_amount = _sum_field(daily, "revenue_app_amount")
    yesterday_revenue_amount = _last_field(daily, "revenue_amount")
    app_users = _sum_field(daily, "app_new_users")
    yesterday_app_users = _last_field(daily, "app_new_users")
    last_year_row = last_year_rows[0] if last_year_rows else {}
    last_year_revenue_amount = float(last_year_row.get("last_year_revenue_amount") or 0)
    last_year_deposit_tail_row = last_year_deposit_tail_rows[0] if last_year_deposit_tail_rows else {}
    last_year_deposit_tail_revenue = float(last_year_deposit_tail_row.get("last_year_deposit_tail_revenue") or 0)
    last_year_deposit_tail_revenue_share = float(last_year_deposit_tail_row.get("last_year_deposit_tail_revenue_share") or 0)
    last_year_high_value_row = last_year_high_value_rows[0] if last_year_high_value_rows else {}
    last_year_high_value_users = float(last_year_high_value_row.get("last_year_high_value_users") or 0)
    last_year_high_value_renew_users = float(last_year_high_value_row.get("last_year_high_value_renew_users") or 0)
    last_year_high_value_renew_revenue = float(last_year_high_value_row.get("last_year_high_value_renew_revenue") or 0)
    last_year_app_row = last_year_app_rows[0] if last_year_app_rows else {}
    last_year_app_users = float(last_year_app_row.get("last_year_app_new_users") or 0)
    total_orders = _last_field(daily, "total_orders")
    total_revenue_amount = _last_field(daily, "total_revenue_amount")
    deposit_users = _last_field(daily, "deposit_users")
    deposit_tail_users = _last_field(daily, "deposit_tail_total_users") or _last_field(daily, "deposit_tail_users")
    deposit_tail_revenue = _last_field(daily, "deposit_tail_total_revenue") or _last_field(daily, "deposit_tail_revenue")
    reservoir_users = _last_field(daily, "reservoir_users")
    reservoir_tail_users = _last_field(daily, "reservoir_tail_total_users") or _last_field(daily, "reservoir_tail_users")
    reservoir_tail_orders = _last_field(daily, "reservoir_tail_total_orders") or _last_field(daily, "reservoir_tail_orders")
    reservoir_tail_revenue = _last_field(daily, "reservoir_tail_total_revenue") or _last_field(daily, "reservoir_tail_revenue")
    reservoir_june_tail_users = _last_field(daily, "reservoir_june_tail_users")
    reservoir_june_tail_orders = _last_field(daily, "reservoir_june_tail_orders")
    reservoir_june_tail_revenue = _last_field(daily, "reservoir_june_tail_revenue")
    reservoir_may_tail_users = _last_field(daily, "reservoir_may_tail_users")
    reservoir_may_tail_orders = _last_field(daily, "reservoir_may_tail_orders")
    reservoir_may_tail_revenue = _last_field(daily, "reservoir_may_tail_revenue")
    reservoir_total_tail_users = _last_field(daily, "reservoir_total_tail_users")
    reservoir_total_tail_orders = _last_field(daily, "reservoir_total_tail_orders")
    reservoir_total_tail_revenue = _last_field(daily, "reservoir_total_tail_revenue")
    reservoir_conversion_users = _last_field(daily, "reservoir_conversion_users")
    reservoir_conversion_orders = _last_field(daily, "reservoir_conversion_orders")
    reservoir_conversion_revenue = _last_field(daily, "reservoir_conversion_revenue")
    reservoir_july_conversion_users = _last_field(daily, "reservoir_july_conversion_users")
    reservoir_july_conversion_orders = _last_field(daily, "reservoir_july_conversion_orders")
    reservoir_july_conversion_revenue = _last_field(daily, "reservoir_july_conversion_revenue")
    family_orders = _last_field(daily, "family_orders")
    family_base_orders = _last_field(daily, "family_base_orders")
    family_primary_orders = _last_field(daily, "family_primary_orders")
    family_primary_base_orders = _last_field(daily, "family_primary_base_orders")
    family_middle_orders = _last_field(daily, "family_middle_orders")
    family_middle_base_orders = _last_field(daily, "family_middle_base_orders")
    family_high_orders = _last_field(daily, "family_high_orders")
    family_high_base_orders = _last_field(daily, "family_high_base_orders")
    from_primary_orders = _last_field(daily, "from_primary_orders")
    from_primary_base_orders = _last_field(daily, "from_primary_base_orders")
    from_primary_primary_orders = _last_field(daily, "from_primary_primary_orders")
    from_primary_primary_base_orders = _last_field(daily, "from_primary_primary_base_orders")
    high_value_users = _last_field(daily, "high_value_users")
    high_value_renew_users = _last_field(daily, "high_value_renew_users")
    high_value_renew_revenue = _last_field(daily, "high_value_renew_revenue")

    return {
        "report_day": effective_day,
        "daily": daily,
        "revenue_progress": normalize_revenue_progress_rows(revenue_progress_rows),
        "revenue": {
            "amount": revenue_amount,
            "yesterday_amount": yesterday_revenue_amount,
            "telesale_amount": revenue_telesale_amount,
            "app_amount": revenue_app_amount,
            "target": REVENUE_TARGET_WAN * 10000,
            "progress": safe_div(revenue_amount, REVENUE_TARGET_WAN * 10000),
            "last_year_amount": last_year_revenue_amount,
            "last_year_progress": safe_div(last_year_revenue_amount, REVENUE_TARGET_WAN * 10000),
        },
        "app_flow": {
            "users": app_users,
            "yesterday_users": yesterday_app_users,
            "target": APP_FLOW_TARGET_USERS,
            "progress": safe_div(app_users, APP_FLOW_TARGET_USERS),
            "last_year_users": last_year_app_users,
        },
        "deposit": {
            "users": deposit_users,
            "target": DEPOSIT_TARGET_USERS,
            "progress": safe_div(deposit_users, DEPOSIT_TARGET_USERS),
            "tail_users": deposit_tail_users,
            "tail_rate": safe_div(deposit_tail_users, deposit_users),
            "tail_revenue": deposit_tail_revenue,
            "tail_revenue_share": safe_div(deposit_tail_revenue, revenue_amount),
            "last_year_tail_revenue": last_year_deposit_tail_revenue,
            "last_year_tail_revenue_share": last_year_deposit_tail_revenue_share,
            "tail_aov": safe_div(deposit_tail_revenue, deposit_tail_users),
        },
        "reservoir": {
            "users": reservoir_users,
            "target": RESERVOIR_TARGET_USERS,
            "progress": safe_div(reservoir_users, RESERVOIR_TARGET_USERS),
            "tail_users": reservoir_tail_users,
            "tail_orders": reservoir_tail_orders,
            "tail_rate": safe_div(reservoir_tail_users, reservoir_users),
            "revenue": reservoir_tail_revenue,
            "june_tail_users": reservoir_june_tail_users,
            "june_tail_orders": reservoir_june_tail_orders,
            "june_tail_revenue": reservoir_june_tail_revenue,
            "june_tail_rate": safe_div(reservoir_june_tail_users, reservoir_users),
            "may_tail_users": reservoir_may_tail_users,
            "may_tail_orders": reservoir_may_tail_orders,
            "may_tail_revenue": reservoir_may_tail_revenue,
            "may_tail_rate": safe_div(reservoir_may_tail_users, reservoir_users),
            "total_tail_users": reservoir_total_tail_users,
            "total_tail_orders": reservoir_total_tail_orders,
            "total_tail_revenue": reservoir_total_tail_revenue,
            "total_tail_rate": safe_div(reservoir_total_tail_users, reservoir_users),
            "conversion_users": reservoir_conversion_users,
            "conversion_orders": reservoir_conversion_orders,
            "conversion_revenue": reservoir_conversion_revenue,
            "conversion_rate": safe_div(reservoir_conversion_users, reservoir_users),
            "july_conversion_users": reservoir_july_conversion_users,
            "july_conversion_orders": reservoir_july_conversion_orders,
            "july_conversion_revenue": reservoir_july_conversion_revenue,
            "july_conversion_rate": safe_div(reservoir_july_conversion_users, reservoir_users),
        },
       "family": {
           "orders": family_orders,
           "base_orders": family_base_orders,
           "order_share": safe_div(family_orders, family_base_orders),
           "target": FAMILY_ORDER_SHARE_TARGET,
           "revenue": _sum_field(daily, "family_revenue"),
            "primary_share": safe_div(family_primary_orders, family_primary_base_orders),
            "middle_share": safe_div(family_middle_orders, family_middle_base_orders),
            "high_share": safe_div(family_high_orders, family_high_base_orders),
       },
       "from_primary": {
           "orders": from_primary_orders,
           "base_orders": from_primary_base_orders,
           "order_share": safe_div(from_primary_orders, from_primary_base_orders),
           "target": FROM_PRIMARY_ORDER_SHARE_TARGET,
           "revenue": _sum_field(daily, "from_primary_revenue"),
            "primary_share": safe_div(from_primary_primary_orders, from_primary_primary_base_orders),
       },
        "high_value_renewal": {
            "users": high_value_users,
            "renew_users": high_value_renew_users,
            "renew_rate": safe_div(high_value_renew_users, high_value_users),
            "renew_revenue": high_value_renew_revenue,
            "renew_aov": safe_div(high_value_renew_revenue, high_value_renew_users),
            "last_year_renew_rate": safe_div(last_year_high_value_renew_users, last_year_high_value_users),
            "last_year_renew_aov": safe_div(last_year_high_value_renew_revenue, last_year_high_value_renew_users),
        },
    }


def sample_metrics(report_day: date) -> Dict[str, Any]:
    effective_day = effective_report_day(report_day)
    start_day = report_start_for(effective_day)
    daily = []
    current = start_day
    index = 0
    while current <= effective_day:
        index += 1
        daily.append(
            {
                "day": ymd(current),
                "revenue_amount": 0 if index == 2 else index * 180000,
                "revenue_telesale_amount": 0 if index == 2 else index * 110000,
                "revenue_app_amount": 0 if index == 2 else index * 70000,
                "app_new_users": index * 8500,
                "deposit_users": min(DEPOSIT_TARGET_USERS, 7800 + index * 180),
                "deposit_tail_users": 3900 + index * 120,
                "deposit_tail_revenue": 2600000 + index * 180000,
                "deposit_tail_total_users": 3900 + index * 120,
                "deposit_tail_total_revenue": 2600000 + index * 180000,
                "deposit_tail_cumulative_users": 3900 + index * 120,
                "deposit_tail_cumulative_revenue": 2600000 + index * 180000,
                "reservoir_users": 23600,
                "reservoir_tail_users": 7600 + index * 160,
                "reservoir_tail_orders": 8200 + index * 150,
                "reservoir_tail_revenue": 2900000 + index * 160000,
                "reservoir_tail_total_users": 7600 + index * 160,
                "reservoir_tail_total_orders": 8200 + index * 150,
                "reservoir_tail_total_revenue": 2900000 + index * 160000,
                "reservoir_june_tail_users": 1200,
                "reservoir_june_tail_orders": 1260,
                "reservoir_june_tail_revenue": 4200000,
                "reservoir_may_tail_users": 240,
                "reservoir_may_tail_orders": 250,
                "reservoir_may_tail_revenue": 900000,
                "reservoir_total_tail_users": 8800 + index * 160,
                "reservoir_total_tail_orders": 9460 + index * 150,
                "reservoir_total_tail_revenue": 7100000 + index * 160000,
                "reservoir_conversion_users": 10200 + index * 180,
                "reservoir_conversion_orders": 12100 + index * 210,
                "reservoir_conversion_revenue": 8200000 + index * 220000,
                "reservoir_july_conversion_users": 7900 + index * 170,
                "reservoir_july_conversion_orders": 9100 + index * 190,
                "reservoir_july_conversion_revenue": 3600000 + index * 190000,
                "reservoir_tail_cumulative_users": 7600 + index * 160,
                "reservoir_tail_cumulative_orders": 8200 + index * 150,
                "reservoir_tail_cumulative_revenue": 2900000 + index * 160000,
                "reservoir_conversion_cumulative_users": 10200 + index * 180,
                "reservoir_conversion_cumulative_orders": 12100 + index * 210,
                "reservoir_conversion_cumulative_revenue": 8200000 + index * 220000,
                "reservoir_july_conversion_cumulative_users": 7900 + index * 170,
                "reservoir_july_conversion_cumulative_orders": 9100 + index * 190,
                "reservoir_july_conversion_cumulative_revenue": 3600000 + index * 190000,
                "total_orders": 25000 + index * 300,
                "total_revenue_amount": 6800000 + index * 500000,
               "family_orders": 4400 + index * 120,
               "family_base_orders": 22000 + index * 350,
                "family_revenue": 2000000 + index * 130000,
                "family_primary_orders": 2200 + index * 60,
                "family_primary_base_orders": 9000 + index * 120,
                "family_middle_orders": 1300 + index * 35,
                "family_middle_base_orders": 7000 + index * 100,
                "family_high_orders": 900 + index * 25,
                "family_high_base_orders": 6000 + index * 80,
                "from_primary_orders": 2800 + index * 80,
                "from_primary_base_orders": 22000 + index * 350,
                "from_primary_revenue": 1100000 + index * 90000,
                "from_primary_primary_orders": 2200 + index * 65,
                "from_primary_primary_base_orders": 7000 + index * 100,
                "high_value_users": 1200 + index * 30,
                "high_value_renew_users": 360 + index * 12,
                "high_value_renew_revenue": 900000 + index * 42000,
            }
        )
        current += timedelta(days=1)

    latest = daily[-1]
    revenue_amount = _sum_field(daily, "revenue_amount")
    revenue_telesale_amount = _sum_field(daily, "revenue_telesale_amount")
    revenue_app_amount = _sum_field(daily, "revenue_app_amount")
    app_users = _sum_field(daily, "app_new_users")
    last_year_revenue_amount = revenue_amount * 0.82
    last_year_app_users = app_users * 0.9
    app_month_target = 30000000
    telesale_month_target = 90000000
    month_total_target = app_month_target + telesale_month_target
    return {
        "report_day": effective_day,
        "daily": daily,
        "revenue_progress": [
            {
                "channel": "整体",
                "month_total_target": month_total_target,
                "cumulative_target_revenue": month_total_target * safe_div((effective_day - start_day).days + 1, days_in_month(effective_day)),
                "cumulative_real_revenue": revenue_amount,
                "actual_completion_progress": safe_div(revenue_amount, month_total_target),
                "predicted_target_progress": safe_div((effective_day - start_day).days + 1, days_in_month(effective_day)),
                "time_progress": safe_div((effective_day - start_day).days + 1, days_in_month(effective_day)),
            },
            {
                "channel": "APP",
                "month_total_target": app_month_target,
                "cumulative_target_revenue": app_month_target * safe_div((effective_day - start_day).days + 1, days_in_month(effective_day)),
                "cumulative_real_revenue": revenue_app_amount,
                "actual_completion_progress": safe_div(revenue_app_amount, app_month_target),
                "predicted_target_progress": safe_div((effective_day - start_day).days + 1, days_in_month(effective_day)),
                "time_progress": safe_div((effective_day - start_day).days + 1, days_in_month(effective_day)),
            },
            {
                "channel": "电销",
                "month_total_target": telesale_month_target,
                "cumulative_target_revenue": telesale_month_target * safe_div((effective_day - start_day).days + 1, days_in_month(effective_day)),
                "cumulative_real_revenue": revenue_telesale_amount,
                "actual_completion_progress": safe_div(revenue_telesale_amount, telesale_month_target),
                "predicted_target_progress": safe_div((effective_day - start_day).days + 1, days_in_month(effective_day)),
                "time_progress": safe_div((effective_day - start_day).days + 1, days_in_month(effective_day)),
            },
        ],
        "revenue": {
            "amount": revenue_amount,
            "yesterday_amount": latest["revenue_amount"],
            "telesale_amount": revenue_telesale_amount,
            "app_amount": revenue_app_amount,
            "target": REVENUE_TARGET_WAN * 10000,
            "progress": safe_div(revenue_amount, REVENUE_TARGET_WAN * 10000),
            "last_year_amount": last_year_revenue_amount,
            "last_year_progress": safe_div(last_year_revenue_amount, REVENUE_TARGET_WAN * 10000),
        },
        "app_flow": {
            "users": app_users,
            "yesterday_users": latest["app_new_users"],
            "target": APP_FLOW_TARGET_USERS,
            "progress": safe_div(app_users, APP_FLOW_TARGET_USERS),
            "last_year_users": last_year_app_users,
        },
        "deposit": {
            "users": latest["deposit_users"],
            "target": DEPOSIT_TARGET_USERS,
            "progress": safe_div(latest["deposit_users"], DEPOSIT_TARGET_USERS),
            "tail_users": latest["deposit_tail_cumulative_users"],
            "tail_rate": safe_div(latest["deposit_tail_cumulative_users"], latest["deposit_users"]),
            "tail_revenue": latest["deposit_tail_cumulative_revenue"],
            "tail_revenue_share": safe_div(latest["deposit_tail_cumulative_revenue"], revenue_amount),
            "last_year_tail_revenue": revenue_amount * 0.18,
            "last_year_tail_revenue_share": 0.18,
            "tail_aov": safe_div(latest["deposit_tail_cumulative_revenue"], latest["deposit_tail_cumulative_users"]),
        },
        "reservoir": {
            "users": latest["reservoir_users"],
            "target": RESERVOIR_TARGET_USERS,
            "progress": safe_div(latest["reservoir_users"], RESERVOIR_TARGET_USERS),
            "tail_users": latest["reservoir_tail_cumulative_users"],
            "tail_orders": latest.get("reservoir_tail_cumulative_orders", 0),
            "tail_rate": safe_div(latest["reservoir_tail_cumulative_users"], latest["reservoir_users"]),
            "revenue": latest["reservoir_tail_cumulative_revenue"],
            "june_tail_users": latest.get("reservoir_june_tail_users", 0),
            "june_tail_orders": latest.get("reservoir_june_tail_orders", 0),
            "june_tail_revenue": latest.get("reservoir_june_tail_revenue", 0),
            "june_tail_rate": safe_div(latest.get("reservoir_june_tail_users", 0), latest["reservoir_users"]),
            "may_tail_users": latest.get("reservoir_may_tail_users", 0),
            "may_tail_orders": latest.get("reservoir_may_tail_orders", 0),
            "may_tail_revenue": latest.get("reservoir_may_tail_revenue", 0),
            "may_tail_rate": safe_div(latest.get("reservoir_may_tail_users", 0), latest["reservoir_users"]),
            "total_tail_users": latest.get("reservoir_total_tail_users", 0),
            "total_tail_orders": latest.get("reservoir_total_tail_orders", 0),
            "total_tail_revenue": latest.get("reservoir_total_tail_revenue", 0),
            "total_tail_rate": safe_div(latest.get("reservoir_total_tail_users", 0), latest["reservoir_users"]),
            "conversion_users": latest.get("reservoir_conversion_users", 0),
            "conversion_orders": latest.get("reservoir_conversion_orders", 0),
            "conversion_revenue": latest.get("reservoir_conversion_revenue", 0),
            "conversion_rate": safe_div(latest.get("reservoir_conversion_users", 0), latest["reservoir_users"]),
            "july_conversion_users": latest.get("reservoir_july_conversion_users", 0),
            "july_conversion_orders": latest.get("reservoir_july_conversion_orders", 0),
            "july_conversion_revenue": latest.get("reservoir_july_conversion_revenue", 0),
            "july_conversion_rate": safe_div(latest.get("reservoir_july_conversion_users", 0), latest["reservoir_users"]),
        },
       "family": {
           "orders": latest["family_orders"],
           "base_orders": latest["family_base_orders"],
           "order_share": safe_div(latest["family_orders"], latest["family_base_orders"]),
           "target": FAMILY_ORDER_SHARE_TARGET,
           "revenue": _sum_field(daily, "family_revenue"),
            "primary_share": safe_div(latest["family_primary_orders"], latest["family_primary_base_orders"]),
            "middle_share": safe_div(latest["family_middle_orders"], latest["family_middle_base_orders"]),
            "high_share": safe_div(latest["family_high_orders"], latest["family_high_base_orders"]),
       },
       "from_primary": {
           "orders": latest["from_primary_orders"],
           "base_orders": latest["from_primary_base_orders"],
           "order_share": safe_div(latest["from_primary_orders"], latest["from_primary_base_orders"]),
           "target": FROM_PRIMARY_ORDER_SHARE_TARGET,
           "revenue": _sum_field(daily, "from_primary_revenue"),
            "primary_share": safe_div(latest["from_primary_primary_orders"], latest["from_primary_primary_base_orders"]),
       },
        "high_value_renewal": {
            "users": latest["high_value_users"],
            "renew_users": latest["high_value_renew_users"],
            "renew_rate": safe_div(latest["high_value_renew_users"], latest["high_value_users"]),
            "renew_revenue": latest["high_value_renew_revenue"],
            "renew_aov": safe_div(latest["high_value_renew_revenue"], latest["high_value_renew_users"]),
            "last_year_renew_rate": safe_div(latest["high_value_renew_users"] * 0.8, latest["high_value_users"]),
            "last_year_renew_aov": safe_div(latest["high_value_renew_revenue"] * 0.75, latest["high_value_renew_users"] * 0.8),
        },
    }


def _json_for_html(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def dashboard_daily_rows(metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    revenue_total = 0.0
    app_total = 0.0
    deposit_tail_users_total = 0.0
    deposit_tail_revenue_total = 0.0
    reservoir_tail_users_total = 0.0
    reservoir_tail_revenue_total = 0.0
    reservoir_conversion_users_total = 0.0
    reservoir_conversion_revenue_total = 0.0
    reservoir_july_conversion_users_total = 0.0
    reservoir_july_conversion_revenue_total = 0.0
    for row in metrics["daily"]:
        item = dict(row)
        revenue_total += float(row.get("revenue_amount") or 0)
        app_total += float(row.get("app_new_users") or 0)

        deposit_tail_users_total = float(
            row.get("deposit_tail_cumulative_users")
            or (deposit_tail_users_total + float(row.get("deposit_tail_users") or 0))
        )
        deposit_tail_revenue_total = float(
            row.get("deposit_tail_cumulative_revenue")
            or (deposit_tail_revenue_total + float(row.get("deposit_tail_revenue") or 0))
        )
        reservoir_tail_users_total = float(
            row.get("reservoir_tail_cumulative_users")
            or (reservoir_tail_users_total + float(row.get("reservoir_tail_users") or 0))
        )
        reservoir_tail_revenue_total = float(
            row.get("reservoir_tail_cumulative_revenue")
            or (reservoir_tail_revenue_total + float(row.get("reservoir_tail_revenue") or 0))
        )
        reservoir_conversion_users_total = float(
            row.get("reservoir_conversion_cumulative_users")
            or (reservoir_conversion_users_total + float(row.get("reservoir_conversion_users") or 0))
        )
        reservoir_conversion_revenue_total = float(
            row.get("reservoir_conversion_cumulative_revenue")
            or (reservoir_conversion_revenue_total + float(row.get("reservoir_conversion_revenue") or 0))
        )
        reservoir_july_conversion_users_total = float(
            row.get("reservoir_july_conversion_cumulative_users")
            or (reservoir_july_conversion_users_total + float(row.get("reservoir_july_conversion_users") or 0))
        )
        reservoir_july_conversion_revenue_total = float(
            row.get("reservoir_july_conversion_cumulative_revenue")
            or (reservoir_july_conversion_revenue_total + float(row.get("reservoir_july_conversion_revenue") or 0))
        )

        item["revenue_amount_cumulative"] = revenue_total
        item["app_new_users_cumulative"] = app_total
        item["deposit_tail_cumulative_users"] = deposit_tail_users_total
        item["deposit_tail_cumulative_revenue"] = deposit_tail_revenue_total
        item["deposit_tail_rate_cumulative"] = safe_div(deposit_tail_users_total, row.get("deposit_users"))
        item["deposit_tail_revenue_share_cumulative"] = safe_div(deposit_tail_revenue_total, revenue_total)
        item["reservoir_tail_cumulative_users"] = reservoir_tail_users_total
        item["reservoir_tail_cumulative_revenue"] = reservoir_tail_revenue_total
        item["reservoir_tail_rate_cumulative"] = safe_div(reservoir_tail_users_total, row.get("reservoir_users"))
        item["reservoir_conversion_cumulative_users"] = reservoir_conversion_users_total
        item["reservoir_conversion_cumulative_revenue"] = reservoir_conversion_revenue_total
        item["reservoir_conversion_rate_cumulative"] = safe_div(reservoir_conversion_users_total, row.get("reservoir_users"))
        item["reservoir_july_conversion_cumulative_users"] = reservoir_july_conversion_users_total
        item["reservoir_july_conversion_cumulative_revenue"] = reservoir_july_conversion_revenue_total
        item["reservoir_july_conversion_rate_cumulative"] = safe_div(reservoir_july_conversion_users_total, row.get("reservoir_users"))
        item["family_order_share_daily"] = safe_div(row.get("family_orders"), row.get("family_base_orders"))
        item["family_primary_share_daily"] = safe_div(row.get("family_primary_orders"), row.get("family_primary_base_orders"))
        item["family_middle_share_daily"] = safe_div(row.get("family_middle_orders"), row.get("family_middle_base_orders"))
        item["family_high_share_daily"] = safe_div(row.get("family_high_orders"), row.get("family_high_base_orders"))
        item["from_primary_order_share_daily"] = safe_div(row.get("from_primary_orders"), row.get("from_primary_base_orders"))
        item["from_primary_primary_share_daily"] = safe_div(row.get("from_primary_primary_orders"), row.get("from_primary_primary_base_orders"))
        for hidden_reservoir_field in (
            "reservoir_may_tail_users",
            "reservoir_may_tail_orders",
            "reservoir_may_tail_revenue",
            "reservoir_june_tail_users",
            "reservoir_june_tail_orders",
            "reservoir_june_tail_revenue",
        ):
            item.pop(hidden_reservoir_field, None)
        rows.append(item)

    if rows:
        latest = rows[-1]
        latest["revenue_amount_cumulative"] = metrics["revenue"]["amount"]
        latest["app_new_users_cumulative"] = metrics["app_flow"]["users"]
        latest["deposit_users"] = metrics["deposit"]["users"]
        latest["deposit_tail_cumulative_users"] = metrics["deposit"]["tail_users"]
        latest["deposit_tail_cumulative_revenue"] = metrics["deposit"]["tail_revenue"]
        latest["deposit_tail_rate_cumulative"] = metrics["deposit"]["tail_rate"]
        latest["deposit_tail_revenue_share_cumulative"] = metrics["deposit"]["tail_revenue_share"]
        latest["reservoir_users"] = metrics["reservoir"]["users"]
        latest["reservoir_tail_cumulative_users"] = metrics["reservoir"]["tail_users"]
        latest["reservoir_tail_cumulative_revenue"] = metrics["reservoir"]["revenue"]
        latest["reservoir_tail_rate_cumulative"] = metrics["reservoir"]["tail_rate"]
        latest["reservoir_conversion_cumulative_users"] = metrics["reservoir"]["conversion_users"]
        latest["reservoir_conversion_cumulative_revenue"] = metrics["reservoir"]["conversion_revenue"]
        latest["reservoir_conversion_rate_cumulative"] = metrics["reservoir"]["conversion_rate"]
        latest["reservoir_july_conversion_cumulative_users"] = metrics["reservoir"]["july_conversion_users"]
        latest["reservoir_july_conversion_cumulative_revenue"] = metrics["reservoir"]["july_conversion_revenue"]
        latest["reservoir_july_conversion_rate_cumulative"] = metrics["reservoir"]["july_conversion_rate"]
        latest["family_order_share_daily"] = metrics["family"]["order_share"]
        latest["family_primary_share_daily"] = metrics["family"]["primary_share"]
        latest["family_middle_share_daily"] = metrics["family"]["middle_share"]
        latest["family_high_share_daily"] = metrics["family"]["high_share"]
        latest["from_primary_order_share_daily"] = metrics["from_primary"]["order_share"]
        latest["from_primary_primary_share_daily"] = metrics["from_primary"]["primary_share"]
    return rows


def dashboard_payload(metrics: Dict[str, Any]) -> Dict[str, Any]:
    report_window_label = report_window_label_for(metrics["report_day"])
    return {
        "version": 2,
        "report_day": ymd(metrics["report_day"]),
        "report_start": ymd(report_start_for(metrics["report_day"])),
        "report_window_label": report_window_label,
        "daily": dashboard_daily_rows(metrics),
        "revenue_progress": revenue_progress_payload_rows(metrics),
        "targets": {
            "revenue_amount": metrics["revenue"]["target"],
            "app_new_users": metrics["app_flow"]["target"],
            "deposit_users": metrics["deposit"]["target"],
            "deposit_tail_revenue_share_last_year": metrics["deposit"]["last_year_tail_revenue_share"],
            "reservoir_users": metrics["reservoir"]["target"],
        },
        "summary": {
            "revenue": format_money_wan(metrics["revenue"]["amount"]),
            "last_year_revenue_progress": format_pct(metrics["revenue"]["last_year_progress"]),
            "app_flow": format_users(metrics["app_flow"]["users"]),
            "deposit_tail_rate": format_pct(metrics["deposit"]["tail_rate"]),
            "reservoir_users": format_users(metrics["reservoir"]["users"]),
        },
        "hints": {
            "revenue": f"目标 {REVENUE_TARGET_WAN:,}万，当前完成 {format_pct(metrics['revenue']['progress'])}，去年同期完成率 {format_pct(metrics['revenue']['last_year_progress'])}",
            "app_flow": f"目标 {format_users(APP_FLOW_TARGET_USERS)}，当前完成 {format_pct(metrics['app_flow']['progress'])}，去年同期 {format_users(metrics['app_flow']['last_year_users'])}",
            "deposit": f"尾款率=定金用户中{report_window_label}购买正价组合品且组合品支付时间不早于定金支付时间的用户 / 定金用户",
            "reservoir": f"转化=蓄水用户在蓄水支付后再次购买任意商品；转大=蓄水用户中{report_window_label}购买正价组合品且组合品支付时间不早于蓄水支付时间",
            "family": "business_good_kind_name_level_3 = 小初高品，分母为 business_good_kind_name_level_1 = 组合品，按天展示订单占比",
            "from_primary": "分子=小学品加拓展，分母=小学品+小学品加拓展，按天展示订单占比",
            "high_value_renewal": "高净值活跃池=活跃表当天 business_user_pay_status_business_day 为高净值用户；续费=同日购买指定商品，今年看组合品，去年看组合品+续购",
        },
        "tables": {
            "revenue_telesale": format_money_wan(metrics["revenue"]["telesale_amount"]),
            "revenue_app": format_money_wan(metrics["revenue"]["app_amount"]),
            "revenue_yesterday": format_money_wan(metrics["revenue"]["yesterday_amount"]),
            "revenue_yoy": format_money_yoy(metrics["revenue"]["amount"], metrics["revenue"]["last_year_amount"]),
            "last_year_revenue": format_money_wan(metrics["revenue"]["last_year_amount"]),
            "last_year_progress": format_pct(metrics["revenue"]["last_year_progress"]),
            "app_flow_yesterday": format_users(metrics["app_flow"]["yesterday_users"]),
            "app_flow_yoy": format_users_yoy(metrics["app_flow"]["users"], metrics["app_flow"]["last_year_users"]),
            "deposit_users": format_users(metrics["deposit"]["users"]),
            "deposit_tail_users": format_users(metrics["deposit"]["tail_users"]),
            "deposit_tail_rate": format_pct(metrics["deposit"]["tail_rate"]),
            "deposit_tail_revenue": format_money_wan(metrics["deposit"]["tail_revenue"]),
            "deposit_tail_revenue_share": format_pct(metrics["deposit"]["tail_revenue_share"]),
            "deposit_last_year_tail_revenue_share": format_pct(metrics["deposit"]["last_year_tail_revenue_share"]),
            "deposit_tail_aov": format_money_yuan(metrics["deposit"]["tail_aov"]),
            "reservoir_users": format_users(metrics["reservoir"]["users"]),
            "reservoir_total_tail_users": format_users(metrics["reservoir"]["total_tail_users"]),
            "reservoir_total_tail_rate": format_pct(metrics["reservoir"]["total_tail_rate"]),
            "reservoir_total_tail_orders": format_orders(metrics["reservoir"]["total_tail_orders"]),
            "reservoir_total_revenue": format_money_wan(metrics["reservoir"]["total_tail_revenue"]),
            "reservoir_conversion_users": format_users(metrics["reservoir"]["conversion_users"]),
            "reservoir_conversion_orders": format_orders(metrics["reservoir"]["conversion_orders"]),
            "reservoir_conversion_rate": format_pct(metrics["reservoir"]["conversion_rate"]),
            "reservoir_conversion_revenue": format_money_wan(metrics["reservoir"]["conversion_revenue"]),
            "reservoir_july_conversion_users": format_users(metrics["reservoir"]["july_conversion_users"]),
            "reservoir_july_conversion_orders": format_orders(metrics["reservoir"]["july_conversion_orders"]),
            "reservoir_july_conversion_rate": format_pct(metrics["reservoir"]["july_conversion_rate"]),
            "reservoir_july_conversion_revenue": format_money_wan(metrics["reservoir"]["july_conversion_revenue"]),
            "reservoir_tail_rate": format_pct(metrics["reservoir"]["tail_rate"]),
            "reservoir_tail_users": format_users(metrics["reservoir"]["tail_users"]),
            "reservoir_tail_orders": format_orders(metrics["reservoir"].get("tail_orders", 0)),
            "reservoir_revenue": format_money_wan(metrics["reservoir"]["revenue"]),
           "family_order_share": format_pct(metrics["family"]["order_share"]),
            "family_primary_share": format_pct(metrics["family"]["primary_share"]),
            "family_middle_share": format_pct(metrics["family"]["middle_share"]),
            "family_high_share": format_pct(metrics["family"]["high_share"]),
           "family_revenue": format_money_wan(metrics["family"]["revenue"]),
           "from_primary_order_share": format_pct(metrics["from_primary"]["order_share"]),
            "from_primary_primary_share": format_pct(metrics["from_primary"]["primary_share"]),
           "from_primary_revenue": format_money_wan(metrics["from_primary"]["revenue"]),
            "high_value_renew_rate": format_pct(metrics["high_value_renewal"]["renew_rate"]),
            "high_value_renew_aov": format_money_yuan(metrics["high_value_renewal"]["renew_aov"]),
            "high_value_renew_rate_yoy": format_rate_yoy(metrics["high_value_renewal"]["renew_rate"], metrics["high_value_renewal"]["last_year_renew_rate"]),
            "high_value_renew_aov_yoy": format_yuan_yoy(metrics["high_value_renewal"]["renew_aov"], metrics["high_value_renewal"]["last_year_renew_aov"]),
        },
    }


def encode_dashboard_payload(metrics: Dict[str, Any]) -> str:
    raw = json.dumps(dashboard_payload(metrics), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compressed = zlib.compress(raw, 9)
    return base64.urlsafe_b64encode(compressed).decode("ascii").rstrip("=")


def build_detail_url(metrics: Dict[str, Any], base_url: str = KEY_METRICS_DETAIL_URL) -> str:
    clean_base = base_url.split("#", 1)[0]
    separator = "&" if "?" in clean_base else "?"
    encoded_payload = encode_dashboard_payload(metrics)
    version = f"{yyyymmdd(metrics['report_day'])}_{zlib.crc32(encoded_payload.encode('ascii')) & 0xFFFFFFFF:08x}"
    return f"{clean_base}{separator}v={version}#payload={encoded_payload}"


def fine_dashboard_field_dictionary_html() -> str:
    summary_fields = [
        ("year_month", "月份，固定为 202607。"),
        ("date_sk", "日期，例如 20260701。"),
        ("channel", "渠道，包含 APP、电销、整体。"),
        ("month_begin_timestamp", "当月开始日期。"),
        ("month_end_timestamp", "当月结束日期。"),
        ("day_timestamp", "当前行对应日期。"),
        ("month_day_cnt", "当月总天数，7 月为 31 天。"),
        ("month_day", "当前是当月第几天。"),
        ("target_revenue", "当天营收目标，每日营收目标来自 revenue_target_GMV。"),
        ("real_revenue", "当天实际营收。"),
        ("month_total_target", "当月总目标。"),
        ("cumulative_target_revenue", "截至当天的累计目标营收。"),
        ("cumulative_real_revenue", "截至当天的累计实际营收。"),
        ("time_progress", "时间进度，即已过天数 / 当月总天数。"),
        ("predicted_target_progress", "目标进度，即累计目标 / 当月总目标。"),
        ("actual_completion_progress", "实际完成进度，即累计实际营收 / 当月总目标。"),
        ("forecast_completion_progress", "按当前日均营收推算的月底预计完成进度。"),
        ("actual_vs_cumulative_target_progress", "实际营收相对当前累计目标的完成度。"),
        ("daily_target_gap", "当天目标缺口，计算为当天目标 - 当天实际。"),
        ("cumulative_target_gap", "累计目标缺口，计算为累计目标 - 累计实际。"),
    ]
    detail_fields = [
        ("year_month", "月份，固定为 202607。"),
        ("date_sk", "日期，例如 20260701。"),
        ("period", "时期，月日格式，例如 0701。"),
        ("channel", "渠道，包含 APP、电销、整体，可用于筛选。"),
        ("cumulative_real_revenue", "截至当天的累计实际营收。"),
        ("lastyear_cumulative_real_revenue", "去年同期截至同一天的累计实际营收。"),
        ("revenue_gap", "累计实际营收与去年同期累计实际营收的差值。"),
        ("real_revenue", "当天实际营收。"),
        ("lastyear_real_revenue", "去年同期当天实际营收。"),
        ("lastyear_daily_revenue_gap", "当天实际营收与去年同期当天实际营收的差值。"),
        ("actual_target_completion_progress", "实际目标达成进度，即累计实际营收 / 当月总目标。"),
        ("lastyear_revenue_progress", "去年同期营收进度，即去年同期累计实际营收 / 今年当月总目标。"),
        ("forecast_target_completion_progress", "按当前日均营收推算的月底预计目标达成进度。"),
        ("cumulative_target_revenue", "截至当天的累计目标营收。"),
        ("cumulative_revenue_gap", "累计营收差值，计算为累计实际 - 累计目标。"),
        ("target_daily_revenue", "当天目标营收，每日营收目标来自 revenue_target_GMV。"),
        ("daily_revenue_gap", "每日营收差值，计算为当天实际 - 当天目标。"),
    ]

    def rows(items: List[Tuple[str, str]]) -> str:
        return "".join(
            f"<tr><td><code>{html.escape(field)}</code></td><td>{html.escape(description)}</td></tr>"
            for field, description in items
        )

    return f"""
    <section>
      <div class="head">
        <h2>冲顶帆软底表字段说明</h2>
        <div class="hint">用于帆软接表、筛选和核对口径</div>
      </div>
      <p class="field-note">目标表：<code>tmp.xuxingling_202607_chongding_revenue_target</code>；每日营收目标来自 <code>revenue_target_GMV</code>。</p>
      <h3>汇总进度表：<code>tmp.xuxingling_202607_chongding_fine_summary</code></h3>
      <div class="chart-wrap"><table class="field-table"><thead><tr><th>字段</th><th>含义</th></tr></thead><tbody>{rows(summary_fields)}</tbody></table></div>
      <h3>明细趋势表：<code>tmp.xuxingling_202607_chongding_fine_detail</code></h3>
      <div class="chart-wrap"><table class="field-table"><thead><tr><th>字段</th><th>含义</th></tr></thead><tbody>{rows(detail_fields)}</tbody></table></div>
    </section>"""


def _row_by_channel(rows: List[Dict[str, Any]], channel: str) -> Dict[str, Any]:
    return next((row for row in rows if row.get("channel") == channel), {})


def revenue_dial_html(title: str, value: str, pct_value: Number, tone: str) -> str:
    return f"""
        <div class="revenue-dial-card">
          <div class="dial-title">{html.escape(title)}</div>
          <div class="revenue-dial" style="--pct:{_css_pct(pct_value)};--tone:{tone};">
            <div class="dial-inner">
              <strong>{html.escape(value)}</strong>
            </div>
          </div>
        </div>"""


def channel_meter_html(row: Dict[str, Any], tone: str) -> str:
    channel = str(row.get("channel") or "-")
    actual_progress = float(row.get("actual_progress_value") or 0)
    target_progress = float(row.get("target_progress_value") or 0)
    channel_label = "APP" if channel == "APP" else "电销"
    return f"""
        <div class="channel-meter">
          <div class="meter-head">
            <div>
              <div class="meter-title" style="color:{tone};">{html.escape(channel)}</div>
              <div class="meter-kv">{html.escape(channel_label)}营收目标 <strong>{html.escape(str(row.get("month_target_short") or "-"))}</strong></div>
              <div class="meter-money">{html.escape(str(row.get("cumulative_actual") or "-"))}</div>
            </div>
            <div class="meter-pct" style="color:{tone};">{html.escape(str(row.get("actual_progress") or "-"))}</div>
          </div>
          <div class="meter-body">
            <div class="thermo">
              <div class="thermo-target" style="bottom:{_css_pct(target_progress)};"></div>
              <div class="thermo-fill" style="height:{_css_pct(actual_progress)};background:{tone};"></div>
            </div>
            <div class="meter-scale">
              <span>100%</span><span>75%</span><span>50%</span><span>25%</span><span>0%</span>
            </div>
          </div>
          <div class="meter-foot">{html.escape(channel_label)}预测目标进度 {html.escape(str(row.get("target_progress") or "-"))} · 实际完成 {html.escape(str(row.get("actual_progress") or "-"))}</div>
        </div>"""


def revenue_progress_section_html(rows: List[Dict[str, Any]]) -> str:
    overall = _row_by_channel(rows, "整体")
    app = _row_by_channel(rows, "APP")
    telesale = _row_by_channel(rows, "电销")
    channel_rows = [row for row in (app, telesale) if row]
    app_share = float(app.get("mix_share_value") or 0)
    telesale_share = float(telesale.get("mix_share_value") or 0)
    return f"""
    <section class="revenue-visual">
      <div class="head">
        <h2>冲顶营收进度</h2>
        <div class="hint">营收目标来自 revenue_target_GMV，按整体、APP、电销拆分</div>
      </div>
      <div id="revenue_progress_visual">
        <div class="revenue-hero">
          <div class="headline-number">
            <span>当前预测目标</span>
            <strong>{html.escape(str(overall.get("month_target") or "-"))}</strong>
          </div>
          <div class="headline-number right">
            <span>累计实际营收</span>
            <strong>{html.escape(str(overall.get("cumulative_actual") or "-"))}</strong>
          </div>
        </div>
        <div class="dial-grid">
          {revenue_dial_html("时间进度", str(overall.get("time_progress") or "-"), overall.get("time_progress_value"), "#7fc97b")}
          {revenue_dial_html("目标进度", str(overall.get("target_progress") or "-"), overall.get("target_progress_value"), "#6b7280")}
          {revenue_dial_html("实际完成", str(overall.get("actual_progress") or "-"), overall.get("actual_progress_value"), "#f97316")}
        </div>
        <div class="channel-visuals">
          <div class="channel-grid">
            {"".join(channel_meter_html(row, "#2563eb" if row.get("channel") == "APP" else "#f59e0b") for row in channel_rows)}
          </div>
          <div class="mix-panel">
            <h3>APP与电销营收占比</h3>
            <div class="mix-bar">
              <div class="mix-app" style="flex-basis:{_css_pct(app_share)};">{html.escape(str(app.get("mix_share") or "-"))}</div>
              <div class="mix-sale" style="flex-basis:{_css_pct(telesale_share)};">{html.escape(str(telesale.get("mix_share") or "-"))}</div>
            </div>
            <div class="mix-legend"><span class="blue">APP {html.escape(str(app.get("cumulative_actual") or "-"))}</span><span class="orange">电销 {html.escape(str(telesale.get("cumulative_actual") or "-"))}</span></div>
          </div>
        </div>
      </div>
    </section>"""


def build_html(metrics: Dict[str, Any], snapshot_url: Optional[str] = None) -> str:
    report_day = metrics["report_day"]
    report_start = report_start_for(report_day)
    report_window_label = report_window_label_for(report_day)
    summary = {
        "revenue": format_money_wan(metrics["revenue"]["amount"]),
        "app_flow": format_users(metrics["app_flow"]["users"]),
        "deposit_tail_rate": format_pct(metrics["deposit"]["tail_rate"]),
        "reservoir_users": format_users(metrics["reservoir"]["users"]),
    }
    payload = dashboard_payload(metrics)
    payload_json = _json_for_html(payload)
    snapshot_fetch_js = (
        f"fetch({_json_for_html(snapshot_url)}, {{cache: \"no-store\"}})"
        if snapshot_url
        else "Promise.resolve(null)"
    )
    revenue_progress_html = revenue_progress_section_html(payload["revenue_progress"])

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>问鼎·C端私域数据趋势看板</title>
  <style>
    :root {{ --ink:#172033; --muted:#667085; --line:#b8e4e7; --blue:#2563eb; --green:#16a34a; --cyan:#0891b2; --orange:#f97316; --purple:#7c3aed; --bg:#e9fbfb; --card:#fff; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; color:var(--ink); background:var(--bg); }}
    main {{ width:min(1180px, calc(100vw - 32px)); margin:24px auto 40px; }}
    header, section {{ background:var(--card); border:1px solid var(--line); border-radius:16px; box-shadow:0 8px 24px rgba(23,32,51,.05); }}
    header {{ padding:24px 28px; background:linear-gradient(135deg,#d7f7f7,#fff); }}
    h1 {{ margin:0; font-size:28px; line-height:1.2; letter-spacing:0; }}
    h2 {{ margin:0; font-size:20px; line-height:1.3; }}
    .sub, .hint, footer {{ color:var(--muted); }}
    .sub {{ margin-top:8px; font-size:14px; }}
    .snapshot-notice {{ margin:12px 0 0; padding:10px 14px; border:1px solid #f7c873; border-radius:10px; background:#fff8e8; color:#8a5a00; font-size:13px; }}
    .snapshot-notice[hidden] {{ display:none; }}
    .summary {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-top:18px; }}
    .metric {{ background:rgba(255,255,255,.85); border:1px solid var(--line); border-radius:12px; padding:14px; }}
    .label {{ color:var(--muted); font-size:13px; }}
    .value {{ margin-top:8px; font-size:24px; font-weight:760; }}
    section {{ margin-top:16px; padding:20px 24px; }}
    .head {{ display:flex; align-items:baseline; justify-content:space-between; gap:16px; margin-bottom:12px; }}
    .hint {{ font-size:13px; text-align:right; }}
    .chart-wrap {{ width:100%; overflow-x:auto; }}
    svg {{ width:100%; min-width:860px; height:260px; display:block; }}
    .axis {{ stroke:#d0d7e5; stroke-width:1; }}
    .grid {{ stroke:#edf1f7; stroke-width:1; }}
    .tick {{ fill:#667085; font-size:12px; }}
    .chart-title {{ fill:#344054; font-size:14px; font-weight:700; }}
    .axis-label {{ fill:#667085; font-size:12px; font-weight:650; }}
    .value-label {{ fill:#344054; font-size:12px; font-weight:700; paint-order:stroke; stroke:#fff; stroke-width:4px; stroke-linejoin:round; }}
    .legend {{ display:flex; gap:18px; flex-wrap:wrap; margin-top:10px; color:var(--muted); font-size:13px; }}
    .legend span::before {{ content:""; display:inline-block; width:10px; height:10px; margin-right:6px; border-radius:50%; background:currentColor; }}
    .blue {{ color:var(--blue); }} .green {{ color:var(--green); }} .cyan {{ color:var(--cyan); }} .orange {{ color:var(--orange); }} .purple {{ color:var(--purple); }}
    table {{ width:100%; border-collapse:collapse; margin-top:8px; font-size:14px; }}
    th,td {{ border-bottom:1px solid #edf1f7; padding:10px 8px; text-align:left; white-space:nowrap; }}
    th {{ color:var(--muted); font-weight:650; }}
    h3 {{ margin:18px 0 8px; font-size:15px; line-height:1.4; }}
    code {{ font-family:"SFMono-Regular","Consolas","Liberation Mono",monospace; font-size:.92em; color:#30405f; }}
    .field-note {{ margin:0 0 10px; color:var(--muted); font-size:13px; line-height:1.6; }}
    .progress-note {{ margin:0 0 10px; color:var(--muted); font-size:13px; line-height:1.6; }}
    .field-table td:nth-child(2) {{ white-space:normal; line-height:1.55; }}
    .progress-table td:not(:first-child), .progress-table th:not(:first-child) {{ text-align:right; }}
    .summary-row td {{ font-weight:760; background:#f8fbff; }}
    .revenue-visual {{ background:#eef8ff; border-color:#a9d8f1; }}
    .revenue-hero {{ display:grid; grid-template-columns:1fr 1fr; gap:1px; margin:-20px -24px 16px; border-bottom:1px solid #b9def2; background:#c7e5f7; }}
    .headline-number {{ background:#eef8ff; padding:26px 32px; text-align:center; }}
    .headline-number span {{ display:block; color:#344054; font-weight:760; font-size:20px; }}
    .headline-number strong {{ display:block; margin-top:10px; color:#4b5563; font-size:30px; font-style:italic; letter-spacing:1px; }}
    .headline-number.right strong {{ color:#f59e0b; }}
    .dial-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }}
    .revenue-dial-card {{ min-height:250px; border:1px solid #a9d8f1; background:#f6fbff; padding:14px; text-align:center; }}
    .dial-title {{ color:#344054; font-weight:700; text-align:left; font-size:14px; }}
    .revenue-dial {{ width:168px; height:168px; margin:18px auto 0; border-radius:50%; background:conic-gradient(var(--tone) 0 var(--pct), #d7e5f0 var(--pct) 100%); display:grid; place-items:center; box-shadow:inset 0 0 0 12px rgba(255,255,255,.78), 0 6px 14px rgba(23,32,51,.08); }}
    .dial-inner {{ width:108px; height:108px; border-radius:50%; background:#f8fbff; display:grid; place-items:center; color:#4b5563; }}
    .dial-inner strong {{ font-size:22px; font-style:italic; }}
    .channel-visuals {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-top:10px; }}
    .channel-grid {{ display:contents; }}
    .channel-meter, .mix-panel {{ border:1px solid #a9d8f1; background:#f6fbff; padding:16px; min-height:270px; }}
    .meter-head {{ display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }}
    .meter-title {{ font-size:24px; font-weight:800; }}
    .meter-kv {{ margin-top:8px; color:#667085; font-size:13px; }}
    .meter-kv strong {{ color:#344054; font-size:18px; margin-left:6px; }}
    .meter-money {{ margin-top:8px; color:#ef3b1a; font-weight:850; font-size:24px; font-style:italic; }}
    .meter-pct {{ font-size:20px; font-weight:850; font-style:italic; }}
    .meter-body {{ display:flex; justify-content:center; gap:14px; align-items:center; margin-top:12px; }}
    .thermo {{ position:relative; width:16px; height:164px; border-radius:10px; background:#d9e8f2; overflow:hidden; }}
    .thermo-fill {{ position:absolute; left:0; right:0; bottom:0; border-radius:10px; min-height:4px; }}
    .thermo-target {{ position:absolute; left:-4px; right:-4px; height:2px; background:#344054; z-index:2; }}
    .meter-scale {{ height:164px; display:flex; flex-direction:column; justify-content:space-between; color:#667085; font-size:12px; }}
    .meter-foot {{ color:var(--muted); font-size:12px; text-align:center; margin-top:10px; }}
    .mix-panel h3 {{ text-align:center; margin-top:0; }}
    .mix-bar {{ height:220px; width:76px; margin:10px auto; display:flex; flex-direction:column; justify-content:flex-end; border-radius:12px; overflow:hidden; background:#d9e8f2; }}
    .mix-bar div {{ display:grid; place-items:center; min-height:28px; color:white; font-weight:700; }}
    .mix-app {{ background:#7896ba; }}
    .mix-sale {{ background:#f6bd68; }}
    .mix-legend {{ display:flex; justify-content:center; gap:12px; flex-wrap:wrap; font-size:12px; color:var(--muted); }}
    footer {{ font-size:12px; margin-top:18px; line-height:1.6; }}
    @media (max-width:900px) {{ .dial-grid, .channel-visuals, .channel-grid, .revenue-hero {{ grid-template-columns:1fr; }} .revenue-hero {{ margin:-16px -16px 16px; }} }}
    @media (max-width:760px) {{ main {{ width:min(100vw - 20px,1180px); margin-top:12px; }} header,section {{ padding:16px; border-radius:12px; }} .summary {{ grid-template-columns:repeat(2,1fr); }} h1 {{ font-size:22px; }} .value {{ font-size:20px; }} .headline-number strong {{ font-size:24px; }} }}
  </style>
</head>
<body>
  <main>
{revenue_progress_html}
    <header>
      <h1>问鼎·C端私域数据趋势看板</h1>
      <div class="sub" id="report_day_text">数据截止 {html.escape(ymd(report_day))}</div>
      <div class="summary">
        <div class="metric"><div class="label">私域累计营收</div><div class="value blue" id="summary_revenue">{html.escape(summary["revenue"])}</div></div>
        <div class="metric"><div class="label">APP累计新增流量</div><div class="value green" id="summary_app_flow">{html.escape(summary["app_flow"])}</div></div>
        <div class="metric"><div class="label">定金尾款率</div><div class="value blue" id="summary_deposit_tail_rate">{html.escape(summary["deposit_tail_rate"])}</div></div>
        <div class="metric"><div class="label">蓄水用户数</div><div class="value cyan" id="summary_reservoir_users">{html.escape(summary["reservoir_users"])}</div></div>
      </div>
    </header>
    <div id="snapshot_notice" class="snapshot-notice" role="status" hidden></div>
    <section><div class="head"><h2>私域营收进度</h2><div class="hint" id="hint_revenue">目标 {REVENUE_TARGET_WAN:,}万，当前完成 {format_pct(metrics["revenue"]["progress"])}，去年同期完成率 {format_pct(metrics["revenue"]["last_year_progress"])}</div></div><div class="chart-wrap"><svg id="revenue_amount"></svg></div><div class="legend"><span class="blue">累计营收</span><span class="orange">目标线</span></div><table><thead><tr><th>指标</th><th>当前值</th></tr></thead><tbody><tr><td>电销营收</td><td id="revenue_telesale_value">{format_money_wan(metrics["revenue"]["telesale_amount"])}</td></tr><tr><td>APP营收</td><td id="revenue_app_value">{format_money_wan(metrics["revenue"]["app_amount"])}</td></tr><tr><td>去年同期营收</td><td id="last_year_revenue_value">{format_money_wan(metrics["revenue"]["last_year_amount"])}</td></tr><tr><td>去年同期完成率</td><td id="last_year_progress_value">{format_pct(metrics["revenue"]["last_year_progress"])}</td></tr></tbody></table></section>
    <section><div class="head"><h2>APP新增流量进度</h2><div class="hint" id="hint_app_flow">目标 {format_users(APP_FLOW_TARGET_USERS)}，当前完成 {format_pct(metrics["app_flow"]["progress"])}</div></div><div class="chart-wrap"><svg id="app_new_users"></svg></div><div class="legend"><span class="green">累计新增用户</span><span class="orange">目标线</span></div></section>
    <section><div class="head"><h2>定金量与尾款表现</h2><div class="hint" id="hint_deposit">尾款率=定金用户中{report_window_label}购买正价组合品且组合品支付时间不早于定金支付时间的用户 / 定金用户</div></div><div class="chart-wrap"><svg id="deposit_tail_rate"></svg></div><div class="legend"><span class="purple">累计尾款率</span></div><div class="chart-wrap"><svg id="deposit_tail_revenue_share"></svg></div><div class="legend"><span class="blue">定金尾款占C端营收</span><span class="orange">去年同期尾款占比</span></div><table><thead><tr><th>指标</th><th>当前值</th><th>说明</th></tr></thead><tbody><tr><td>定金用户</td><td id="deposit_users_value">{format_users(metrics["deposit"]["users"])}</td><td>6月24日至6月30日，商业化+电销</td></tr><tr><td>尾款量</td><td id="deposit_tail_users_value">{format_users(metrics["deposit"]["tail_users"])}</td><td>定金用户中{report_window_label}购买正价组合品且支付时间不早于定金支付时间</td></tr><tr><td>尾款率</td><td id="deposit_tail_rate_value">{format_pct(metrics["deposit"]["tail_rate"])}</td><td>累计尾款量 / 定金用户</td></tr><tr><td>尾款客单价</td><td id="deposit_tail_aov_value">{format_money_yuan(metrics["deposit"]["tail_aov"])}</td><td>尾款营收贡献 / 尾款量</td></tr><tr><td>定金尾款占C端营收</td><td id="deposit_tail_revenue_share_value">{format_pct(metrics["deposit"]["tail_revenue_share"])}</td><td>累计尾款营收 / 累计C端营收</td></tr><tr><td>去年同期尾款占比</td><td id="deposit_last_year_tail_revenue_share_value">{format_pct(metrics["deposit"]["last_year_tail_revenue_share"])}</td><td>去年同期累计尾款营收 / 去年同期累计C端营收</td></tr></tbody></table></section>
    <section><div class="head"><h2>蓄水量</h2><div class="hint" id="hint_reservoir">蓄水用户=5/22-6/30购买同步课加培优课流量品用户；转化=蓄水支付后再次购买任意商品；转大=购买正价组合品</div></div><div class="chart-wrap"><svg id="reservoir_tail_rate"></svg></div><div class="legend"><span class="purple">7月累计转大率</span></div><div class="chart-wrap"><svg id="reservoir_revenue"></svg></div><div class="legend"><span class="cyan">7月累计转大营收</span></div><table><thead><tr><th>指标</th><th>用户数</th><th>订单数</th><th>占比</th><th>营收贡献</th></tr></thead><tbody><tr><td>蓄水用户</td><td id="reservoir_users_value">{format_users(metrics["reservoir"]["users"])}</td><td>-</td><td>-</td><td>-</td></tr><tr><td>累计转化</td><td id="reservoir_conversion_users_value">{format_users(metrics["reservoir"]["conversion_users"])}</td><td id="reservoir_conversion_orders_value">{format_orders(metrics["reservoir"]["conversion_orders"])}</td><td id="reservoir_conversion_rate_value">{format_pct(metrics["reservoir"]["conversion_rate"])}</td><td id="reservoir_conversion_revenue_value">{format_money_wan(metrics["reservoir"]["conversion_revenue"])}</td></tr><tr><td>7月转化</td><td id="reservoir_july_conversion_users_value">{format_users(metrics["reservoir"]["july_conversion_users"])}</td><td id="reservoir_july_conversion_orders_value">{format_orders(metrics["reservoir"]["july_conversion_orders"])}</td><td id="reservoir_july_conversion_rate_value">{format_pct(metrics["reservoir"]["july_conversion_rate"])}</td><td id="reservoir_july_conversion_revenue_value">{format_money_wan(metrics["reservoir"]["july_conversion_revenue"])}</td></tr><tr><td>累计转大</td><td id="reservoir_total_tail_users_value">{format_users(metrics["reservoir"]["total_tail_users"])}</td><td id="reservoir_total_tail_orders_value">{format_orders(metrics["reservoir"]["total_tail_orders"])}</td><td id="reservoir_total_tail_rate_value">{format_pct(metrics["reservoir"]["total_tail_rate"])}</td><td id="reservoir_total_revenue_value">{format_money_wan(metrics["reservoir"]["total_tail_revenue"])}</td></tr><tr><td>7月累计转大</td><td id="reservoir_tail_users_value">{format_users(metrics["reservoir"]["tail_users"])}</td><td id="reservoir_tail_orders_value">{format_orders(metrics["reservoir"].get("tail_orders", 0))}</td><td id="reservoir_tail_rate_value">{format_pct(metrics["reservoir"]["tail_rate"])}</td><td id="reservoir_revenue_value">{format_money_wan(metrics["reservoir"]["revenue"])}</td></tr></tbody></table></section>
    <section><div class="head"><h2>家庭包</h2><div class="hint" id="hint_family">business_good_kind_name_level_3 = 小初高品，分母为 business_good_kind_name_level_1 = 组合品，按天展示订单占比</div></div><div class="chart-wrap"><svg id="family_order_share"></svg></div><div class="legend"><span class="purple">总占比</span><span class="blue">小学团占比</span><span class="green">初中团占比</span><span class="orange">高中团占比</span></div><table><thead><tr><th>汇总订单占比</th><th>小学团占比</th><th>初中团占比</th><th>高中团占比</th><th>营收贡献</th><th>分母</th></tr></thead><tbody><tr><td id="family_order_share_value">{format_pct(metrics["family"]["order_share"])}</td><td id="family_primary_share">{format_pct(metrics["family"]["primary_share"])}</td><td id="family_middle_share">{format_pct(metrics["family"]["middle_share"])}</td><td id="family_high_share">{format_pct(metrics["family"]["high_share"])}</td><td id="family_revenue_value">{format_money_wan(metrics["family"]["revenue"])}</td><td>business_good_kind_name_level_1 = 组合品</td></tr></tbody></table></section>
    <section><div class="head"><h2>从小学</h2><div class="hint" id="hint_from_primary">分子=小学品加拓展，分母=小学品+小学品加拓展，按天展示订单占比</div></div><div class="chart-wrap"><svg id="from_primary_order_share"></svg></div><div class="legend"><span class="orange">总占比</span><span class="blue">小学团占比</span></div><table><thead><tr><th>汇总订单占比</th><th>小学团占比</th><th>营收贡献</th><th>分母</th></tr></thead><tbody><tr><td id="from_primary_order_share_value">{format_pct(metrics["from_primary"]["order_share"])}</td><td id="from_primary_primary_share">{format_pct(metrics["from_primary"]["primary_share"])}</td><td id="from_primary_revenue_value">{format_money_wan(metrics["from_primary"]["revenue"])}</td><td>小学品+小学品加拓展</td></tr></tbody></table></section>
    <section><div class="head"><h2>高净值续费</h2><div class="hint" id="hint_high_value_renewal">高净值活跃池=活跃表当天 business_user_pay_status_business_day 为高净值用户；续费=同日购买指定商品，今年看组合品，去年看组合品+续购</div></div><table><thead><tr><th>续费率</th><th>续费率同比</th><th>续费客单价</th><th>客单价同比</th></tr></thead><tbody><tr><td id="high_value_renew_rate_value">{format_pct(metrics["high_value_renewal"]["renew_rate"])}</td><td id="high_value_renew_rate_yoy">{html.escape(format_rate_yoy(metrics["high_value_renewal"]["renew_rate"], metrics["high_value_renewal"]["last_year_renew_rate"]))}</td><td id="high_value_renew_aov_value">{format_money_yuan(metrics["high_value_renewal"]["renew_aov"])}</td><td id="high_value_renew_aov_yoy">{html.escape(format_yuan_yoy(metrics["high_value_renewal"]["renew_aov"], metrics["high_value_renewal"]["last_year_renew_aov"]))}</td></tr></tbody></table></section>
    <footer>说明：趋势从{ymd(report_start)}开始按天展示，没数据日期展示0；金额来自 dws.topic_order_detail.sub_amount；C端口径为 business_gmv_attribution IN ('商业化','电销')。</footer>
  </main>
  <script>
    const fallbackPayload = {payload_json};
    let daily = fallbackPayload.daily;
    let targets = fallbackPayload.targets;
    function setText(id, value) {{
      const node = document.getElementById(id);
      if (node && value !== undefined && value !== null) node.textContent = value;
    }}
    async function decodePayloadFromUrl() {{
      const hashValue = new URLSearchParams(location.hash.replace(/^#/, "")).get("payload");
      const queryValue = new URLSearchParams(location.search).get("payload");
      const encoded = hashValue || queryValue;
      if (!encoded) return null;
      const padded = encoded + "=".repeat((4 - encoded.length % 4) % 4);
      const binary = Uint8Array.from(atob(padded.replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0));
      if (!("DecompressionStream" in window)) throw new Error("当前浏览器不支持链接数据解压");
      const stream = new Blob([binary]).stream().pipeThrough(new DecompressionStream("deflate"));
      return JSON.parse(await new Response(stream).text());
    }}
    async function loadSnapshot() {{
      const response = await {snapshot_fetch_js};
      if (!response) return null;
      if (!response.ok) throw new Error(`快照请求失败：${{response.status}}`);
      return response.json();
    }}
    function showSnapshotNotice(message) {{
      const notice = document.getElementById("snapshot_notice");
      if (!notice) return;
      notice.textContent = message;
      notice.hidden = !message;
    }}
    function shouldUseUrlPayload(payload) {{
      if (!payload) return false;
      if (payload.version < fallbackPayload.version) return false;
      return true;
    }}
    function cumul(field) {{
      let total = 0;
      return daily.map(row => {{ total += Number(row[field] || 0); return {{day: row.day.slice(5), value: total}}; }});
    }}
    function latest(field) {{
      return daily.map(row => ({{day: row.day.slice(5), value: Number(row[field] || 0)}}));
    }}
    function rate(numField, denField) {{
      return daily.map(row => ({{day: row.day.slice(5), value: Number(row[denField] || 0) ? Number(row[numField] || 0) / Number(row[denField]) : 0}}));
    }}
    function cumulativeRate(numField, denField) {{
      let numerator = 0;
      let denominator = 0;
      return daily.map(row => {{
        numerator += Number(row[numField] || 0);
        denominator += Number(row[denField] || 0);
        return {{day: row.day.slice(5), value: denominator ? numerator / denominator : 0}};
      }});
    }}
    function cumulativeAgainstLatest(numField, denField) {{
      let total = 0;
      let denominator = 0;
      return daily.map(row => {{
        total += Number(row[numField] || 0);
        denominator = Number(row[denField] || denominator || 0);
        return {{day: row.day.slice(5), value: denominator ? total / denominator : 0}};
      }});
    }}
    function formatChartValue(value, format) {{
      const numeric = Number(value || 0);
      if (format === "pct") return `${{(numeric * 100).toFixed(2)}}%`;
      if (format === "money") return `¥ ${{(numeric / 10000).toFixed(2)}}万`;
      if (format === "users") return `${{Math.round(numeric).toLocaleString("zh-CN")}}人`;
      return Math.round(numeric).toLocaleString("zh-CN");
    }}
    function pointPath(points) {{
      return points.map((p, i) => `${{i === 0 ? "M" : "L"}}${{p.x.toFixed(1)}},${{p.y.toFixed(1)}}`).join(" ");
    }}
    function drawSeries(svg, points, color, format, labelOffset) {{
      svg.insertAdjacentHTML("beforeend", `<path d="${{pointPath(points)}}" fill="none" stroke="${{color}}" stroke-width="4" stroke-linecap="round"/>`);
      points.forEach((p, i) => {{
        svg.insertAdjacentHTML("beforeend", `<circle cx="${{p.x}}" cy="${{p.y}}" r="4" fill="${{color}}"/>`);
        const labelY = Math.max(18, p.y + labelOffset);
        svg.insertAdjacentHTML("beforeend", `<text class="value-label" text-anchor="middle" x="${{p.x}}" y="${{labelY}}">${{formatChartValue(p.value, format)}}</text>`);
      }});
    }}
    function draw(id, rows, options) {{
      const svg = document.getElementById(id);
      if (!svg) return;
      if (!Array.isArray(rows) || rows.length === 0) {{
        svg.setAttribute("viewBox", "0 0 980 120");
        svg.innerHTML = `<text x="24" y="64" fill="#667085" font-size="16">暂无可展示数据</text>`;
        return;
      }}
      const width = 980, height = 260, pad = {{left: 58, right: 28, top: 24, bottom: 42}};
      const maxValue = Math.max(options.target || 0, ...rows.map(r => r.value), .01) * 1.08;
      svg.setAttribute("viewBox", `0 0 ${{width}} ${{height}}`);
      svg.innerHTML = "";
      if (options.label) {{
        svg.insertAdjacentHTML("beforeend", `<text class="chart-title" x="${{pad.left}}" y="16">${{options.label}}</text>`);
      }}
      for (let i = 0; i <= 4; i++) {{
        const y = pad.top + ((height - pad.top - pad.bottom) * i) / 4;
        svg.insertAdjacentHTML("beforeend", `<line class="grid" x1="${{pad.left}}" y1="${{y}}" x2="${{width - pad.right}}" y2="${{y}}"/>`);
        const label = formatChartValue((maxValue * (4 - i)) / 4, options.format);
        svg.insertAdjacentHTML("beforeend", `<text class="tick" x="8" y="${{y + 4}}">${{label}}</text>`);
      }}
      svg.insertAdjacentHTML("beforeend", `<line class="axis" x1="${{pad.left}}" y1="${{height - pad.bottom}}" x2="${{width - pad.right}}" y2="${{height - pad.bottom}}"/>`);
      if (options.target) {{
        const targetY = pad.top + (height - pad.top - pad.bottom) - (options.target / maxValue) * (height - pad.top - pad.bottom);
        svg.insertAdjacentHTML("beforeend", `<line x1="${{pad.left}}" y1="${{targetY}}" x2="${{width - pad.right}}" y2="${{targetY}}" stroke="#f97316" stroke-width="2" stroke-dasharray="6 6"/>`);
      }}
      const innerW = width - pad.left - pad.right, innerH = height - pad.top - pad.bottom;
      const points = rows.map((row, i) => {{
        const x = pad.left + (innerW * i) / Math.max(1, rows.length - 1);
        const y = pad.top + innerH - (row.value / maxValue) * innerH;
        return {{x, y, day: row.day, value: row.value}};
      }});
      drawSeries(svg, points, options.color, options.format, -10);
      points.forEach((p, i) => {{
        svg.insertAdjacentHTML("beforeend", `<text class="tick" text-anchor="middle" x="${{p.x}}" y="${{height - 16}}">${{p.day}}</text>`);
      }});
    }}
    function drawMulti(id, seriesList, options) {{
      const svg = document.getElementById(id);
      if (!svg) return;
      const series = (Array.isArray(seriesList) ? seriesList : []).filter(item => Array.isArray(item.rows) && item.rows.length);
      if (!series.length) {{
        svg.setAttribute("viewBox", "0 0 980 120");
        svg.innerHTML = `<text x="24" y="64" fill="#667085" font-size="16">暂无可展示数据</text>`;
        return;
      }}
      const width = 980, height = 280, pad = {{left: 58, right: 112, top: 26, bottom: 42}};
      const maxValue = Math.max(...series.flatMap(item => item.rows.map(row => Number(row.value || 0))), .01) * 1.12;
      svg.setAttribute("viewBox", `0 0 ${{width}} ${{height}}`);
      svg.innerHTML = "";
      if (options && options.label) {{
        svg.insertAdjacentHTML("beforeend", `<text class="chart-title" x="${{pad.left}}" y="16">${{options.label}}</text>`);
      }}
      for (let i = 0; i <= 4; i++) {{
        const y = pad.top + ((height - pad.top - pad.bottom) * i) / 4;
        svg.insertAdjacentHTML("beforeend", `<line class="grid" x1="${{pad.left}}" y1="${{y}}" x2="${{width - pad.right}}" y2="${{y}}"/>`);
        const label = formatChartValue((maxValue * (4 - i)) / 4, options.format || "pct");
        svg.insertAdjacentHTML("beforeend", `<text class="tick" x="8" y="${{y + 4}}">${{label}}</text>`);
      }}
      svg.insertAdjacentHTML("beforeend", `<line class="axis" x1="${{pad.left}}" y1="${{height - pad.bottom}}" x2="${{width - pad.right}}" y2="${{height - pad.bottom}}"/>`);
      const innerW = width - pad.left - pad.right, innerH = height - pad.top - pad.bottom;
      series.forEach((item, seriesIndex) => {{
        const points = item.rows.map((row, i) => {{
          const x = pad.left + (innerW * i) / Math.max(1, item.rows.length - 1);
          const y = pad.top + innerH - (Number(row.value || 0) / maxValue) * innerH;
          return {{x, y, day: row.day, value: Number(row.value || 0)}};
        }});
        svg.insertAdjacentHTML("beforeend", `<path d="${{pointPath(points)}}" fill="none" stroke="${{item.color}}" stroke-width="3" stroke-linecap="round" stroke-dasharray="${{item.dash || ""}}"/>`);
        points.forEach(p => svg.insertAdjacentHTML("beforeend", `<circle cx="${{p.x}}" cy="${{p.y}}" r="3.5" fill="${{item.color}}"/>`));
        const last = points[points.length - 1];
        if (last) {{
          const labelY = Math.max(18, Math.min(height - pad.bottom - 8, last.y + (seriesIndex - 1.5) * 14));
          svg.insertAdjacentHTML("beforeend", `<text class="value-label" x="${{last.x + 8}}" y="${{labelY}}">${{item.label}} ${{formatChartValue(last.value, options.format || "pct")}}</text>`);
        }}
        points.forEach((p, i) => {{
          if (seriesIndex === 0) svg.insertAdjacentHTML("beforeend", `<text class="tick" text-anchor="middle" x="${{p.x}}" y="${{height - 16}}">${{p.day}}</text>`);
        }});
      }});
    }}
    function renderRevenueProgress(rows) {{
      const root = document.getElementById("revenue_progress_visual");
      if (!root || !Array.isArray(rows)) return;
      const esc = value => String(value ?? "-").replace(/[&<>"']/g, ch => ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}}[ch]));
      const pct = value => `${{Math.max(0, Math.min(1, Number(value || 0))) * 100}}%`;
      const byChannel = name => rows.find(row => row.channel === name) || {{}};
      const overall = byChannel("整体");
      const app = byChannel("APP");
      const sale = byChannel("电销");
      const dial = (title, value, pctValue, tone) => `
        <div class="revenue-dial-card">
          <div class="dial-title">${{esc(title)}}</div>
          <div class="revenue-dial" style="--pct:${{pct(pctValue)}};--tone:${{tone}};"><div class="dial-inner"><strong>${{esc(value)}}</strong></div></div>
        </div>`;
      const meter = (row, tone) => {{
        if (!row.channel) return "";
        const label = row.channel === "APP" ? "APP" : "电销";
        return `
        <div class="channel-meter">
          <div class="meter-head"><div><div class="meter-title" style="color:${{tone}};">${{esc(row.channel)}}</div><div class="meter-kv">${{esc(label)}}营收目标 <strong>${{esc(row.month_target_short)}}</strong></div><div class="meter-money">${{esc(row.cumulative_actual)}}</div></div><div class="meter-pct" style="color:${{tone}};">${{esc(row.actual_progress)}}</div></div>
          <div class="meter-body"><div class="thermo"><div class="thermo-target" style="bottom:${{pct(row.target_progress_value)}};"></div><div class="thermo-fill" style="height:${{pct(row.actual_progress_value)}};background:${{tone}};"></div></div><div class="meter-scale"><span>100%</span><span>75%</span><span>50%</span><span>25%</span><span>0%</span></div></div>
          <div class="meter-foot">${{esc(label)}}预测目标进度 ${{esc(row.target_progress)}} · 实际完成 ${{esc(row.actual_progress)}}</div>
        </div>`;
      }};
      root.innerHTML = `
        <div class="revenue-hero"><div class="headline-number"><span>当前预测目标</span><strong>${{esc(overall.month_target)}}</strong></div><div class="headline-number right"><span>累计实际营收</span><strong>${{esc(overall.cumulative_actual)}}</strong></div></div>
        <div class="dial-grid">${{dial("时间进度", overall.time_progress, overall.time_progress_value, "#7fc97b")}}${{dial("目标进度", overall.target_progress, overall.target_progress_value, "#6b7280")}}${{dial("实际完成", overall.actual_progress, overall.actual_progress_value, "#f97316")}}</div>
        <div class="channel-visuals"><div class="channel-grid">${{meter(app, "#2563eb")}}${{meter(sale, "#f59e0b")}}</div><div class="mix-panel"><h3>APP与电销营收占比</h3><div class="mix-bar"><div class="mix-app" style="flex-basis:${{pct(app.mix_share_value)}};">${{esc(app.mix_share)}}</div><div class="mix-sale" style="flex-basis:${{pct(sale.mix_share_value)}};">${{esc(sale.mix_share)}}</div></div><div class="mix-legend"><span class="blue">APP ${{esc(app.cumulative_actual)}}</span><span class="orange">电销 ${{esc(sale.cumulative_actual)}}</span></div></div></div>`;
    }}
    function renderDashboard(payload) {{
      daily = payload.daily || [];
      targets = payload.targets || {{}};
      setText("report_day_text", `数据截止 ${{payload.report_day || ""}}`);
      setText("summary_revenue", payload.summary && payload.summary.revenue);
      setText("summary_app_flow", payload.summary && payload.summary.app_flow);
      setText("summary_deposit_tail_rate", payload.summary && payload.summary.deposit_tail_rate);
      setText("summary_reservoir_users", payload.summary && payload.summary.reservoir_users);
      setText("hint_revenue", payload.hints && payload.hints.revenue);
      setText("hint_app_flow", payload.hints && payload.hints.app_flow);
      setText("hint_deposit", payload.hints && payload.hints.deposit);
      setText("hint_reservoir", payload.hints && payload.hints.reservoir);
      setText("hint_family", payload.hints && payload.hints.family);
      setText("hint_from_primary", payload.hints && payload.hints.from_primary);
      setText("hint_high_value_renewal", payload.hints && payload.hints.high_value_renewal);
      const table = payload.tables || {{}};
      setText("revenue_telesale_value", table.revenue_telesale);
      setText("revenue_app_value", table.revenue_app);
      setText("last_year_revenue_value", table.last_year_revenue);
      setText("last_year_progress_value", table.last_year_progress);
      setText("deposit_users_value", table.deposit_users);
      setText("deposit_tail_users_value", table.deposit_tail_users);
      setText("deposit_tail_rate_value", table.deposit_tail_rate);
      setText("deposit_tail_aov_value", table.deposit_tail_aov);
      setText("deposit_tail_revenue_value", table.deposit_tail_revenue);
      setText("deposit_tail_revenue_share_value", table.deposit_tail_revenue_share);
      setText("deposit_last_year_tail_revenue_share_value", table.deposit_last_year_tail_revenue_share);
      setText("reservoir_users_value", table.reservoir_users);
      setText("reservoir_total_tail_users_value", table.reservoir_total_tail_users);
      setText("reservoir_total_tail_orders_value", table.reservoir_total_tail_orders);
      setText("reservoir_total_tail_rate_value", table.reservoir_total_tail_rate);
      setText("reservoir_total_revenue_value", table.reservoir_total_revenue);
      setText("reservoir_conversion_users_value", table.reservoir_conversion_users);
      setText("reservoir_conversion_orders_value", table.reservoir_conversion_orders);
      setText("reservoir_conversion_rate_value", table.reservoir_conversion_rate);
      setText("reservoir_conversion_revenue_value", table.reservoir_conversion_revenue);
      setText("reservoir_july_conversion_users_value", table.reservoir_july_conversion_users);
      setText("reservoir_july_conversion_orders_value", table.reservoir_july_conversion_orders);
      setText("reservoir_july_conversion_rate_value", table.reservoir_july_conversion_rate);
      setText("reservoir_july_conversion_revenue_value", table.reservoir_july_conversion_revenue);
      setText("reservoir_tail_users_value", table.reservoir_tail_users);
      setText("reservoir_tail_orders_value", table.reservoir_tail_orders);
      setText("reservoir_tail_rate_value", table.reservoir_tail_rate);
      setText("reservoir_revenue_value", table.reservoir_revenue);
     setText("family_order_share_value", table.family_order_share);
      setText("family_primary_share", table.family_primary_share);
      setText("family_middle_share", table.family_middle_share);
      setText("family_high_share", table.family_high_share);
     setText("family_revenue_value", table.family_revenue);
     setText("from_primary_order_share_value", table.from_primary_order_share);
      setText("from_primary_primary_share", table.from_primary_primary_share);
     setText("from_primary_revenue_value", table.from_primary_revenue);
      setText("high_value_renew_rate_value", table.high_value_renew_rate);
      setText("high_value_renew_aov_value", table.high_value_renew_aov);
      setText("high_value_renew_rate_yoy", table.high_value_renew_rate_yoy);
      setText("high_value_renew_aov_yoy", table.high_value_renew_aov_yoy);
      draw("revenue_amount", latest("revenue_amount_cumulative"), {{target: targets.revenue_amount, color: "#2563eb", label: "累计私域营收", format: "money"}});
      draw("app_new_users", latest("app_new_users_cumulative"), {{target: targets.app_new_users, color: "#16a34a", label: "累计APP新增用户", format: "users"}});
      draw("deposit_tail_rate", latest("deposit_tail_rate_cumulative"), {{color: "#7c3aed", label: "累计定金尾款率", format: "pct"}});
      draw("deposit_tail_revenue_share", latest("deposit_tail_revenue_share_cumulative"), {{target: targets.deposit_tail_revenue_share_last_year, color: "#2563eb", label: "定金尾款占C端营收比例", format: "pct"}});
      draw("reservoir_tail_rate", latest("reservoir_tail_rate_cumulative"), {{color: "#7c3aed", label: "累计转大率", format: "pct"}});
      draw("reservoir_revenue", latest("reservoir_tail_cumulative_revenue"), {{color: "#0891b2", label: "累计转大营收", format: "money"}});
      drawMulti("family_order_share", [
        {{rows: latest("family_order_share_daily"), color: "#7c3aed", label: "总占比"}},
        {{rows: latest("family_primary_share_daily"), color: "#2563eb", label: "小学团占比", dash: "8 6"}},
        {{rows: latest("family_middle_share_daily"), color: "#16a34a", label: "初中团占比", dash: "8 6"}},
        {{rows: latest("family_high_share_daily"), color: "#f97316", label: "高中团占比", dash: "8 6"}}
      ], {{label: "家庭包订单占比趋势", format: "pct"}});
      drawMulti("from_primary_order_share", [
        {{rows: latest("from_primary_order_share_daily"), color: "#f97316", label: "总占比"}},
        {{rows: latest("from_primary_primary_share_daily"), color: "#2563eb", label: "小学团占比", dash: "8 6"}}
      ], {{label: "从小学订单占比趋势", format: "pct"}});
      renderRevenueProgress(payload.revenue_progress || []);
    }}
    async function loadLatestDashboard() {{
      try {{
        const snapshot = await loadSnapshot();
        if (shouldUseUrlPayload(snapshot)) renderDashboard(snapshot);
      }} catch (error) {{
        showSnapshotNotice("快照加载失败，当前展示页面内置数据。");
        console.warn("未能读取独立报表快照，已使用页面内置兜底数据", error);
      }}
      try {{
        const payload = await decodePayloadFromUrl();
        if (shouldUseUrlPayload(payload)) renderDashboard(payload);
      }} catch (error) {{
        console.warn("未能读取链接中的最新数据，已使用当前快照", error);
      }}
    }}
    renderDashboard(fallbackPayload);
    loadLatestDashboard();
  </script>
</body>
</html>"""


def write_html(metrics: Dict[str, Any], output_dir: Path = OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "index.html"
    path.write_text(build_html(metrics), encoding="utf-8")
    return path


def write_static_report(metrics: Dict[str, Any], output_dir: Path) -> Dict[str, Path]:
    public_dir = output_dir / "public"
    data_dir = public_dir / "data"
    sql_dir = output_dir / "sql"
    data_dir.mkdir(parents=True, exist_ok=True)
    sql_dir.mkdir(parents=True, exist_ok=True)

    html_path = public_dir / "index.html"
    snapshot_path = data_dir / "report.json"
    sql_path = sql_dir / "report.sql"
    html_path.write_text(build_html(metrics, snapshot_url="./data/report.json"), encoding="utf-8")
    snapshot_path.write_text(
        json.dumps(dashboard_payload(metrics), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    sql_path.write_text(key_metrics_sql(metrics["report_day"]).strip() + ";\n", encoding="utf-8")
    return {"html": html_path, "snapshot": snapshot_path, "sql": sql_path}


def build_card(metrics: Dict[str, Any], detail_url: str = KEY_METRICS_DETAIL_URL) -> Dict[str, Any]:
    report_day = metrics["report_day"]
    report_start = report_start_for(report_day)
    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    "**📲 私域营收进度**\n"
                    f"累计营收：<font color='blue'>**{format_money_wan(metrics['revenue']['amount'])}**</font>    "
                    f"昨日营收：**{format_money_wan(metrics['revenue']['yesterday_amount'])}**\n"
                    f"{grey(format_money_yoy(metrics['revenue']['amount'], metrics['revenue']['last_year_amount']))}\n"
                    f"目标：**¥ {REVENUE_TARGET_WAN:,}.00万**    "
                    f"进度：**{format_pct(metrics['revenue']['progress'])}**\n"
                    f"<font color='blue'>{progress_bar(metrics['revenue']['progress'])}</font>"
                ),
            },
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    "**🌿 APP新增流量进度**\n"
                    f"累计新增：<font color='green'>**{format_users(metrics['app_flow']['users'])}**</font>    "
                    f"昨日新增：**{format_users(metrics['app_flow']['yesterday_users'])}**\n"
                    f"{grey(format_users_yoy(metrics['app_flow']['users'], metrics['app_flow']['last_year_users']))}\n"
                    f"目标：**{format_users(APP_FLOW_TARGET_USERS)}**    "
                    f"进度：**{format_pct(metrics['app_flow']['progress'])}**\n"
                    f"<font color='green'>{progress_bar(metrics['app_flow']['progress'])}</font>"
                ),
            },
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    "**📘 定金量**\n"
                    f"C端私域定金：<font color='blue'>**{format_users(metrics['deposit']['users'])}**</font>    "
                    f"尾款量：**{format_users(metrics['deposit']['tail_users'])}**    "
                    f"尾款率：**{format_pct(metrics['deposit']['tail_rate'])}**\n"
                    f"尾款客单价：**{format_money_yuan(metrics['deposit']['tail_aov'])}**    "
                    f"尾款营收贡献：**{format_money_wan(metrics['deposit']['tail_revenue'])}**"
                ),
            },
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    "**💧 蓄水量**\n"
                    f"蓄水用户：<font color='green'>**{format_users(metrics['reservoir']['users'])}**</font>\n"
                    f"累计转化：**{format_users(metrics['reservoir']['conversion_users'])}** / "
                    f"{format_pct(metrics['reservoir']['conversion_rate'])} / "
                    f"{format_money_wan(metrics['reservoir']['conversion_revenue'])}\n"
                    f"7月转化：**{format_users(metrics['reservoir']['july_conversion_users'])}** / "
                    f"{format_pct(metrics['reservoir']['july_conversion_rate'])} / "
                    f"{format_money_wan(metrics['reservoir']['july_conversion_revenue'])}\n"
                    f"累计转大：**{format_users(metrics['reservoir']['total_tail_users'])}** / "
                    f"{format_pct(metrics['reservoir']['total_tail_rate'])} / "
                    f"{format_money_wan(metrics['reservoir']['total_tail_revenue'])}\n"
                    f"7月累计转大：**{format_users(metrics['reservoir']['tail_users'])}** / "
                    f"{format_pct(metrics['reservoir']['tail_rate'])} / "
                    f"{format_money_wan(metrics['reservoir']['revenue'])}"
                ),
            },
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    "**👥 家庭包**\n"
                    f"订单占比：<font color='purple'>**{format_pct(metrics['family']['order_share'])}**</font>    "
                    f"营收贡献：**{format_money_wan(metrics['family']['revenue'])}**\n"
                    f"小学团：<font color='blue'>**{format_pct(metrics['family']['primary_share'])}**</font>    "
                    f"初中团：<font color='blue'>**{format_pct(metrics['family']['middle_share'])}**</font>    "
                    f"高中团：<font color='blue'>**{format_pct(metrics['family']['high_share'])}**</font>"
                ),
            },
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    "**🧡 从小学**\n"
                    f"订单占比：<font color='orange'>**{format_pct(metrics['from_primary']['order_share'])}**</font>    "
                    f"营收贡献：**{format_money_wan(metrics['from_primary']['revenue'])}**\n"
                    f"小学团：<font color='orange'>**{format_pct(metrics['from_primary']['primary_share'])}**</font>"
                ),
            },
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    "**💎 高净值续费**\n"
                    f"续费率：<font color='blue'>**{format_pct(metrics['high_value_renewal']['renew_rate'])}**</font>    "
                    f"续费率同比：{grey(format_rate_yoy(metrics['high_value_renewal']['renew_rate'], metrics['high_value_renewal']['last_year_renew_rate']))}\n"
                    f"续费客单价：**{format_money_yuan(metrics['high_value_renewal']['renew_aov'])}**    "
                    f"客单价同比：{grey(format_yuan_yoy(metrics['high_value_renewal']['renew_aov'], metrics['high_value_renewal']['last_year_renew_aov']))}"
                ),
            },
        },
        {
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": f"趋势图从{ymd(report_start)}开始，没数据日期展示0；点击按钮查看完整 HTML 趋势看板。",
                }
            ],
        },
        {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看完整趋势看板"},
                    "type": "primary",
                    "url": detail_url,
                }
            ],
        },
    ]
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "turquoise",
            "title": {"tag": "plain_text", "content": "问鼎·C端私域数据"},
            "subtitle": {"tag": "plain_text", "content": f"数据截止 {ymd(report_day)}"},
        },
        "elements": elements,
    }


def send_card(card: Dict[str, Any], webhook_url: str = WEBHOOK_URL, dry_run: bool = False) -> None:
    payload = {"msg_type": "interactive", "card": card}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if dry_run:
        print("POST " + webhook_url)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    print("飞书 webhook 返回：" + body)
    try:
        response = json.loads(body)
    except json.JSONDecodeError:
        return
    if response.get("code") not in (None, 0) or response.get("StatusCode") not in (None, 0):
        raise RuntimeError(f"飞书推送失败：{body}")


def _relative_to_project(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


def _publish_cwd_and_path(path: Path) -> tuple:
    resolved = path.resolve()
    try:
        return str(PROJECT_ROOT), str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved.parent), resolved.name


def publish_html(output_dir: Path = OUTPUT_DIR, dry_run: bool = False) -> str:
    output_path = output_dir if output_dir.suffix == ".html" else output_dir / "index.html"
    publish_cwd, publish_path = _publish_cwd_and_path(output_path)
    scope_cmd = ["lark-cli", "apps", "+access-scope-set", "--app-id", MIAODA_APP_ID, "--scope", "tenant", "--json"]
    publish_cmd = ["lark-cli", "apps", "+html-publish", "--app-id", MIAODA_APP_ID, "--path", publish_path, "--json"]
    if not shutil.which("lark-cli"):
        raise RuntimeError("未找到 lark-cli，无法发布最新 HTML，看板链接会停留在旧版本。请先在调度机安装并配置 lark-cli，或使用 --skip-publish 明确跳过发布。")
    if dry_run:
        print(" ".join(publish_cmd))
        print(" ".join(scope_cmd))
        return KEY_METRICS_DETAIL_URL
    publish_result = subprocess.run(
        publish_cmd,
        cwd=publish_cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    payload = json.loads(publish_result.stdout)
    url = payload.get("data", {}).get("url") or KEY_METRICS_DETAIL_URL
    subprocess.run(
        scope_cmd,
        cwd=str(PROJECT_ROOT),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    print("妙搭 HTML 已发布：" + url)
    return url


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 C端私域关键指标 HTML 看板，并推送飞书卡片")
    parser.add_argument("--date", help="数据截止日期 YYYY-MM-DD；默认昨天")
    parser.add_argument("--sample", action="store_true", help="使用样例数据，不连接数仓")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不发送飞书，不发布妙搭")
    parser.add_argument("--publish", action="store_true", help="发布/更新妙搭 HTML 外壳；调度机无 lark-cli 时不要使用")
    parser.add_argument("--skip-publish", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--skip-card", action="store_true", help="只生成/发布 HTML，不推送飞书卡片")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report_day = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else default_report_day()
    metrics = sample_metrics(report_day) if args.sample else fetch_metrics(report_day)
    write_html(metrics)
    if args.publish and not args.skip_publish:
        published_url = publish_html(OUTPUT_DIR, dry_run=args.dry_run)
        detail_url = build_detail_url(metrics, published_url)
    else:
        detail_url = build_detail_url(metrics)
    if not args.skip_card:
        send_card(build_card(metrics, detail_url), dry_run=args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"执行失败：{exc}", file=sys.stderr)
        sys.exit(1)
