from copy import deepcopy
from datetime import datetime
from math import inf
from pathlib import Path
import unittest

from review_pack.models import ModuleResult, ReviewPackResult, ReviewRequest
from review_pack.normalize import pair_periods
from review_pack.sql_loader import render_sql
from review_pack.validation import check_channel_sum, check_formula, validate_pack


REQUIRED_ROW = {
    "channel": "私域整体",
    "dimension_type": "总览",
    "dimension_value": "全部",
    "metric": "营收",
    "source_version": "v1",
    "definition_id": "test-v1",
    "current_value": 100,
    "last_year_value": 80,
    "period_status": "complete",
    "current_date_range": "2026-07-01/2026-07-15",
    "last_year_date_range": "2025-07-01/2025-07-15",
    "data_updated_at": datetime(2026, 7, 16, 9, 0),
}


def row(metric="营收", **overrides):
    item = dict(REQUIRED_ROW, metric=metric, definition_id=f"{metric}-v1")
    item.update(overrides)
    return item


def duplicate_key_rows():
    return [row(), row()]


def rows_with_pay_20_active_50_rate_point_5():
    return [
        row("活跃用户", current_value=50, last_year_value=50),
        row("支付用户", current_value=20, last_year_value=20),
        row("转化率", current_value=0.5, last_year_value=0.4),
    ]


def current_period_only_rows():
    return [row(last_year_value=None, period_status="missing_last_year")]


def rows_with_orders_minus_1():
    return [row("订单量", current_value=-1, last_year_value=1)]


def pack_with_rows(module, rows):
    request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", 1000)
    return ReviewPackResult(
        request=request,
        modules={module: ModuleResult(module=module, status="success", rows=rows)},
    )


class ReviewPackValidationTest(unittest.TestCase):
    def test_channel_mismatch_reports_difference(self):
        rows = [
            {"metric": "营收", "channel": "私域整体", "current_value": 120},
            {"metric": "营收", "channel": "APP", "current_value": 50},
            {"metric": "营收", "channel": "销售", "current_value": 60},
        ]

        check = check_channel_sum("overview", rows, 0.01)[0]

        self.assertEqual(check.status, "failed")
        self.assertEqual(check.difference, 10)

    def test_required_failures_are_reported(self):
        cases = [
            ("duplicate_key", duplicate_key_rows(), "duplicate_key"),
            (
                "conversion_formula",
                rows_with_pay_20_active_50_rate_point_5(),
                "formula_conversion",
            ),
            ("missing_last_year", current_period_only_rows(), "period_complete"),
            ("negative_count", rows_with_orders_minus_1(), "non_negative"),
        ]
        for name, rows, check_id in cases:
            with self.subTest(name=name):
                result = pack_with_rows("overview", rows)
                failed = {
                    item.check_id
                    for item in validate_pack(result)
                    if item.status == "failed"
                }
                self.assertIn(check_id, failed)

    def test_validation_does_not_mutate_pack(self):
        result = pack_with_rows("overview", [row()])
        before = deepcopy(result)

        validate_pack(result)

        self.assertEqual(result, before)

    def test_module_status_distinguishes_optional_unavailability(self):
        result = pack_with_rows("overview", [row()])
        result.modules["deposit"] = ModuleResult(
            module="deposit", status="not_applicable", error="未提供来源期"
        )
        result.modules["sales_funnel"] = ModuleResult(
            module="sales_funnel", status="failed", error="query failed"
        )

        checks = validate_pack(result)

        deposit = [
            item
            for item in checks
            if item.module == "deposit" and item.check_id == "module_status"
        ][0]
        sales = [
            item
            for item in checks
            if item.module == "sales_funnel" and item.check_id == "module_status"
        ][0]
        self.assertEqual(deposit.status, "warning")
        self.assertEqual(sales.status, "failed")

    def test_missing_required_column_and_conflicting_key_fail(self):
        incomplete = row()
        del incomplete["definition_id"]
        conflicting = row(current_value=101)
        result = pack_with_rows("overview", [incomplete, row(), conflicting])

        failed = {
            item.check_id for item in validate_pack(result) if item.status == "failed"
        }

        self.assertIn("required_columns", failed)
        self.assertIn("conflicting_key", failed)

    def test_channel_check_only_adds_additive_metrics(self):
        def channel_row(metric, channel, value):
            return {
                "metric": metric,
                "channel": channel,
                "dimension_type": "渠道",
                "dimension_value": channel,
                "current_value": value,
            }

        rows = [
            channel_row("营收", "私域整体", 110),
            channel_row("营收", "APP", 50),
            channel_row("营收", "销售", 60),
            channel_row("转化率", "私域整体", 0.4),
            channel_row("转化率", "APP", 0.2),
            channel_row("转化率", "销售", 0.3),
            channel_row("活跃人数", "私域整体", 90),
            channel_row("活跃人数", "APP", 50),
            channel_row("活跃人数", "销售", 50),
        ]

        checks = check_channel_sum("active_efficiency", rows, 0.01)

        revenue = [item for item in checks if item.actual == 110][0]
        overlap = [item for item in checks if item.check_id == "channel_overlap"][0]
        self.assertEqual(revenue.status, "passed")
        self.assertEqual(overlap.status, "warning")
        self.assertFalse(any(item.actual == 0.4 for item in checks))

    def test_non_partition_channel_details_are_summarized_once(self):
        rows = []
        for value, private, app, sales in (
            ("新增×组合品", 120, 50, 60),
            ("续费×组合品", 90, 40, 45),
        ):
            for channel, amount in (
                ("私域整体", private),
                ("APP", app),
                ("销售", sales),
            ):
                rows.append(
                    {
                        "metric": "营收",
                        "channel": channel,
                        "dimension_type": "用户层级×商品",
                        "dimension_value": value,
                        "current_value": amount,
                    }
                )

        checks = check_channel_sum("product_structure", rows, 0.01)

        self.assertFalse(any(item.status == "failed" for item in checks))
        warnings = [
            item
            for item in checks
            if item.check_id == "channel_sum_unverifiable"
        ]
        self.assertEqual(len(warnings), 1)
        self.assertIn("用户层级×商品", warnings[0].message)

    def test_product_base_dimension_still_fails_real_channel_mismatch(self):
        rows = [
            {
                "metric": "营收",
                "channel": channel,
                "dimension_type": "商品",
                "dimension_value": "组合品",
                "current_value": value,
            }
            for channel, value in (("私域整体", 120), ("APP", 50), ("销售", 60))
        ]

        checks = check_channel_sum("product_structure", rows, 0.01)

        self.assertTrue(
            any(item.check_id == "channel_sum" and item.status == "failed" for item in checks)
        )

    def test_unique_strategy_channels_strong_check_people_but_sales_does_not(self):
        def channel_rows(metric):
            return [
                {
                    "metric": metric,
                    "channel": channel,
                    "dimension_type": "用户层级×学段",
                    "dimension_value": "新增×高中",
                    "current_value": value,
                }
                for channel, value in (("私域整体", 12), ("APP", 5), ("销售", 6))
            ]

        for module, metric in (
            ("deposit", "尾款人数"),
            ("reservoir", "蓄水来源用户数"),
        ):
            with self.subTest(module=module):
                checks = check_channel_sum(module, channel_rows(metric), 0.01)
                self.assertTrue(
                    any(
                        item.check_id == "channel_sum"
                        and item.status == "failed"
                        for item in checks
                    )
                )

        sales = check_channel_sum(
            "sales_funnel", channel_rows("线索领取人数"), 0.01
        )
        self.assertFalse(
            any(item.check_id == "channel_sum" and item.status == "failed" for item in sales)
        )

    def test_dimension_total_includes_unknown_bucket(self):
        result = pack_with_rows(
            "active_efficiency",
            [row("营收", dimension_type="渠道", current_value=100, last_year_value=80)],
        )
        result.modules["user_stage"] = ModuleResult(
            module="user_stage",
            status="success",
            rows=[
                row(
                    "营收",
                    dimension_type="学段",
                    dimension_value="小学",
                    current_value=70,
                    last_year_value=60,
                ),
                row(
                    "营收",
                    dimension_type="学段",
                    dimension_value="未知",
                    current_value=20,
                    last_year_value=20,
                ),
                row(
                    "活跃人数",
                    dimension_type="学段",
                    dimension_value="小学",
                    current_value=70,
                    last_year_value=60,
                ),
                row(
                    "活跃人数",
                    dimension_type="学段",
                    dimension_value="未知",
                    current_value=20,
                    last_year_value=20,
                ),
            ],
        )

        checks = validate_pack(result)
        failed = {
            item.check_id
            for item in checks
            if item.status == "failed"
        }

        self.assertIn("dimension_sum", failed)
        self.assertTrue(
            any(
                item.check_id == "stage_unknown_coverage"
                and item.status == "warning"
                for item in checks
            )
        )

    def test_deposit_and_sales_conservation(self):
        deposit_rows = [
            row("定金来源用户数", current_value=10, last_year_value=8),
            row("尾款人数", current_value=4, last_year_value=3),
            row("转组合品人数", current_value=3, last_year_value=2),
            row("转498人数", current_value=2, last_year_value=2),
            row("转其他商品人数", current_value=1, last_year_value=1),
            row("未转化人数", current_value=5, last_year_value=3),
        ]
        sales_rows = [
            row("电话拨打人数", current_value=20, last_year_value=10),
            row("有效接通人数", current_value=8, last_year_value=5),
            row("未有效接通人数", current_value=11, last_year_value=5),
        ]

        deposit_failed = {
            item.check_id
            for item in validate_pack(pack_with_rows("deposit", deposit_rows))
            if item.status == "failed"
        }
        sales_failed = {
            item.check_id
            for item in validate_pack(pack_with_rows("sales_funnel", sales_rows))
            if item.status == "failed"
        }

        self.assertIn("deposit_conservation", deposit_failed)
        self.assertIn("sales_conservation", sales_failed)

    def test_deposit_conservation_allows_overlapping_product_destinations(self):
        rows = [
            row("定金来源用户数", current_value=10, last_year_value=8),
            row("尾款人数", current_value=6, last_year_value=5),
            row("未转化人数", current_value=4, last_year_value=3),
            row("转组合品人数", current_value=5, last_year_value=4),
            row("转498人数", current_value=4, last_year_value=3),
            row("转其他商品人数", current_value=2, last_year_value=1),
        ]

        checks = validate_pack(pack_with_rows("deposit", rows))

        conservation = [
            item for item in checks if item.check_id == "deposit_conservation"
        ]
        self.assertTrue(conservation)
        self.assertTrue(all(item.status == "passed" for item in conservation))
        self.assertTrue(
            any(
                item.check_id == "deposit_destination_overlap"
                and item.status == "warning"
                for item in checks
            )
        )

    def test_formula_checks_conversion_aov_and_arpu(self):
        rows = [
            row("活跃人数", current_value=50, last_year_value=40),
            row("付费人数", current_value=20, last_year_value=10),
            row("付费金额", current_value=200, last_year_value=100),
            row("付费转化率", current_value=0.4, last_year_value=0.25),
            row("客单价", current_value=9, last_year_value=10),
            row("ARPU", current_value=4, last_year_value=2.5),
        ]

        checks = check_formula("active_efficiency", rows, 0.01)
        by_id = {item.check_id: item for item in checks}

        self.assertEqual(by_id["formula_conversion"].status, "passed")
        self.assertEqual(by_id["formula_aov"].status, "failed")
        self.assertEqual(by_id["formula_arpu"].status, "passed")

    def test_goal_completion_can_exceed_one_but_bounded_rate_cannot(self):
        bad_percentage = row("目标完成率", current_value=1.2, last_year_value=0.5)
        impossible_conversion = row(
            "付费转化率", current_value=1.2, last_year_value=0.5
        )
        stale = row(data_updated_at=datetime(2026, 7, 14, 23, 59))
        result = pack_with_rows(
            "overview", [bad_percentage, impossible_conversion, stale]
        )

        checks = validate_pack(result)
        percentage_failures = [
            item
            for item in checks
            if item.check_id == "percentage_range" and item.status == "failed"
        ]

        self.assertEqual([item.actual for item in percentage_failures], [1.2])
        self.assertTrue(
            any(
                item.check_id == "update_freshness" and item.status == "failed"
                for item in checks
            )
        )

    def test_overview_current_only_metrics_allow_missing_last_year(self):
        current_only_metrics = (
            "活动目标",
            "目标完成额",
            "目标完成率",
            "目标差额",
            "时间进度",
            "营收进度与时间进度差",
        )
        rows = [
            row(
                metric,
                current_value=1,
                last_year_value=None,
                period_status="missing_last_year",
            )
            for metric in current_only_metrics
        ]
        rows.append(
            row(
                "营收",
                current_value=100,
                last_year_value=None,
                period_status="missing_last_year",
            )
        )

        failures = [
            item
            for item in validate_pack(pack_with_rows("overview", rows))
            if item.check_id == "period_complete" and item.status == "failed"
        ]

        self.assertEqual(len(failures), 1)
        self.assertIn("营收", failures[0].message)

    def test_optional_metric_source_is_a_warning(self):
        unavailable = [
            row(
                metric,
                dimension_type="用户层级×学段",
                dimension_value="新增×1–3 年级×数据源未接入",
                source_version="data_source_missing",
                definition_id="sales_funnel.wechat.data_source_missing.v1",
                current_value=None,
                last_year_value=None,
            )
            for metric in ("企微添加人数", "企微添加率")
        ]

        checks = validate_pack(pack_with_rows("sales_funnel", unavailable))

        optional = [item for item in checks if item.check_id == "optional_source"]
        self.assertEqual(len(optional), 1)
        self.assertEqual(optional[0].status, "warning")
        self.assertFalse(
            any(
                item.status == "failed"
                and item.check_id.startswith(("numeric_value", "formula"))
                for item in checks
            )
        )

    def test_sales_numeric_rows_validate_formulas_and_conservation(self):
        overrides = {
            "dimension_type": "用户层级×学段",
            "dimension_value": "新增×1–3 年级",
            "source_version": "v2;event_ordered_nested_funnel",
            "definition_id": "sales_funnel.nested_event_ordered.v2",
        }
        rows = [
            row("线索领取人数", current_value=50, last_year_value=40, **overrides),
            row("电话拨打人数", current_value=20, last_year_value=10, **overrides),
            row("有效接通人数", current_value=8, last_year_value=4, **overrides),
            row("有效接通率", current_value=0.4, last_year_value=0.4, **overrides),
            row("未有效接通人数", current_value=12, last_year_value=6, **overrides),
            row("转化人数", current_value=10, last_year_value=8, **overrides),
            row("转化率", current_value=0.2, last_year_value=0.2, **overrides),
            row("转化营收", current_value=100, last_year_value=80, **overrides),
            row("客单价", current_value=10, last_year_value=10, **overrides),
            row("ARPU", current_value=2, last_year_value=2, **overrides),
        ]

        checks = validate_pack(pack_with_rows("sales_funnel", rows))

        self.assertTrue(
            any(
                item.check_id == "sales_conservation" and item.status == "passed"
                for item in checks
            )
        )
        for check_id in ("formula_conversion", "formula_aov", "formula_arpu"):
            self.assertTrue(
                any(item.check_id == check_id and item.status == "passed" for item in checks)
            )

    def test_sales_numeric_strings_fail_instead_of_being_parsed(self):
        invalid = row(
            "线索领取人数",
            current_value="50",
            last_year_value="40",
            dimension_type="用户层级×学段",
            dimension_value="新增×1–3 年级",
            source_version="v2;event_ordered_nested_funnel",
            definition_id="sales_funnel.nested_event_ordered.v2",
        )

        checks = validate_pack(pack_with_rows("sales_funnel", [invalid]))

        self.assertTrue(
            any(
                item.check_id == "numeric_value" and item.status == "failed"
                for item in checks
            )
        )

    def test_data_source_missing_marker_does_not_hide_other_invalid_metrics(self):
        invalid = row(
            "转化人数",
            current_value=None,
            last_year_value=None,
            dimension_type="用户层级×学段",
            dimension_value="新增×1–3 年级×数据源未接入",
            source_version="data_source_missing",
            definition_id="sales_funnel.wechat.data_source_missing.v1",
        )

        checks = validate_pack(pack_with_rows("sales_funnel", [invalid]))

        self.assertTrue(
            any(
                item.check_id == "numeric_value" and item.status == "failed"
                for item in checks
            )
        )

    def test_cross_module_stage_total_uses_unknown_bucket(self):
        result = pack_with_rows(
            "active_efficiency",
            [row("营收", current_value=100, last_year_value=80)],
        )
        result.modules["user_stage"] = ModuleResult(
            module="user_stage",
            status="success",
            rows=[
                row(
                    "营收",
                    dimension_type="学段",
                    dimension_value="小学",
                    current_value=70,
                    last_year_value=60,
                ),
                row(
                    "营收",
                    dimension_type="学段",
                    dimension_value="未知",
                    current_value=20,
                    last_year_value=20,
                ),
            ],
        )

        failed = [
            item
            for item in validate_pack(result)
            if item.check_id == "dimension_sum" and item.status == "failed"
        ]

        self.assertTrue(failed)

    def test_segmented_sales_formulas_are_checked(self):
        rows = [
            row("有效接通人数", current_value=8, last_year_value=4),
            row("有效接通后转化人数", current_value=2, last_year_value=1),
            row("有效接通后转化率", current_value=0.3, last_year_value=0.25),
            row("有效接通后营收", current_value=100, last_year_value=40),
            row("有效接通后客单价", current_value=50, last_year_value=40),
            row("有效接通后ARPU", current_value=12.5, last_year_value=10),
        ]

        checks = check_formula("sales_funnel", rows, 0.01)

        self.assertTrue(
            any(
                item.check_id == "formula_conversion" and item.status == "failed"
                for item in checks
            )
        )
        self.assertTrue(
            any(item.check_id == "formula_aov" and item.status == "passed" for item in checks)
        )
        self.assertTrue(
            any(item.check_id == "formula_arpu" and item.status == "passed" for item in checks)
        )

    def test_missing_metric_and_non_numeric_mandatory_value_fail(self):
        invalid = row("营收", current_value="不可用", last_year_value=80)

        failed = {
            item.check_id
            for item in validate_pack(pack_with_rows("overview", [invalid]))
            if item.status == "failed"
        }

        self.assertIn("required_results", failed)
        self.assertIn("numeric_value", failed)

    def test_zero_denominator_null_rate_is_not_a_missing_period(self):
        rows = [
            row("活跃人数", current_value=0, last_year_value=0),
            row("付费人数", current_value=0, last_year_value=0),
            row("付费转化率", current_value=None, last_year_value=None),
        ]

        checks = validate_pack(pack_with_rows("active_efficiency", rows))

        self.assertFalse(any(item.check_id == "period_complete" for item in checks))
        zero_checks = [item for item in checks if item.check_id == "zero_denominator"]
        self.assertEqual(len(zero_checks), 2)
        self.assertTrue(all(item.status == "warning" for item in zero_checks))

    def test_zero_denominator_rejects_fake_zero_rate(self):
        rows = [
            row("活跃人数", current_value=0, last_year_value=0),
            row("付费人数", current_value=0, last_year_value=0),
            row("付费转化率", current_value=0, last_year_value=0),
        ]

        checks = validate_pack(pack_with_rows("active_efficiency", rows))

        failures = [
            item for item in checks
            if item.check_id == "zero_denominator" and item.status == "failed"
        ]
        self.assertEqual(len(failures), 2)

    def test_overview_requires_service_metrics_for_each_channel(self):
        required = ("营收", "服务期营收", "业务营收与服务期营收差额")
        rows = [
            row(metric, channel=channel, dimension_type="经营总览", dimension_value=channel)
            for channel in ("私域整体", "APP", "销售")
            for metric in required
            if not (channel == "APP" and metric == "服务期营收")
        ]

        checks = validate_pack(pack_with_rows("overview", rows))

        self.assertTrue(any(
            item.check_id == "required_results_by_channel"
            and item.status == "failed"
            and "APP" in item.message
            and "服务期营收" in item.message
            for item in checks
        ))

    def test_every_core_module_requires_each_metric_by_channel(self):
        rows = [
            row("活跃人数", channel="私域整体", dimension_type="渠道", dimension_value="私域整体"),
            row("活跃人数", channel="销售", dimension_type="渠道", dimension_value="销售"),
        ]

        checks = validate_pack(pack_with_rows("active_efficiency", rows))

        self.assertTrue(any(
            item.check_id == "required_results_by_channel"
            and item.status == "failed"
            and "APP" in item.message
            and "活跃人数" in item.message
            for item in checks
        ))

    def test_nonzero_denominator_null_formula_fails(self):
        rows = [
            row("活跃人数", current_value=50, last_year_value=40),
            row("付费人数", current_value=20, last_year_value=10),
            row("付费转化率", current_value=None, last_year_value=0.25),
        ]

        checks = validate_pack(pack_with_rows("active_efficiency", rows))

        self.assertTrue(
            any(
                item.check_id == "formula_conversion"
                and item.status == "failed"
                and item.actual is None
                for item in checks
            )
        )

    def test_nonzero_denominator_null_formula_fails_when_numerator_is_unavailable(self):
        rows = [
            row("活跃蓄水用户数", current_value=5, last_year_value=4),
            row(
                "活跃蓄水用户转大率",
                current_value=None,
                last_year_value=None,
            ),
        ]

        checks = validate_pack(pack_with_rows("reservoir", rows))

        self.assertTrue(
            any(
                item.check_id == "formula_conversion"
                and item.status == "failed"
                and item.actual is None
                for item in checks
            )
        )
        self.assertTrue(
            any(
                item.check_id == "formula_unverifiable"
                and item.status == "warning"
                for item in checks
            )
        )

    def test_required_base_none_and_non_finite_values_fail(self):
        rows = [
            row("营收", current_value=None, last_year_value=80),
            row("订单量", current_value=inf, last_year_value=1),
        ]

        failures = [
            item
            for item in validate_pack(pack_with_rows("overview", rows))
            if item.check_id == "numeric_value" and item.status == "failed"
        ]

        self.assertEqual({item.actual for item in failures}, {"None", "inf"})

    def test_product_structure_reports_unverifiable_formulas(self):
        rows = [
            row(
                metric,
                dimension_type="商品",
                dimension_value="组合品",
                current_value=value,
                last_year_value=value,
            )
            for metric, value in (
                ("订单量", 2),
                ("付费人数", 2),
                ("营收", 200),
                ("订单占比", 0.5),
                ("付费人数占比", 0.5),
                ("营收占比", 0.5),
                ("转化率", 0.2),
                ("客单价", 100),
                ("ARPU", 20),
            )
        ]

        checks = validate_pack(pack_with_rows("product_structure", rows))

        self.assertTrue(
            any(
                item.check_id == "formula_aov" and item.status == "passed"
                for item in checks
            )
        )
        unverifiable = [
            item
            for item in checks
            if item.check_id == "formula_unverifiable" and item.status == "warning"
        ]
        self.assertTrue(unverifiable)
        self.assertTrue(any("转化率" in item.message for item in unverifiable))

    def test_product_sql_normalize_validate_uses_active_payers_for_conversion(self):
        request = ReviewRequest.create("匿名活动", "2026-07-01", "2026-07-15", 1000)
        sql = render_sql(Path("queries/review_pack/product_structure.sql"), request)
        self.assertIn("'活跃付费人数'", sql)
        self.assertIn("'活跃人数'", sql)

        raw_rows = []
        for period, values in (
            (
                "本期",
                {"付费人数": 12, "活跃付费人数": 4, "活跃人数": 10, "转化率": 0.8},
            ),
            (
                "去年同期",
                {"付费人数": 8, "活跃付费人数": 3, "活跃人数": 10, "转化率": 0.3},
            ),
        ):
            for metric, value in values.items():
                raw_rows.append(
                    {
                        "period": period,
                        "channel": "APP",
                        "dimension_type": "商品",
                        "dimension_value": "组合品",
                        "metric": metric,
                        "value": value,
                        "source_version": "v1",
                        "data_updated_at": datetime(2026, 7, 16, 9, 0),
                        "definition_id": "product.active-cohort.v1",
                    }
                )

        paired = pair_periods(raw_rows, request)
        checks = validate_pack(pack_with_rows("product_structure", paired))
        conversion = [
            item
            for item in checks
            if item.check_id == "formula_conversion" and item.status == "failed"
        ]

        self.assertEqual(len(conversion), 1)
        self.assertEqual(conversion[0].actual, 0.8)
        self.assertEqual(conversion[0].expected, 0.4)

    def test_user_layer_unknown_uses_query_dimension_name(self):
        unknown = row(
            "活跃人数",
            dimension_type="用户层级",
            dimension_value="未映射",
            current_value=1,
            last_year_value=0,
        )

        failed = {
            item.check_id
            for item in validate_pack(pack_with_rows("user_stage", [unknown]))
            if item.status == "failed"
        }

        self.assertIn("user_unknown", failed)

    def test_stage_unknown_uses_query_bucket_name(self):
        unknown = row(
            "活跃人数",
            dimension_type="学段",
            dimension_value="未知学段",
            current_value=1,
            last_year_value=0,
        )

        checks = validate_pack(pack_with_rows("user_stage", [unknown]))

        self.assertFalse(
            any(item.check_id == "stage_unknown" and item.status == "failed" for item in checks)
        )
        coverage = [
            item for item in checks if item.check_id == "stage_unknown_coverage"
        ]
        self.assertEqual(len(coverage), 1)
        self.assertEqual(coverage[0].status, "warning")
        self.assertIn("识别覆盖率", coverage[0].message)

    def test_stage_unknown_coverage_is_one_warning_per_channel_dimension(self):
        rows = [
            row(
                metric,
                channel="销售",
                dimension_type="学段",
                dimension_value=dimension_value,
                current_value=current,
                last_year_value=last_year,
            )
            for metric, dimension_value, current, last_year in (
                ("活跃人数", "未知学段", 20, 10),
                ("活跃人数", "高中", 80, 90),
                ("营收", "未知学段", 200, 100),
                ("营收", "高中", 800, 900),
            )
        ]

        checks = validate_pack(pack_with_rows("user_stage", rows))

        coverage = [
            item for item in checks if item.check_id == "stage_unknown_coverage"
        ]
        self.assertEqual(len(coverage), 1)
        self.assertEqual(coverage[0].status, "warning")
        self.assertIn("本期 80.00%", coverage[0].message)
        self.assertIn("去年同期 90.00%", coverage[0].message)

    def test_stage_coverage_finds_unknown_component_in_combined_dimensions(self):
        result = pack_with_rows(
            "user_stage",
            [
                row(
                    "活跃人数",
                    channel="APP",
                    dimension_type="用户层级×学段",
                    dimension_value="新增×未知学段",
                    current_value=20,
                    last_year_value=10,
                ),
                row(
                    "活跃人数",
                    channel="APP",
                    dimension_type="用户层级×学段",
                    dimension_value="新增×高中",
                    current_value=80,
                    last_year_value=90,
                ),
            ],
        )
        result.modules["product_structure"] = ModuleResult(
            module="product_structure",
            status="success",
            rows=[
                row(
                    "活跃人数",
                    channel="APP",
                    dimension_type="学段×商品",
                    dimension_value="未知学段×组合品",
                    current_value=20,
                    last_year_value=10,
                ),
                row(
                    "活跃人数",
                    channel="APP",
                    dimension_type="学段×商品",
                    dimension_value="高中×组合品",
                    current_value=80,
                    last_year_value=90,
                ),
            ],
        )

        warnings = [
            item
            for item in validate_pack(result)
            if item.check_id == "stage_unknown_coverage"
        ]

        self.assertEqual(
            {item.message.split("保留未知桶")[0] for item in warnings},
            {"APP用户层级×学段", "APP学段×商品"},
        )

    def test_high_value_stage_coverage_uses_source_population_denominator(self):
        rows = []
        for metric, unknown, known in (
            ("来源用户数", 20, 80),
            ("活跃人数", 5, 5),
        ):
            rows.extend(
                [
                    row(
                        metric,
                        channel="销售",
                        dimension_type="学段",
                        dimension_value="未知学段",
                        current_value=unknown,
                        last_year_value=unknown,
                    ),
                    row(
                        metric,
                        channel="销售",
                        dimension_type="学段",
                        dimension_value="高中",
                        current_value=known,
                        last_year_value=known,
                    ),
                ]
            )

        checks = validate_pack(pack_with_rows("high_value", rows))
        warning = next(
            item for item in checks if item.check_id == "stage_unknown_coverage"
        )

        self.assertIn("分母口径：来源用户数", warning.message)
        self.assertIn("本期 80.00%", warning.message)


if __name__ == "__main__":
    unittest.main()
