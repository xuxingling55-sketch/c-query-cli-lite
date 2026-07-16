from datetime import date
import unittest

from review_pack.models import (
    CheckResult,
    ModuleResult,
    ReviewPackResult,
    ReviewRequest,
    parse_target,
)


class ReviewRequestTest(unittest.TestCase):
    def test_same_length_last_year_period(self):
        r = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        self.assertEqual(r.last_year_start, date(2025, 7, 1))
        self.assertEqual(r.last_year_end, date(2025, 7, 15))
        self.assertEqual(r.period_days, 15)
        self.assertEqual(r.target_amount, 120_000_000)

    def test_rejects_reversed_range(self):
        with self.assertRaisesRegex(ValueError, "截止日期不能早于开始日期"):
            ReviewRequest.create("暑促", "2026-07-15", "2026-07-01", "1.2亿")

    def test_rejects_unshiftable_leap_day(self):
        with self.assertRaisesRegex(ValueError, "去年同期无法保持相同月日"):
            ReviewRequest.create("闰日", "2024-02-29", "2024-03-01", "100万")

    def test_rejects_last_year_period_that_loses_a_day(self):
        with self.assertRaisesRegex(ValueError, "去年同期无法同时保持相同月日和天数"):
            ReviewRequest.create("跨闰日", "2024-02-28", "2024-03-01", "100万")

    def test_rejects_last_year_period_that_gains_a_day(self):
        with self.assertRaisesRegex(ValueError, "去年同期无法同时保持相同月日和天数"):
            ReviewRequest.create("跨闰日", "2025-02-28", "2025-03-01", "100万")

    def test_target_units(self):
        self.assertEqual(parse_target("3500万"), 35_000_000)
        self.assertEqual(parse_target("12000000"), 12_000_000)

    def test_rejects_non_positive_target(self):
        with self.assertRaisesRegex(ValueError, "目标金额必须大于零"):
            ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "0")

    def test_rejects_non_finite_target(self):
        for value in ("nan", "inf", "-inf"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "目标金额必须是有限正数"):
                    parse_target(value)

    def test_parses_optional_source_windows(self):
        r = ReviewRequest.create(
            "暑促",
            "2026-07-01",
            "2026-07-15",
            "1.2亿",
            deposit_source_start="2026-06-01",
            deposit_source_end="2026-06-30",
            reservoir_source_start="2026-05-01",
            reservoir_source_end="2026-05-31",
        )
        self.assertEqual(r.deposit_source_start, date(2026, 6, 1))
        self.assertEqual(r.deposit_source_end, date(2026, 6, 30))
        self.assertEqual(r.reservoir_source_start, date(2026, 5, 1))
        self.assertEqual(r.reservoir_source_end, date(2026, 5, 31))

    def test_rejects_incomplete_source_window(self):
        with self.assertRaisesRegex(ValueError, "定金策略来源日期必须同时提供开始和结束日期"):
            ReviewRequest.create(
                "暑促",
                "2026-07-01",
                "2026-07-15",
                "1.2亿",
                deposit_source_start="2026-06-01",
            )

    def test_rejects_reversed_strategy_source_windows(self):
        cases = (
            {
                "deposit_source_start": "2026-06-30",
                "deposit_source_end": "2026-06-01",
            },
            {
                "reservoir_source_start": "2026-05-31",
                "reservoir_source_end": "2026-05-01",
            },
        )
        for source_window in cases:
            with self.subTest(source_window=source_window):
                with self.assertRaisesRegex(ValueError, "截止日期不能早于开始日期"):
                    ReviewRequest.create(
                        "暑促",
                        "2026-07-01",
                        "2026-07-15",
                        "1.2亿",
                        **source_window,
                    )


class ResultModelsTest(unittest.TestCase):
    def test_shared_result_contract_defaults(self):
        request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        module = ModuleResult(module="sales", status="ok")
        check = CheckResult(
            check_id="sales-total",
            level="error",
            status="passed",
            module="sales",
            message="销售额一致",
        )
        result = ReviewPackResult(request=request, modules={"sales": module})

        self.assertEqual(module.rows, [])
        self.assertEqual(module.error, "")
        self.assertEqual(module.source_version, "v1")
        self.assertIsNone(check.actual)
        self.assertIsNone(check.expected)
        self.assertIsNone(check.difference)
        self.assertEqual(result.checks, [])
        self.assertEqual(result.local_snapshot, "")
        self.assertEqual(result.lark_url, "")


if __name__ == "__main__":
    unittest.main()
