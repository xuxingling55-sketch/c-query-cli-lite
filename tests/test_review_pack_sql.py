from pathlib import Path
from tempfile import TemporaryDirectory
import re
import unittest

from review_pack.catalog import LONG_COLUMNS, module_spec
from review_pack.models import ReviewRequest
from review_pack.sql_loader import NotApplicableError, render_sql


def cte_body(sql: str, cte_name: str, next_cte_name: str) -> str:
    """Return one top-level CTE body for focused structural assertions."""
    def find_cte(name: str, offset: int = 0) -> re.Match[str]:
        match = re.search(
            rf"(?im)(?:^|,\s*\n?)\s*{re.escape(name)}\s+AS\s*\(",
            sql[offset:],
        )
        if match is None:
            raise ValueError(f"CTE not found: {name}")
        return match

    start_match = find_cte(cte_name)
    start = start_match.start()
    end_match = find_cte(next_cte_name, start_match.end())
    end = start_match.end() + end_match.start()
    return sql[start:end]


class RenderSqlTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "query.sql"

    def test_replaces_dates_and_target(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        self.path.write_text(
            "SELECT {{CURRENT_START}} current_start, "
            "{{CURRENT_END}} current_end, "
            "{{LAST_YEAR_START}} last_year_start, "
            "{{LAST_YEAR_END}} last_year_end, "
            "{{TARGET}} target_amount "
            "FROM dws.topic_order_detail "
            "WHERE paid_time_sk BETWEEN {{CURRENT_START}} AND {{CURRENT_END}} "
            "LIMIT 10000",
            encoding="utf-8",
        )

        sql = render_sql(self.path, request)

        for value in ("20260701", "20260715", "20250701", "20250715", "120000000"):
            self.assertIn(value, sql)
        self.assertNotIn("{{", sql)

    def test_rejects_unknown_tokens(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        self.path.write_text(
            "SELECT {{UNKNOWN}} FROM dws.topic_order_detail "
            "WHERE paid_time_sk = 20260701 LIMIT 10000",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "未解析模板参数"):
            render_sql(self.path, request)

    def test_replaces_strategy_source_dates_independently(self):
        request = ReviewRequest.create(
            "暑促",
            "2026-07-01",
            "2026-07-15",
            "1.2亿",
            deposit_source_start="2026-06-24",
            deposit_source_end="2026-06-30",
            reservoir_source_start="2026-05-01",
            reservoir_source_end="2026-05-31",
        )
        self.path.write_text(
            "SELECT {{DEPOSIT_SOURCE_START}} deposit_start, "
            "{{DEPOSIT_SOURCE_END}} deposit_end, "
            "{{RESERVOIR_SOURCE_START}} reservoir_start, "
            "{{RESERVOIR_SOURCE_END}} reservoir_end "
            "FROM dws.topic_order_detail "
            "WHERE paid_time_sk BETWEEN {{CURRENT_START}} AND {{CURRENT_END}}",
            encoding="utf-8",
        )

        sql = render_sql(self.path, request)

        for value in ("20260624", "20260630", "20260501", "20260531"):
            self.assertIn(value, sql)

    def test_missing_strategy_window_is_not_applicable(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        self.path.write_text(
            "SELECT {{DEPOSIT_SOURCE_START}} "
            "FROM dws.topic_order_detail WHERE paid_time_sk = 20260701 LIMIT 10000",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(NotApplicableError, "定金策略来源日期"):
            render_sql(self.path, request)

    def test_converts_sql_validation_failure_to_clear_exception(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        self.path.write_text(
            "DELETE FROM dws.topic_order_detail WHERE paid_time_sk = {{CURRENT_START}}",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "SQL 安全检查失败.*危险关键字"):
            render_sql(self.path, request)

    def test_returns_normalized_sql_from_validator(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        self.path.write_text(
            "SELECT {{CURRENT_START}} current_start FROM dws.topic_order_detail "
            "WHERE paid_time_sk = {{CURRENT_START}};",
            encoding="utf-8",
        )

        sql = render_sql(self.path, request)

        self.assertTrue(sql.endswith("LIMIT 10000"))
        self.assertNotIn(";", sql)

    def test_core_templates_use_confirmed_periods_and_stages(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        root = Path("queries/review_pack")
        sqls = {
            name: render_sql(root / f"{name}.sql", request)
            for name in ("overview", "active_efficiency", "user_stage", "product_structure")
        }

        for sql in sqls.values():
            for token in ("20260701", "20260715", "20250701", "20250715"):
                self.assertIn(token, sql)
            self.assertIn("LIMIT 10000", sql.upper())
            for column in (
                "period",
                "channel",
                "dimension_type",
                "dimension_value",
                "metric",
                "value",
                "source_version",
                "data_updated_at",
                "definition_id",
            ):
                self.assertIn(column, sql.lower())

        self.assertIn("'1–3 年级'", sqls["user_stage"])
        self.assertIn("'4–6 年级'", sqls["user_stage"])
        self.assertNotIn("1-4年级", sqls["user_stage"])
        self.assertIn("'家庭包'", sqls["product_structure"])

    def test_core_templates_keep_confirmed_sources_and_filters(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        root = Path("queries/review_pack")
        active = render_sql(root / "active_efficiency.sql", request)
        stages = render_sql(root / "user_stage.sql", request)
        products = render_sql(root / "product_structure.sql", request)

        self.assertIn("aws.business_active_user_last_14_day", active)
        self.assertNotIn("dws.topic_order_detail", active)
        self.assertIn("COUNT(DISTINCT", active.upper())
        self.assertIn("'高净值－历史大会员可续购'", stages)
        self.assertIn("'高净值－历史大会员不可续购'", stages)
        for token in ("u_user IS NOT NULL", "is_test_user = 0", "original_amount >= 39"):
            self.assertIn(token, products)
        self.assertIn("'price_basis=original_amount'", products)

    def test_private_active_denominators_do_not_require_revenue_attribution(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        root = Path("queries/review_pack")

        for name in ("active_efficiency", "user_stage", "product_structure"):
            sql = render_sql(root / f"{name}.sql", request)
            all_users = cte_body(sql, "all_active_users", "private_active_users")
            private_users = cte_body(sql, "private_active_users", "channel_active_users")

            active_source = "from raw" if name == "active_efficiency" else "from active_raw"
            self.assertIn(active_source, all_users.lower())
            self.assertNotIn("channel is not null", all_users.lower())
            self.assertNotIn("business_gmv_attribution in", all_users.lower())
            self.assertIn("from all_active_users", private_users.lower())

        active = render_sql(root / "active_efficiency.sql", request)
        raw = cte_body(active, "raw", "all_active_users")
        self.assertIn("then coalesce(a.normal_price_amount, 0)", raw.lower())
        self.assertIn("else 0", raw.lower())

    def test_product_structure_has_channels_audience_breakdowns_and_fixed_grid(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        sql = render_sql(Path("queries/review_pack/product_structure.sql"), request)

        for token in (
            "'私域整体'",
            "'APP'",
            "'销售'",
            "'用户层级×商品'",
            "'学段×商品'",
            "dimension_grid",
            "'商品' AS dimension_type",
            "'用户层级×商品'",
            "'学段×商品'",
            "COALESCE(a.user_layer, '未映射')",
            "COALESCE(a.stage, '未知学段')",
        ):
            self.assertIn(token, sql)

        grid = cte_body(sql, "dimension_values", "dimension_grid")
        for token in ("FROM products", "FROM user_layer_values", "FROM stage_values"):
            self.assertIn(token, grid)

    def test_user_stage_keeps_unknowns_and_uses_fixed_dimension_grid(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        sql = render_sql(Path("queries/review_pack/user_stage.sql"), request)

        self.assertIn("'未映射'", sql)
        self.assertIn("'未知学段'", sql)
        self.assertIn("dimension_grid", sql)
        dimension_rows = cte_body(sql, "dimension_rows", "channels")
        self.assertNotIn("<> '未映射'", dimension_rows)
        self.assertNotIn("<> '未知学段'", dimension_rows)

        grid = cte_body(sql, "dimension_values", "dimension_grid")
        for token in ("FROM user_layer_values", "FROM stage_values", "JOIN stage_values"):
            self.assertIn(token, grid)

    def test_strategy_and_sales_templates_match_the_fixed_catalog(self):
        request = ReviewRequest.create(
            "暑促",
            "2026-07-01",
            "2026-07-15",
            "1.2亿",
            deposit_source_start="2026-06-24",
            deposit_source_end="2026-06-30",
            reservoir_source_start="2026-05-22",
            reservoir_source_end="2026-06-30",
        )
        root = Path("queries/review_pack")

        for name in ("deposit", "reservoir", "high_value", "sales_funnel"):
            sql = render_sql(root / f"{name}.sql", request)
            for period in ("本期", "去年同期"):
                self.assertIn(period, sql)
            for channel in ("私域整体", "APP", "销售"):
                self.assertIn(f"'{channel}'", sql)
            for column in LONG_COLUMNS:
                self.assertIn(column, sql.lower())
            for metric in module_spec(name).metrics:
                self.assertIn(f"'{metric}'", sql)

    def test_strategy_source_windows_are_independent_from_activity_windows(self):
        request = ReviewRequest.create(
            "暑促",
            "2026-07-01",
            "2026-07-15",
            "1.2亿",
            deposit_source_start="2026-06-24",
            deposit_source_end="2026-06-30",
            reservoir_source_start="2026-05-22",
            reservoir_source_end="2026-06-30",
        )
        root = Path("queries/review_pack")
        deposit = render_sql(root / "deposit.sql", request)
        reservoir = render_sql(root / "reservoir.sql", request)

        deposit_source = cte_body(deposit, "deposit_source_rows", "deposit_users")
        deposit_tail = cte_body(deposit, "tail_order_rows", "tail_orders")
        self.assertIn("20260624", deposit)
        self.assertIn("20260630", deposit)
        self.assertNotIn("20260715", deposit_source)
        self.assertIn("20260715", deposit_tail)

        reservoir_source = cte_body(reservoir, "reservoir_source_rows", "reservoir_users")
        reservoir_conversion = cte_body(reservoir, "conversion_order_rows", "conversion_orders")
        self.assertIn("20260522", reservoir)
        self.assertIn("20260630", reservoir)
        self.assertNotIn("20260715", reservoir_source)
        self.assertIn("20260715", reservoir_conversion)

    def test_sales_funnel_keeps_phone_branches_and_marks_wechat_missing(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        sql = render_sql(Path("queries/review_pack/sales_funnel.sql"), request)

        for token in ("有效接通", "未有效接通", "data_source_missing", "数据源未接入"):
            self.assertIn(token, sql)
        wechat = cte_body(sql, "wechat_metrics", "metrics")
        self.assertNotIn("call_phone_cnt", wechat)
        self.assertNotIn("call_through_cnt", wechat)

    def test_sales_funnel_is_nested_and_orders_follow_contact_events(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        sql = render_sql(Path("queries/review_pack/sales_funnel.sql"), request)

        pool = cte_body(sql, "pool_users", "phone_events")
        phone = cte_body(sql, "phone_events", "phone_users")
        receive_conversion = cte_body(sql, "conversion_after_receive", "conversion_after_connected")
        connect_conversion = cte_body(sql, "conversion_after_connected", "conversion_after_unconnected")
        unconnected_conversion = cte_body(sql, "conversion_after_unconnected", "funnel_users")

        self.assertIn("MIN(IF(d.recieve_u_user IS NOT NULL, d.day, NULL)) AS first_receive_day", pool)
        self.assertIn("FROM pool_users r", phone)
        self.assertIn("call_created_at", phone)
        self.assertIn("r.first_receive_day", phone)
        self.assertIn("p.end_day", phone)
        self.assertIn("FROM pool_users r", receive_conversion)
        self.assertIn("o.paid_time_sk >= r.first_receive_day", receive_conversion)
        self.assertIn("o.paid_time > p.first_connected_time", connect_conversion)
        self.assertIn("p.first_connected_time IS NULL", unconnected_conversion)
        self.assertIn("o.paid_time > p.first_call_time", unconnected_conversion)

    def test_strategy_users_have_one_stable_source_channel(self):
        request = ReviewRequest.create(
            "暑促", "2026-07-01", "2026-07-15", "1.2亿",
            deposit_source_start="2026-06-24", deposit_source_end="2026-06-30",
            reservoir_source_start="2026-05-22", reservoir_source_end="2026-06-30",
        )
        root = Path("queries/review_pack")
        for name, source_cte, user_cte in (
            ("deposit", "deposit_source_ranked", "deposit_users"),
            ("reservoir", "reservoir_source_ranked", "reservoir_users"),
        ):
            sql = render_sql(root / f"{name}.sql", request)
            ranked = cte_body(sql, source_cte, user_cte)
            users = cte_body(sql, user_cte, "activity_audience" if name == "deposit" else "active_audience")
            self.assertIn("ROW_NUMBER() OVER", ranked)
            self.assertIn("PARTITION BY period, user_id", ranked)
            self.assertIn("source_time DESC, order_id DESC", ranked)
            self.assertIn("source_rank = 1", users)
            self.assertNotIn("GROUP BY period, channel, user_id", users)

    def test_strategy_templates_build_fixed_dimension_grids(self):
        request = ReviewRequest.create(
            "暑促", "2026-07-01", "2026-07-15", "1.2亿",
            deposit_source_start="2026-06-24", deposit_source_end="2026-06-30",
            reservoir_source_start="2026-05-22", reservoir_source_end="2026-06-30",
        )
        root = Path("queries/review_pack")
        for name in ("deposit", "reservoir", "sales_funnel"):
            sql = render_sql(root / f"{name}.sql", request)
            for cte in ("channels AS (", "user_layer_values AS (", "stage_values AS (", "dimension_grid AS ("):
                self.assertIn(cte, sql)
            grid = cte_body(sql, "dimension_grid", "summary_actual")
            self.assertIn("CROSS JOIN channels", grid)
            self.assertIn("CROSS JOIN user_layer_values", grid)
            self.assertIn("CROSS JOIN stage_values", grid)
            summary = cte_body(sql, "summary_actual", "summary")
            self.assertNotIn("MAX(user_layer)", summary)
            self.assertNotIn("MAX(stage)", summary)

        high_value = render_sql(root / "high_value.sql", request)
        for cte in ("layer_grid AS (", "stage_grid AS (", "product_grid AS ("):
            self.assertIn(cte, high_value)
        self.assertNotIn("CROSS JOIN high_value_layers u CROSS JOIN stage_values", high_value)

    def test_high_value_preserves_line_items_and_scopes_combo_metrics(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        sql = render_sql(Path("queries/review_pack/high_value.sql"), request)
        order_rows = cte_body(sql, "order_line_rows", "product_order_lines")
        product_metrics = cte_body(sql, "product_metrics", "independent_metrics")

        self.assertIn("o.sku_group_good_id", order_rows)
        self.assertNotIn("MAX(business_good_kind", order_rows)
        self.assertIn("WHERE product = '组合品'", product_metrics)
        self.assertNotIn("product IN ('全部', '组合品')", product_metrics)
        self.assertNotIn("WHERE product NOT IN", product_metrics)
        self.assertIn("source_users", sql)
        self.assertIn("active_users", sql)

    def test_strategy_stage_comes_from_one_latest_fact_row(self):
        request = ReviewRequest.create(
            "暑促", "2026-07-01", "2026-07-15", "1.2亿",
            deposit_source_start="2026-06-24", deposit_source_end="2026-06-30",
            reservoir_source_start="2026-05-22", reservoir_source_end="2026-06-30",
        )
        for name, cte_name, next_name in (
            ("deposit", "activity_audience", "tail_order_rows"),
            ("reservoir", "active_audience", "conversion_order_rows"),
        ):
            sql = render_sql(Path(f"queries/review_pack/{name}.sql"), request)
            audience = cte_body(sql, cte_name, next_name)
            self.assertIn("ROW_NUMBER() OVER", audience)
            self.assertIn("ORDER BY a.day DESC", audience)
            self.assertIn("fact_rank = 1", audience)
            self.assertNotIn("MAX(CASE WHEN a.grade_name_month", audience)

    def test_active_fact_ranking_has_stable_business_label_tiebreakers(self):
        request = ReviewRequest.create(
            "暑促", "2026-07-01", "2026-07-15", "1.2亿",
            deposit_source_start="2026-06-24", deposit_source_end="2026-06-30",
            reservoir_source_start="2026-05-22", reservoir_source_end="2026-06-30",
        )
        cases = (
            ("deposit", "activity_audience", "tail_order_rows"),
            ("reservoir", "active_audience", "conversion_order_rows"),
            ("sales_funnel", "active_ranked", "active_users"),
        )

        for name, cte_name, next_name in cases:
            sql = render_sql(Path(f"queries/review_pack/{name}.sql"), request)
            ranked = cte_body(sql, cte_name, next_name)
            normalized = re.sub(r"\s+", " ", ranked)

            self.assertRegex(
                normalized,
                r"ORDER BY a\.day DESC, CASE .*高净值用户.* THEN 1 .*新增.* THEN 2 "
                r".*老未.* THEN 3 .*续费.* THEN 4 .* ELSE 5 END",
            )
            self.assertIn("a.grade_name_month IS NULL", ranked)
            self.assertIn("a.user_strategy_tag_level2_month IS NULL", ranked)
            self.assertIn("a.user_strategy_tag_level2_month DESC", ranked)

    def test_sales_private_active_row_uses_nonconstant_stable_tiebreakers(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        sql = render_sql(Path("queries/review_pack/sales_funnel.sql"), request)
        active_users = cte_body(sql, "active_users", "pool_users")
        normalized = re.sub(r"\s+", " ", active_users)

        self.assertIn("fact_day DESC", normalized)
        self.assertIn("user_layer_priority", normalized)
        self.assertIn("stage_nonempty_priority", normalized)
        self.assertIn("stage_priority", normalized)
        self.assertIn("tag_priority", normalized)
        self.assertNotIn("ORDER BY CASE WHEN channel IS NULL", normalized)
        self.assertNotRegex(normalized, r"ORDER BY[^)]*\buser_id\b")

    def test_third_review_semantics_and_bounded_high_value_output(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        high = render_sql(Path("queries/review_pack/high_value.sql"), request)
        sales = render_sql(Path("queries/review_pack/sales_funnel.sql"), request)
        self.assertIn("dws.topic_user_active_detail_month", high)
        self.assertIn("user_strategy_tag_month", high)
        self.assertIn("'高净值层级' AS dimension_type", high)
        self.assertIn("'学段' AS dimension_type", high)
        self.assertIn("'商品' AS dimension_type", high)
        self.assertNotIn("高净值细分×学段×商品", high)
        # 6 层（含独立未知层）和 5 学段各 13 项；8 商品各 9 项，组合品再加 4 项。
        self.assertLess(2 * 3 * (6 * 13 + 5 * 13 + 8 * 9 + 4), 10000)
        self.assertIn("LIMIT 10000", high)
        self.assertIn("is_valid_connect", sales)
        self.assertNotIn("c.is_connect", sales)
        self.assertIn("private_active_users", sales)

    def test_strategy_conversion_uses_earliest_source_but_channel_uses_latest(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿", deposit_source_start="2026-06-24", deposit_source_end="2026-06-30", reservoir_source_start="2026-05-22", reservoir_source_end="2026-06-30")
        for name in ("deposit", "reservoir"):
            sql = render_sql(Path(f"queries/review_pack/{name}.sql"), request)
            self.assertIn("MIN(source_time) OVER(PARTITION BY period,user_id) earliest_source_time", sql)
            self.assertIn("ORDER BY source_time DESC, order_id DESC", sql)
            self.assertIn("o.paid_time", sql)
            self.assertIn("earliest_source_time", sql)

    def test_high_value_source_pool_uses_history_for_one_stable_channel(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        sql = render_sql(Path("queries/review_pack/high_value.sql"), request)

        for cte in ("source_pool_raw", "source_pool_ranked", "attribution_order_rows", "attribution_ranked", "attributed_source_users"):
            self.assertIn(f"{cte} AS (", sql)
        source_pool = cte_body(sql, "source_pool_raw", "source_pool_ranked")
        history = cte_body(sql, "attribution_order_rows", "attribution_ranked")
        ranked = cte_body(sql, "attribution_ranked", "attributed_source_users")
        attributed = cte_body(sql, "attributed_source_users", "source_users")
        source_users = cte_body(sql, "source_users", "active_users")

        self.assertIn("dws.topic_user_active_detail_month", source_pool)
        self.assertIn("user_strategy_tag_month", source_pool)
        self.assertIn("o.paid_time_sk < p.start_day", history)
        self.assertIn("o.is_test_user = 0", history)
        self.assertIn("o.original_amount >= 39", history)
        self.assertIn("o.business_gmv_attribution IN ('商业化', '电销')", history)
        self.assertIn("ROW_NUMBER() OVER", ranked)
        self.assertIn("PARTITION BY period, user_id", ranked)
        self.assertIn("ORDER BY source_time DESC, order_id DESC", ranked)
        self.assertIn("source_rank = 1", attributed)
        self.assertIn("'私域整体' AS channel", source_users)
        self.assertIn("FROM source_pool", source_users)
        self.assertIn("JOIN attributed_source_users", source_users)

    def test_high_value_builds_three_independent_raw_aggregates(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        sql = render_sql(Path("queries/review_pack/high_value.sql"), request)

        for cte in ("layer_actual", "stage_actual", "product_actual", "layer_combo_actual", "independent_metrics", "output_rows"):
            self.assertIn(f"{cte} AS (", sql)
        layer = cte_body(sql, "layer_actual", "stage_actual")
        stage = cte_body(sql, "stage_actual", "product_actual")
        product = cte_body(sql, "product_actual", "layer_combo_actual")
        final_rows = cte_body(sql, "independent_metrics", "output_rows")

        for aggregate in (layer, stage, product):
            for token in (
                "COUNT(DISTINCT s.user_id)",
                "COUNT(DISTINCT a.user_id)",
                "COUNT(DISTINCT o.user_id)",
                "COUNT(DISTINCT o.order_id)",
                "SUM(o.revenue)",
            ):
                self.assertIn(token, aggregate)
        self.assertIn("'高净值层级' AS dimension_type", final_rows)
        self.assertIn("'学段' AS dimension_type", final_rows)
        self.assertIn("'商品' AS dimension_type", final_rows)
        self.assertNotIn("SUM(value)", sql)
        self.assertNotIn("SUM(pay_users/", sql)
        self.assertNotIn("SUM(revenue/", sql)

    def test_high_value_fixed_layers_keep_unknown_separate(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        sql = render_sql(Path("queries/review_pack/high_value.sql"), request)

        for cte in ("fixed_high_value_layers", "unknown_high_value_layers", "high_value_layers", "source_pool_raw", "source_pool_ranked"):
            self.assertIn(f"{cte} AS (", sql)
        fixed_layers = cte_body(sql, "fixed_high_value_layers", "unknown_high_value_layers")
        unknown_layers = cte_body(sql, "unknown_high_value_layers", "source_pool_raw")
        source_pool = cte_body(sql, "source_pool_raw", "source_pool_ranked")

        for layer in (
            "高净值汇总",
            "高净值－当年毕业",
            "高净值－历史大会员可续购",
            "高净值－历史大会员不可续购",
            "高净值－其他组合品",
        ):
            self.assertIn(f"'{layer}'", fixed_layers)
        self.assertNotIn("未知", fixed_layers)
        self.assertIn("'高净值－未知标签'", unknown_layers)
        self.assertIn("ELSE '高净值－未知标签'", source_pool)
        self.assertIn("REGEXP '付费组合品用户|付费加购品用户'", source_pool)

    def test_high_value_reaggregates_combo_and_keeps_one_product_rule(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        sql = render_sql(Path("queries/review_pack/high_value.sql"), request)

        for cte in ("product_order_lines", "audience_order_lines", "layer_combo_actual", "stage_combo_actual", "layer_summary", "product_metrics", "independent_metrics"):
            self.assertIn(f"{cte} AS (", sql)
        order_lines = cte_body(sql, "order_line_rows", "product_order_lines")
        product_lines = cte_body(sql, "product_order_lines", "audience_order_lines")
        layer_combo = cte_body(sql, "layer_combo_actual", "stage_combo_actual")
        stage_combo = cte_body(sql, "stage_combo_actual", "layer_summary")
        product_metrics = cte_body(sql, "product_metrics", "independent_metrics")

        self.assertIn("o.sku_group_good_id", order_lines)
        self.assertIn("o.sub_amount AS revenue", order_lines)
        for token in (
            "business_good_kind_name_level_3 = '小学品加拓展'",
            "good_name LIKE '从小学%'",
            "good_kind_name_level_3 = '拓展课'",
            "good_stage_subject REGEXP '1-2-specialCourse'",
            "good_stage_subject REGEXP '1-6-specialCourse'",
            "good_stage_subject REGEXP '1-7-specialCourse'",
        ):
            self.assertIn(token, product_lines)
        for aggregate in (layer_combo, stage_combo):
            self.assertIn("COUNT(DISTINCT o.user_id)", aggregate)
            self.assertIn("COUNT(DISTINCT o.order_id)", aggregate)
            self.assertIn("SUM(o.revenue)", aggregate)
        self.assertIn("WHERE product = '组合品'", product_metrics)
        self.assertNotIn("product IN ('全部', '组合品')", product_metrics)


if __name__ == "__main__":
    unittest.main()
