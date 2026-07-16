from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from review_pack.models import ReviewRequest
from review_pack.sql_loader import NotApplicableError, render_sql


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


if __name__ == "__main__":
    unittest.main()
