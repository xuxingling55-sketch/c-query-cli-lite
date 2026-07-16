from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from review_pack.models import ReviewRequest
from review_pack.sql_loader import NotApplicableError, render_sql


def cte_body(sql: str, cte_name: str, next_cte_name: str) -> str:
    """Return one top-level CTE body for focused structural assertions."""
    start = sql.lower().index(f"{cte_name.lower()} as (")
    end = sql.lower().index(f"{next_cte_name.lower()} as (", start)
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


if __name__ == "__main__":
    unittest.main()
