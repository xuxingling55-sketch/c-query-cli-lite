from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import key_metrics_dashboard_push as push  # noqa: E402


class KeyMetricsDashboardPushTest(unittest.TestCase):
    def test_load_db_config_reads_local_config_without_embedded_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "starrocks": {
                            "host": "db.local",
                            "port": 9030,
                            "user": "reader",
                            "password": "secret",
                            "database": "analytics",
                        },
                        "sparksql": {
                            "host": "spark.local",
                            "port": 10010,
                            "user": "reader",
                            "password": "secret",
                            "database": "default",
                        },
                    }
                ),
                encoding="utf-8",
            )
            config = push.load_db_config(path)

        self.assertEqual(config["starrocks"]["host"], "db.local")
        self.assertNotIn("EMBEDDED_DB_CONFIG", Path(push.__file__).read_text(encoding="utf-8"))

    def test_load_db_config_rejects_missing_values(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "缺少 StarRocks"):
                push.load_db_config(Path("/path/that/does/not/exist"))

    def test_revenue_sql_uses_confirmed_c_end_amount_scope(self) -> None:
        sql = push.key_metrics_sql(date(2026, 7, 3))

        self.assertIn("crm_tele_daily AS", sql)
        self.assertIn("aws.crm_order_info a", sql)
        self.assertIn("SUBSTR(a.pay_time, 1, 10) BETWEEN '2026-07-01' AND '2026-07-03'", sql)
        self.assertIn("a.workplace_id IN (4, 400, 702)", sql)
        self.assertIn("a.regiment_id NOT IN (303, 0, 546)", sql)
        self.assertIn("a.worker_id <> 0", sql)
        self.assertIn("a.is_test = false", sql)
        self.assertIn("SUM(CASE WHEN business_gmv_attribution = '商业化' THEN o.sub_amount ELSE 0 END) + MAX(COALESCE(ctd.crm_tele_revenue, 0)) AS revenue_amount", sql)
        self.assertIn("MAX(COALESCE(ctd.crm_tele_revenue, 0)) AS revenue_telesale_amount", sql)
        self.assertIn("SUM(CASE WHEN business_gmv_attribution = '商业化' THEN sub_amount ELSE 0 END) AS revenue_app_amount", sql)
        self.assertIn("business_gmv_attribution = '商业化'", sql)
        orders_window_sql = sql.split("orders_window AS (", 1)[1].split("),\nbig_order AS", 1)[0]
        self.assertNotIn("u_user IS NOT NULL", orders_window_sql)
        self.assertIn("paid_time_sk BETWEEN 20260624 AND 20260630", sql)
        self.assertIn("paid_time_sk BETWEEN 20260522 AND 20260630", sql)
        self.assertIn("deposit_source AS", sql)
        self.assertIn("reservoir_source AS", sql)
        self.assertIn("big_order AS", sql)
        self.assertIn("is_normal_price = 1", sql)
        self.assertIn("original_amount >= 39", sql)
        self.assertIn("business_good_kind_name_level_1 = '组合品'", sql)
        self.assertIn("b.first_big_paid_time >= d.source_paid_time", sql)
        self.assertIn("b.paid_time >= r.first_source_paid_time", sql)
        self.assertNotIn("o.sub_amount > 500", sql)
        self.assertNotIn("o.order_amount >= 500", sql)
        self.assertNotIn("sku_group_good_id <> '74ec057c-4a49-45aa-a0ee-0fd2a410989a'", sql)
        self.assertIn("sku_group_good_id = '74ec057c-4a49-45aa-a0ee-0fd2a410989a'", sql)
        self.assertIn("tele_zhike_double_users AS", sql)
        self.assertIn("array_contains(b.team_names, '入校')", sql)
        self.assertIn("array_contains(b.team_names, '电销/网销')", sql)
        self.assertIn("dct.app_deposit_users + dct.tele_deposit_users + ddt.double_deposit_users AS total_deposit_users", sql)
        self.assertIn("dct.tele_deposit_users + ddt.double_deposit_users AS tele_deposit_users", sql)
        self.assertIn("good_kind_name_level_2 = '同步课加培优课'", sql)
        self.assertIn("good_kind_name_level_3 = '同步课加培优课流量品'", sql)
        self.assertIn("business_good_kind_name_level_3 = '小初高品'", sql)
        self.assertIn("business_good_kind_name_level_1 = '组合品'", sql)
        self.assertIn("o.u_user IS NOT NULL", sql)
        self.assertIn("o.is_test_user = 0", sql)
        self.assertIn("o.original_amount >= 39", sql)
        self.assertIn("o.business_good_kind_name_level_1 = '组合品' AND org.department_name LIKE '%小学%'", sql)
        self.assertIn("o.business_good_kind_name_level_1 = '组合品' AND org.department_name LIKE '%初中%'", sql)
        self.assertIn("o.business_good_kind_name_level_1 = '组合品' AND org.department_name LIKE '%高中%'", sql)
        self.assertIn("business_good_kind_name_level_3 = '小学品加拓展'", sql)
        self.assertIn("o.good_kind_name_level_3 = '拓展课'", sql)
        self.assertIn("o.good_stage_subject REGEXP '1-2-specialCourse'", sql)
        self.assertIn("o.good_stage_subject REGEXP '1-6-specialCourse'", sql)
        self.assertIn("o.good_stage_subject REGEXP '1-7-specialCourse'", sql)
        self.assertIn("o.good_stage_subject_cnt = 3", sql)
        self.assertIn("business_good_kind_name_level_3 IN ('小学品', '小学品加拓展')", sql)
        self.assertIn("COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_3 = '小学品加拓展' THEN o.order_id END) AS from_primary_orders", sql)
        self.assertIn("COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_3 IN ('小学品', '小学品加拓展') THEN o.order_id END) AS from_primary_base_orders", sql)
        self.assertIn("COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_3 = '小学品加拓展' AND org.department_name LIKE '%小学%' THEN o.order_id END) AS from_primary_primary_orders", sql)
        self.assertIn("COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_3 IN ('小学品', '小学品加拓展') AND org.department_name LIKE '%小学%' THEN o.order_id END) AS from_primary_primary_base_orders", sql)
        self.assertIn("SUM(CASE WHEN o.business_good_kind_name_level_3 = '小初高品' AND o.u_user IS NOT NULL AND o.is_test_user = 0 AND o.original_amount >= 39 THEN o.sub_amount ELSE 0 END) AS family_revenue", sql)
        self.assertIn("SUM(CASE WHEN o.u_user IS NOT NULL AND o.is_test_user = 0 AND o.original_amount >= 39 AND (", sql)
        self.assertIn("OR o.business_good_kind_name_level_3 IN ('小学品加拓展')", sql)
        self.assertIn("THEN o.sub_amount ELSE 0 END) AS from_primary_revenue", sql)
        self.assertIn("high_value_active_users AS", sql)
        self.assertIn("FROM aws.business_active_user_last_14_day", sql)
        self.assertIn("day BETWEEN 20260701 AND 20260703", sql)
        self.assertIn("business_user_pay_status_business_day = '高净值用户'", sql)
        self.assertIn("hv.day = o.paid_time_sk", sql)
        self.assertIn("o.business_good_kind_name_level_1 = '组合品'", sql)
        self.assertIn("high_value_renew_total AS", sql)
        self.assertIn("total_high_value_renew_users", sql)
        self.assertIn("MAX(hvrt.total_high_value_renew_users) AS high_value_renew_users", sql)
        self.assertIn("MAX(hvrt.total_high_value_renew_revenue) AS high_value_renew_revenue", sql)
        self.assertIn("high_value_renew_users", sql)
        self.assertNotIn("paid_time_sk < 20260701", sql)
        self.assertNotIn("business_user_pay_status_business = '高净值用户' AND o.sub_amount > 500", sql)
        self.assertIn("MAX(dut.total_deposit_users) AS deposit_users", sql)
        self.assertIn("deposit_tail_total AS", sql)
        self.assertIn("deposit_tail_cumulative_by_day AS", sql)
        self.assertIn("COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN d.u_user END) AS total_deposit_tail_users", sql)
        self.assertIn("SUM(CASE WHEN b.u_user IS NOT NULL THEN b.big_amount ELSE 0 END) AS total_deposit_tail_revenue", sql)
        self.assertIn("MAX(dtc.cumulative_deposit_tail_users) AS deposit_tail_cumulative_users", sql)
        self.assertIn("MAX(dtc.cumulative_deposit_tail_revenue) AS deposit_tail_cumulative_revenue", sql)
        self.assertIn("MAX(dtt.total_deposit_tail_users) AS deposit_tail_total_users", sql)
        self.assertIn("MAX(dtt.total_deposit_tail_revenue) AS deposit_tail_total_revenue", sql)
        self.assertIn("MAX(rut.total_reservoir_users) AS reservoir_users", sql)
        self.assertIn("reservoir_tail_total AS", sql)
        self.assertIn("reservoir_conversion_order AS", sql)
        self.assertIn("reservoir_conversion_total AS", sql)
        self.assertIn("reservoir_july_conversion_total AS", sql)
        self.assertIn("reservoir_conversion_cumulative_by_day AS", sql)
        self.assertIn("SUM(o.sub_amount) AS conversion_amount", sql)
        self.assertIn("AND rs.order_id IS NULL", sql)
        self.assertIn("reservoir_tail_cumulative_by_day AS", sql)
        self.assertIn("COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN r.u_user END) AS total_reservoir_tail_users", sql)
        self.assertIn("SUM(CASE WHEN b.u_user IS NOT NULL THEN b.big_amount ELSE 0 END) AS total_reservoir_tail_revenue", sql)
        self.assertIn("MAX(rtc.cumulative_reservoir_tail_users) AS reservoir_tail_cumulative_users", sql)
        self.assertIn("MAX(rtc.cumulative_reservoir_tail_revenue) AS reservoir_tail_cumulative_revenue", sql)
        self.assertIn("MAX(rtt.total_reservoir_tail_users) AS reservoir_tail_total_users", sql)
        self.assertIn("MAX(rtt.total_reservoir_tail_revenue) AS reservoir_tail_total_revenue", sql)
        self.assertIn("MAX(rct.total_reservoir_conversion_users) AS reservoir_conversion_users", sql)
        self.assertIn("MAX(rjct.total_reservoir_july_conversion_users) AS reservoir_july_conversion_users", sql)
        self.assertIn("MAX(rcc.cumulative_reservoir_conversion_users) AS reservoir_conversion_cumulative_users", sql)

    def test_last_year_revenue_sql_uses_same_period(self) -> None:
        sql = push.last_year_revenue_sql(date(2026, 7, 3))

        self.assertIn("paid_time_sk BETWEEN 20250701 AND 20250703", sql)
        self.assertIn("business_gmv_attribution = '商业化'", sql)
        self.assertIn("aws.crm_order_info a", sql)
        self.assertIn("SUBSTR(a.pay_time, 1, 10) BETWEEN '2025-07-01' AND '2025-07-03'", sql)
        self.assertIn("COALESCE(dws.app_revenue, 0) + COALESCE(crm.tele_revenue, 0) AS last_year_revenue_amount", sql)

    def test_last_year_deposit_tail_share_sql_uses_same_period(self) -> None:
        sql = push.last_year_deposit_tail_share_sql(date(2026, 7, 3))

        self.assertIn("paid_time_sk BETWEEN 20250625 AND 20250630", sql)
        self.assertIn("good_kind_id_level_2 = 'ee74d649-8e32-452a-a461-65de25560440'", sql)
        self.assertIn("paid_time_sk BETWEEN 20250701 AND 20250703", sql)
        self.assertIn("sub_amount > 500", sql)
        self.assertIn("last_year_deposit_tail_revenue", sql)
        self.assertIn("last_year_deposit_tail_revenue_share", sql)

    def test_last_year_high_value_sql_uses_same_period(self) -> None:
        sql = push.last_year_high_value_sql(date(2026, 7, 3))

        self.assertIn("paid_time_sk BETWEEN 20250701 AND 20250703", sql)
        self.assertIn("high_value_active_users AS", sql)
        self.assertIn("FROM aws.business_active_user_last_14_day", sql)
        self.assertIn("day BETWEEN 20250701 AND 20250703", sql)
        self.assertIn("business_user_pay_status_business_day = '高净值用户'", sql)
        self.assertIn("business_good_kind_name_level_1 IN ('组合品', '续购')", sql)
        self.assertNotIn("sub_amount > 500", sql)
        self.assertIn("LEFT JOIN period_orders po", sql)
        self.assertIn("hv.day = po.paid_time_sk", sql)
        self.assertIn("last_year_high_value_users", sql)
        self.assertIn("last_year_high_value_renew_users", sql)
        self.assertIn("last_year_high_value_renew_revenue", sql)

    def test_app_flow_sql_uses_report_window_and_mobile_os(self) -> None:
        sql = push.app_flow_sql(date(2026, 7, 3))

        self.assertIn("a.day BETWEEN 20260701 AND 20260703", sql)
        self.assertIn("a.u_from IN ('android', 'ios', 'harmony')", sql)
        self.assertIn("a.day = c.day", sql)
        self.assertIn("COUNT(u_user) AS install_users", sql)

    def test_date_series_keeps_missing_days_as_zero(self) -> None:
        rows = [{"day": 20260620, "revenue_amount": 10000}, {"day": 20260622, "revenue_amount": 30000}]

        series = push.complete_daily_series(rows, date(2026, 6, 20), date(2026, 6, 22), ["revenue_amount"])

        self.assertEqual([r["day"] for r in series], ["2026-06-20", "2026-06-21", "2026-06-22"])
        self.assertEqual([r["revenue_amount"] for r in series], [10000, 0, 30000])

    def test_fetch_metrics_calculates_confirmed_rates(self) -> None:
        def fake_runner(sql, _db_config):
            if "regist_channel_label1" in sql:
                return [
                    {"day": 20260701, "app_new_users": 100},
                    {"day": 20260702, "app_new_users": 200},
                ]
            if "last_year_deposit_tail_revenue_share" in sql:
                return [
                    {
                        "last_year_deposit_tail_revenue": 30000,
                        "last_year_deposit_tail_revenue_share": 0.2,
                    }
                ]
            if "last_year_revenue_amount" in sql:
                return [{"last_year_revenue_amount": 150000}]
            if "last_year_high_value_users" in sql:
                return [
                    {
                        "last_year_high_value_users": 20,
                        "last_year_high_value_renew_users": 4,
                        "last_year_high_value_renew_revenue": 12000,
                    }
                ]
            return [
                {
                    "day": 20260701,
                    "revenue_amount": 100000,
                    "revenue_telesale_amount": 70000,
                    "revenue_app_amount": 30000,
                    "total_orders": 100,
                    "total_revenue_amount": 100000,
                    "deposit_users": 10,
                    "deposit_tail_users": 4,
                    "deposit_tail_revenue": 40000,
                    "deposit_tail_total_users": 8,
                    "deposit_tail_total_revenue": 120000,
                    "reservoir_users": 50,
                    "reservoir_tail_users": 10,
                    "reservoir_tail_orders": 20,
                    "reservoir_tail_revenue": 20000,
                    "reservoir_tail_total_users": 22,
                    "reservoir_tail_total_revenue": 66000,
                    "reservoir_conversion_users": 25,
                    "reservoir_conversion_orders": 35,
                    "reservoir_conversion_revenue": 80000,
                    "reservoir_july_conversion_users": 12,
                    "reservoir_july_conversion_orders": 18,
                    "reservoir_july_conversion_revenue": 30000,
                    "family_orders": 10,
                    "family_base_orders": 50,
                    "family_revenue": 30000,
                    "from_primary_orders": 8,
                    "from_primary_base_orders": 16,
                    "from_primary_revenue": 12000,
                    "high_value_users": 20,
                    "high_value_renew_users": 5,
                    "high_value_renew_revenue": 15000,
                },
                {
                    "day": 20260702,
                    "revenue_amount": 200000,
                    "revenue_telesale_amount": 110000,
                    "revenue_app_amount": 90000,
                    "total_orders": 200,
                    "total_revenue_amount": 200000,
                    "deposit_users": 10,
                    "deposit_tail_users": 6,
                    "deposit_tail_revenue": 90000,
                    "deposit_tail_total_users": 8,
                    "deposit_tail_total_revenue": 120000,
                    "reservoir_users": 50,
                    "reservoir_tail_users": 15,
                    "reservoir_tail_orders": 50,
                    "reservoir_tail_revenue": 50000,
                    "reservoir_tail_total_users": 22,
                    "reservoir_tail_total_revenue": 66000,
                    "reservoir_conversion_users": 25,
                    "reservoir_conversion_orders": 35,
                    "reservoir_conversion_revenue": 80000,
                    "reservoir_july_conversion_users": 12,
                    "reservoir_july_conversion_orders": 18,
                    "reservoir_july_conversion_revenue": 30000,
                    "family_orders": 30,
                    "family_base_orders": 100,
                    "family_revenue": 70000,
                    "from_primary_orders": 10,
                    "from_primary_base_orders": 20,
                    "from_primary_revenue": 18000,
                    "high_value_users": 25,
                    "high_value_renew_users": 10,
                    "high_value_renew_revenue": 40000,
                },
            ]

        metrics = push.fetch_metrics(date(2026, 7, 2), query_runner=fake_runner)

        self.assertEqual(metrics["report_day"], date(2026, 7, 2))
        self.assertEqual(metrics["revenue"]["amount"], 300000)
        self.assertEqual(metrics["revenue"]["yesterday_amount"], 200000)
        self.assertEqual(metrics["revenue"]["telesale_amount"], 180000)
        self.assertEqual(metrics["revenue"]["app_amount"], 120000)
        self.assertEqual(metrics["revenue"]["last_year_amount"], 150000)
        self.assertAlmostEqual(metrics["revenue"]["last_year_progress"], 150000 / (push.REVENUE_TARGET_WAN * 10000))
        self.assertEqual(metrics["app_flow"]["users"], 300)
        self.assertEqual(metrics["app_flow"]["yesterday_users"], 200)
        self.assertEqual(metrics["deposit"]["users"], 10)
        self.assertAlmostEqual(metrics["deposit"]["tail_rate"], 0.8)
        self.assertEqual(metrics["deposit"]["tail_revenue"], 120000)
        self.assertAlmostEqual(metrics["deposit"]["tail_revenue_share"], 120000 / 300000)
        self.assertEqual(metrics["deposit"]["last_year_tail_revenue"], 30000)
        self.assertAlmostEqual(metrics["deposit"]["last_year_tail_revenue_share"], 0.2)
        self.assertEqual(metrics["deposit"]["tail_users"], 8)
        self.assertEqual(metrics["deposit"]["tail_aov"], 15000)
        self.assertEqual(metrics["reservoir"]["tail_users"], 22)
        self.assertEqual(metrics["reservoir"]["revenue"], 66000)
        self.assertAlmostEqual(metrics["reservoir"]["tail_rate"], 22 / 50)
        self.assertEqual(metrics["reservoir"]["conversion_users"], 25)
        self.assertAlmostEqual(metrics["reservoir"]["conversion_rate"], 25 / 50)
        self.assertEqual(metrics["reservoir"]["july_conversion_users"], 12)
        self.assertAlmostEqual(metrics["reservoir"]["july_conversion_rate"], 12 / 50)
        self.assertAlmostEqual(metrics["family"]["order_share"], 30 / 100)
        self.assertEqual(metrics["family"]["revenue"], 100000)
        self.assertAlmostEqual(metrics["from_primary"]["order_share"], 10 / 20)
        self.assertEqual(metrics["from_primary"]["revenue"], 30000)
        self.assertAlmostEqual(metrics["high_value_renewal"]["renew_rate"], 10 / 25)
        self.assertEqual(metrics["high_value_renewal"]["renew_aov"], 4000)
        self.assertAlmostEqual(metrics["high_value_renewal"]["last_year_renew_rate"], 4 / 20)
        self.assertEqual(metrics["high_value_renewal"]["last_year_renew_aov"], 3000)
        self.assertEqual(len(metrics["daily"]), 2)

    def test_run_query_uses_sparksql_when_configured(self) -> None:
        with (
            patch.object(push, "run_sparksql_query", return_value=[{"ok": 1}]) as spark_query,
            patch.object(push, "run_starrocks_query") as starrocks_query,
        ):
            rows = push.run_query("SELECT 1", {"sparksql": {"host": "spark.local"}})

        self.assertEqual(rows, [{"ok": 1}])
        spark_query.assert_called_once()
        starrocks_query.assert_not_called()

    def test_html_contains_charts_summary_and_zero_days(self) -> None:
        metrics = push.sample_metrics(date(2026, 7, 2))

        html = push.build_html(metrics)

        self.assertIn("问鼎·C端私域数据趋势看板", html)
        self.assertIn("数据截止 2026-07-02", html)
        self.assertIn("私域营收进度", html)
        self.assertIn("电销营收", html)
        self.assertIn("APP营收", html)
        self.assertIn("去年同期完成率", html)
        self.assertIn("APP新增流量进度", html)
        self.assertIn("定金量与尾款表现", html)
        self.assertIn("蓄水量", html)
        self.assertIn("家庭包", html)
        self.assertIn("从小学", html)
        self.assertIn("function cumulativeAgainstLatest", html)
        self.assertIn('draw("revenue_amount", latest("revenue_amount_cumulative")', html)
        self.assertIn('draw("app_new_users", latest("app_new_users_cumulative")', html)
        self.assertIn('draw("deposit_tail_rate", latest("deposit_tail_rate_cumulative")', html)
        self.assertIn('draw("deposit_tail_revenue_share", latest("deposit_tail_revenue_share_cumulative")', html)
        self.assertIn("去年同期尾款占比", html)
        self.assertNotIn('draw("deposit_tail_revenue", cumul("deposit_tail_revenue")', html)
        self.assertIn("function formatChartValue", html)
        self.assertIn("class=\"value-label\"", html)
        self.assertNotIn("function drawDualAxis", html)
        self.assertNotIn('drawDualAxis("reservoir_combo"', html)
        self.assertNotIn("左轴：累计转大率", html)
        self.assertNotIn("右轴：累计转大营收", html)
        self.assertIn('draw("reservoir_tail_rate", latest("reservoir_tail_rate_cumulative"), {color: "#7c3aed", label: "累计转大率", format: "pct"})', html)
        self.assertIn('draw("reservoir_revenue", latest("reservoir_tail_cumulative_revenue"), {color: "#0891b2", label: "累计转大营收", format: "money"})', html)
        self.assertIn("累计转大率", html)
        self.assertIn("累计转大营收", html)
        self.assertIn("累计转化", html)
        self.assertIn("7月转化", html)
        self.assertIn("function drawMulti", html)
        self.assertIn("function shouldUseUrlPayload", html)
        self.assertIn("payload.version < fallbackPayload.version", html)
        self.assertNotIn("payload.report_day !== fallbackPayload.report_day", html)
        self.assertIn('id="family_order_share"', html)
        self.assertIn('id="from_primary_order_share"', html)
        self.assertIn('label: "总占比"', html)
        self.assertIn('label: "小学团占比"', html)
        self.assertIn('label: "初中团占比"', html)
        self.assertIn('label: "高中团占比"', html)
        self.assertIn('stroke-dasharray="${item.dash || ""}"', html)
        self.assertIn('label: "总占比"}', html)
        self.assertIn('label: "小学团占比", dash: "8 6"}', html)
        self.assertIn('label: "初中团占比", dash: "8 6"}', html)
        self.assertIn('label: "高中团占比", dash: "8 6"}', html)
        self.assertIn('drawMulti("family_order_share"', html)
        self.assertIn('drawMulti("from_primary_order_share"', html)
        self.assertIn("汇总订单占比", html)
        self.assertNotIn("function renderShareTable", html)
        self.assertNotIn("targets.family_order_share", html)
        self.assertNotIn("targets.from_primary_order_share", html)
        payload = push.dashboard_payload(metrics)
        self.assertNotIn("family_order_share", payload["targets"])
        self.assertNotIn("from_primary_order_share", payload["targets"])
        self.assertIn("高净值续费", html)
        self.assertIn("续费率同比", html)
        self.assertIn("客单价同比", html)
        self.assertIn('"revenue_amount": 0', html)

    def test_html_contains_revenue_progress_section(self) -> None:
        metrics = push.sample_metrics(date(2026, 6, 22))

        html = push.build_html(metrics)

        self.assertIn("冲顶营收进度", html)
        self.assertIn("revenue-visual", html)
        self.assertIn("revenue-dial", html)
        self.assertIn("thermo", html)
        self.assertIn("mix-bar", html)
        self.assertIn("时间进度", html)
        self.assertIn("目标进度", html)
        self.assertIn("实际完成", html)
        self.assertIn("APP营收目标", html)
        self.assertIn("电销营收目标", html)
        self.assertIn("APP预测目标进度", html)
        self.assertIn("电销预测目标进度", html)
        self.assertIn("营收目标来自 revenue_target_GMV", html)
        self.assertNotIn("预计月底完成", html)
        self.assertNotIn("冲顶帆软底表字段说明", html)
        self.assertLess(html.index("冲顶营收进度"), html.index("<h1>问鼎·C端私域数据趋势看板</h1>"))

    def test_write_static_report_creates_page_snapshot_and_sql(self) -> None:
        metrics = push.sample_metrics(date(2026, 7, 26))

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = push.write_static_report(metrics, Path(temp_dir))
            html_text = paths["html"].read_text(encoding="utf-8")
            payload = json.loads(paths["snapshot"].read_text(encoding="utf-8"))
            sql_text = paths["sql"].read_text(encoding="utf-8")

        self.assertIn('fetch("./data/report.json"', html_text)
        self.assertEqual(payload["report_day"], "2026-07-26")
        self.assertTrue(sql_text.lstrip().startswith("WITH"))

    def test_fetch_metrics_loads_fine_revenue_progress_when_available(self) -> None:
        def fake_runner(sql, _db_config):
            if "xuxingling_202607_chongding_fine_summary" in sql:
                return [
                    {
                        "channel": "整体",
                        "date_sk": 20260703,
                        "target_revenue": 1000,
                        "real_revenue": 900,
                        "month_total_target": 31000,
                        "cumulative_target_revenue": 3000,
                        "cumulative_real_revenue": 2700,
                        "time_progress": 3 / 31,
                        "predicted_target_progress": 3000 / 31000,
                        "actual_completion_progress": 2700 / 31000,
                        "forecast_completion_progress": 27900 / 31000,
                        "actual_vs_cumulative_target_progress": 0.9,
                    }
                ]
            if "regist_channel_label1" in sql:
                return [{"day": 20260703, "app_new_users": 100}]
            if "last_year_revenue_amount" in sql:
                return [{"last_year_revenue_amount": 800}]
            return [
                {
                    "day": 20260703,
                    "revenue_amount": 2700,
                    "revenue_telesale_amount": 1700,
                    "revenue_app_amount": 1000,
                    "total_orders": 10,
                    "total_revenue_amount": 2700,
                    "deposit_users": 1,
                    "deposit_tail_users": 1,
                    "deposit_tail_revenue": 100,
                    "reservoir_users": 2,
                    "reservoir_tail_users": 1,
                    "reservoir_tail_orders": 1,
                    "reservoir_tail_revenue": 100,
                    "family_orders": 1,
                    "family_base_orders": 2,
                    "family_revenue": 100,
                    "from_primary_orders": 1,
                    "from_primary_base_orders": 2,
                    "from_primary_revenue": 100,
                    "high_value_users": 3,
                    "high_value_renew_users": 1,
                    "high_value_renew_revenue": 1200,
                }
            ]

        metrics = push.fetch_metrics(date(2026, 7, 3), query_runner=fake_runner)
        payload = push.dashboard_payload(metrics)

        self.assertEqual(metrics["revenue_progress"][0]["channel"], "整体")
        self.assertEqual(payload["revenue_progress"][0]["channel"], "整体")
        self.assertIn("month_target_short", payload["revenue_progress"][0])
        self.assertNotIn("forecast_progress", payload["revenue_progress"][0])
        self.assertNotIn("forecast_progress_value", payload["revenue_progress"][0])

    def test_revenue_progress_uses_metric_actual_when_fine_row_is_zero(self) -> None:
        metrics = push.sample_metrics(date(2026, 7, 2))
        metrics["revenue_progress"] = [
            {
                "channel": "整体",
                "month_total_target": push.REVENUE_TARGET_WAN * 10000,
                "cumulative_real_revenue": 0,
                "actual_completion_progress": 0,
                "time_progress": 2 / 31,
                "predicted_target_progress": 2 / 31,
            },
            {
                "channel": "APP",
                "month_total_target": 30000000,
                "cumulative_real_revenue": 0,
                "actual_completion_progress": 0,
            },
            {
                "channel": "电销",
                "month_total_target": 90000000,
                "cumulative_real_revenue": 0,
                "actual_completion_progress": 0,
            },
        ]

        payload_rows = push.revenue_progress_payload_rows(metrics)
        overall = payload_rows[0]

        self.assertEqual(overall["channel"], "整体")
        self.assertEqual(overall["cumulative_actual"], push.format_optional_money_wan(metrics["revenue"]["amount"]))
        self.assertGreater(overall["actual_progress_value"], 0)

    def test_card_contains_six_modules_and_detail_link(self) -> None:
        card = push.build_card(push.sample_metrics(date(2026, 6, 22)))
        dumped = json.dumps(card, ensure_ascii=False)

        self.assertEqual(card["header"]["title"]["content"], "问鼎·C端私域数据")
        self.assertIn("数据截止 2026-06-22", dumped)
        self.assertIn("私域营收进度", dumped)
        self.assertIn("昨日营收", dumped)
        self.assertIn("较去年同比", dumped)
        self.assertIn("昨日新增", dumped)
        self.assertIn("目标", dumped)
        self.assertIn("进度", dumped)
        self.assertIn("APP新增流量进度", dumped)
        self.assertIn("定金量", dumped)
        self.assertIn("蓄水量", dumped)
        self.assertIn("累计转化", dumped)
        self.assertIn("7月转化", dumped)
        self.assertNotIn("购买金额>500的其他商品", dumped)
        self.assertIn("家庭包", dumped)
        self.assertIn("从小学", dumped)
        self.assertNotIn("目标：**20.00%**", dumped)
        self.assertNotIn("目标：**50.00%**", dumped)
        self.assertIn("高净值续费", dumped)
        self.assertIn("续费率同比", dumped)
        self.assertIn("客单价同比", dumped)
        self.assertIn("<font color='grey'>较去年同比", dumped)
        self.assertIn("查看完整趋势看板", dumped)
        self.assertIn(push.KEY_METRICS_DETAIL_URL, dumped)

    def test_detail_url_carries_more_dashboard_data(self) -> None:
        metrics = push.sample_metrics(date(2026, 6, 22))

        detail_url = push.build_detail_url(metrics)

        self.assertTrue(detail_url.startswith(push.KEY_METRICS_DETAIL_URL + "?v=20260622_"))
        self.assertIn("#payload=", detail_url)
        self.assertLess(len(detail_url), 12000)
        payload = push.dashboard_payload(metrics)
        self.assertIn("daily", payload)
        self.assertIn("tables", payload)
        self.assertIn("revenue_progress", payload)
        self.assertGreater(len(payload["daily"]), 0)
        self.assertIn("deposit_tail_revenue_share", payload["tables"])
        self.assertIn("deposit_last_year_tail_revenue_share", payload["tables"])
        self.assertIn("deposit_tail_revenue_share_last_year", payload["targets"])
        self.assertIn("last_year_revenue", payload["tables"])
        self.assertIn("last_year_progress", payload["tables"])
        self.assertIn("revenue_telesale", payload["tables"])
        self.assertIn("revenue_app", payload["tables"])
        self.assertIn("reservoir_conversion_users", payload["tables"])
        self.assertIn("reservoir_july_conversion_users", payload["tables"])

    def test_dashboard_daily_trends_match_card_metrics(self) -> None:
        metrics = push.sample_metrics(date(2026, 7, 2))

        payload = push.dashboard_payload(metrics)
        latest = payload["daily"][-1]

        self.assertEqual(latest["revenue_amount_cumulative"], metrics["revenue"]["amount"])
        self.assertEqual(latest["app_new_users_cumulative"], metrics["app_flow"]["users"])
        self.assertEqual(latest["deposit_tail_cumulative_users"], metrics["deposit"]["tail_users"])
        self.assertEqual(latest["deposit_tail_cumulative_revenue"], metrics["deposit"]["tail_revenue"])
        self.assertAlmostEqual(latest["deposit_tail_revenue_share_cumulative"], metrics["deposit"]["tail_revenue_share"])
        self.assertEqual(latest["reservoir_tail_cumulative_users"], metrics["reservoir"]["tail_users"])
        self.assertEqual(latest["reservoir_tail_cumulative_revenue"], metrics["reservoir"]["revenue"])
        self.assertAlmostEqual(latest["reservoir_tail_rate_cumulative"], metrics["reservoir"]["tail_rate"])
        self.assertEqual(latest["reservoir_conversion_cumulative_users"], metrics["reservoir"]["conversion_users"])
        self.assertAlmostEqual(latest["reservoir_conversion_rate_cumulative"], metrics["reservoir"]["conversion_rate"])
        self.assertEqual(latest["reservoir_july_conversion_cumulative_users"], metrics["reservoir"]["july_conversion_users"])
        self.assertAlmostEqual(latest["reservoir_july_conversion_rate_cumulative"], metrics["reservoir"]["july_conversion_rate"])

    def test_publish_sets_tenant_access_scope(self) -> None:
        with patch.object(push.shutil, "which", return_value="/usr/local/bin/lark-cli"), patch.object(push.subprocess, "run") as run:
            run.return_value.stdout = '{"ok":true,"data":{"url":"https://example.test/app"}}'
            url = push.publish_html(Path("/tmp/key_metrics_dashboard_test"), dry_run=False)

        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(url, "https://example.test/app")
        self.assertIn(["lark-cli", "apps", "+html-publish", "--app-id", push.MIAODA_APP_ID, "--path", "index.html", "--json"], commands)
        self.assertIn(["lark-cli", "apps", "+access-scope-set", "--app-id", push.MIAODA_APP_ID, "--scope", "tenant", "--json"], commands)
        self.assertTrue(run.call_args_list[0].kwargs["cwd"].endswith("/tmp/key_metrics_dashboard_test"))

    def test_output_dir_is_under_tmp_for_dolphinscheduler_permissions(self) -> None:
        self.assertEqual(push.OUTPUT_DIR, Path("/tmp/key_metrics_dashboard"))

    def test_publish_fails_when_lark_cli_missing(self) -> None:
        with patch.object(push.shutil, "which", return_value=None), patch.object(push.subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "未找到 lark-cli"):
                push.publish_html(Path("/tmp/key_metrics_dashboard_test"), dry_run=False)

        run.assert_not_called()

    def test_main_uses_payload_link_by_default_without_publishing(self) -> None:
        with (
            patch.object(push, "fetch_metrics", return_value=push.sample_metrics(date(2026, 7, 2))),
            patch.object(push, "publish_html") as publish_html,
            patch.object(push, "send_card") as send_card,
            patch.object(push, "write_html"),
            patch.object(sys, "argv", ["key_metrics_dashboard_push.py", "--date", "2026-07-02"]),
        ):
            push.main()

        publish_html.assert_not_called()
        card = send_card.call_args.args[0]
        dumped = json.dumps(card, ensure_ascii=False)
        self.assertIn(push.KEY_METRICS_DETAIL_URL + "?v=20260702_", dumped)
        self.assertIn("#payload=", dumped)

    def test_main_publishes_only_when_requested(self) -> None:
        with (
            patch.object(push, "fetch_metrics", return_value=push.sample_metrics(date(2026, 7, 2))),
            patch.object(push, "publish_html", return_value="https://example.test/app") as publish_html,
            patch.object(push, "send_card") as send_card,
            patch.object(push, "write_html"),
            patch.object(sys, "argv", ["key_metrics_dashboard_push.py", "--date", "2026-07-02", "--publish"]),
        ):
            push.main()

        publish_html.assert_called_once()
        card = send_card.call_args.args[0]
        dumped = json.dumps(card, ensure_ascii=False)
        self.assertIn("https://example.test/app?v=20260702_", dumped)
        self.assertIn("#payload=", dumped)

    def test_main_skips_publish_when_flag_set(self) -> None:
        with (
            patch.object(push, "fetch_metrics", return_value=push.sample_metrics(date(2026, 7, 2))),
            patch.object(push, "publish_html") as publish_html,
            patch.object(push, "send_card") as send_card,
            patch.object(push, "write_html"),
            patch.object(sys, "argv", ["key_metrics_dashboard_push.py", "--date", "2026-07-02", "--skip-publish"]),
        ):
            push.main()

        publish_html.assert_not_called()
        card = send_card.call_args.args[0]
        dumped = json.dumps(card, ensure_ascii=False)
        self.assertIn(push.KEY_METRICS_DETAIL_URL + "?v=20260702_", dumped)
        self.assertIn("#payload=", dumped)

    def test_main_allows_pre_july_sample_preview(self) -> None:
        with (
            patch.object(push, "publish_html") as publish_html,
            patch.object(push, "send_card") as send_card,
            patch.object(push, "write_html"),
            patch.object(sys, "argv", ["key_metrics_dashboard_push.py", "--sample", "--date", "2026-06-30", "--skip-publish"]),
        ):
            push.main()

        publish_html.assert_not_called()
        card = send_card.call_args.args[0]
        dumped = json.dumps(card, ensure_ascii=False)
        self.assertIn("数据截止 2026-06-30", dumped)

    def test_main_allows_pre_july_real_fetch_for_june_thirtieth_test(self) -> None:
        with (
            patch.object(push, "fetch_metrics", return_value=push.sample_metrics(date(2026, 6, 30))) as fetch_metrics,
            patch.object(push, "publish_html") as publish_html,
            patch.object(push, "send_card"),
            patch.object(push, "write_html"),
            patch.object(sys, "argv", ["key_metrics_dashboard_push.py", "--date", "2026-06-30", "--skip-publish", "--skip-card"]),
        ):
            push.main()

        fetch_metrics.assert_called_once_with(date(2026, 6, 30))
        publish_html.assert_not_called()


if __name__ == "__main__":
    unittest.main()
