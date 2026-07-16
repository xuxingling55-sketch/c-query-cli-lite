from datetime import datetime
import unittest

import pandas as pd

from review_pack.models import ReviewRequest
from review_pack.normalize import pair_periods


def request():
    return ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")


def row(period, value, **overrides):
    result = {
        "period": period,
        "channel": "APP",
        "dimension_type": "总览",
        "dimension_value": "全部",
        "metric": "营收",
        "value": value,
        "source_version": "v1",
        "data_updated_at": datetime(2026, 7, 16, 9, 30),
        "definition_id": "revenue-paid-order-v1",
    }
    result.update(overrides)
    return result


class PairPeriodsTest(unittest.TestCase):
    def test_preserves_numbers_and_adds_comparison_metadata(self):
        paired = pair_periods(
            [row("本期", 120.0), row("去年同期", 100.0)],
            request(),
        )

        self.assertEqual(len(paired), 1)
        self.assertEqual(paired[0]["current_value"], 120.0)
        self.assertEqual(paired[0]["last_year_value"], 100.0)
        self.assertEqual(paired[0]["absolute_change"], 20.0)
        self.assertAlmostEqual(paired[0]["relative_change"], 0.2)
        self.assertEqual(paired[0]["current_date_range"], "2026-07-01/2026-07-15")
        self.assertEqual(
            paired[0]["last_year_date_range"], "2025-07-01/2025-07-15"
        )
        self.assertEqual(paired[0]["period_status"], "complete")
        self.assertEqual(paired[0]["definition_id"], "revenue-paid-order-v1")
        self.assertEqual(paired[0]["data_updated_at"], datetime(2026, 7, 16, 9, 30))

    def test_zero_baseline_has_no_relative_change(self):
        paired = pair_periods([row("本期", 10), row("去年同期", 0)], request())

        self.assertEqual(paired[0]["absolute_change"], 10)
        self.assertIsNone(paired[0]["relative_change"])

    def test_duplicate_period_for_same_key_is_rejected(self):
        duplicate = [row("本期", 10), row("本期", 11)]

        with self.assertRaisesRegex(ValueError, "重复周期数据"):
            pair_periods(duplicate, request())

    def test_missing_counterpart_is_explicit(self):
        paired = pair_periods(
            [
                row("本期", 10, metric="营收"),
                row("去年同期", 3, metric="订单量"),
            ],
            request(),
        )

        by_metric = {item["metric"]: item for item in paired}
        self.assertEqual(by_metric["营收"]["period_status"], "missing_last_year")
        self.assertEqual(by_metric["营收"]["current_value"], 10)
        self.assertIsNone(by_metric["营收"]["last_year_value"])
        self.assertIsNone(by_metric["营收"]["absolute_change"])
        self.assertIsNone(by_metric["营收"]["relative_change"])
        self.assertEqual(by_metric["订单量"]["period_status"], "missing_current")
        self.assertIsNone(by_metric["订单量"]["current_value"])
        self.assertEqual(by_metric["订单量"]["last_year_value"], 3)

    def test_source_version_is_part_of_pairing_key(self):
        paired = pair_periods(
            [
                row("本期", 10, source_version="v1"),
                row("去年同期", 8, source_version="v2"),
            ],
            request(),
        )

        self.assertEqual(len(paired), 2)
        self.assertEqual(
            {item["period_status"] for item in paired},
            {"missing_current", "missing_last_year"},
        )

    def test_definition_id_is_part_of_pairing_key(self):
        paired = pair_periods(
            [
                row("本期", 10, definition_id="old"),
                row("去年同期", 8, definition_id="new"),
            ],
            request(),
        )

        self.assertEqual(len(paired), 2)
        self.assertEqual(
            {item["period_status"] for item in paired},
            {"missing_current", "missing_last_year"},
        )

    def test_non_finite_values_never_produce_non_finite_changes(self):
        cases = (
            (float("inf"), 1),
            (1, float("-inf")),
            (float("inf"), float("inf")),
        )

        for current, last_year in cases:
            with self.subTest(current=current, last_year=last_year):
                paired = pair_periods(
                    [row("本期", current), row("去年同期", last_year)],
                    request(),
                )[0]

                if current in (float("inf"), float("-inf")):
                    self.assertIsNone(paired["current_value"])
                if last_year in (float("inf"), float("-inf")):
                    self.assertIsNone(paired["last_year_value"])
                self.assertIsNone(paired["absolute_change"])
                self.assertIsNone(paired["relative_change"])

    def test_converts_pandas_nan_to_none_without_losing_source_metadata(self):
        paired = pair_periods(
            [
                row(
                    "本期",
                    pd.NA,
                    data_updated_at=pd.NaT,
                    dimension_value=float("nan"),
                ),
                row(
                    "去年同期",
                    8,
                    data_updated_at=datetime(2026, 7, 16, 8, 0),
                    dimension_value=pd.NA,
                ),
            ],
            request(),
        )

        self.assertEqual(len(paired), 1)
        self.assertIsNone(paired[0]["dimension_value"])
        self.assertIsNone(paired[0]["current_value"])
        self.assertEqual(paired[0]["last_year_value"], 8)
        self.assertEqual(paired[0]["data_updated_at"], datetime(2026, 7, 16, 8, 0))


if __name__ == "__main__":
    unittest.main()
