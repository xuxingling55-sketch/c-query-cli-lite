import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from review_pack.catalog import MODULE_SPECS
from review_pack.models import ReviewRequest


def request():
    return ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")


def query_row(value=100):
    return {
        "period": "本期",
        "channel": "私域整体",
        "dimension_type": "总览",
        "dimension_value": "全部",
        "metric": "营收",
        "value": value,
        "source_version": "v1",
        "data_updated_at": None,
        "definition_id": "revenue-paid-order-v1",
    }


class ReviewPackRunnerTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.query_root = self.root / "queries"
        self.output_root = self.root / "outputs"
        self.query_root.mkdir()
        for module in MODULE_SPECS:
            (self.query_root / module.sql_file).write_text(
                "SELECT {{CURRENT_START}} AS paid_time_sk "
                "FROM dws.topic_order_detail "
                "WHERE paid_time_sk = {{CURRENT_START}} LIMIT 10000",
                encoding="utf-8",
            )

    def runner_with(self, fake_query):
        from review_pack.runner import ReviewPackRunner

        return ReviewPackRunner(fake_query, self.query_root, self.output_root)

    def test_runner_is_available_from_package(self):
        from review_pack import ReviewPackRunner, sql_executor_query_runner

        self.assertTrue(callable(ReviewPackRunner))
        self.assertTrue(callable(sql_executor_query_runner))

    def test_one_failure_keeps_other_modules_and_snapshot(self):
        def fake_query(module, sql):
            if module == "sales_funnel":
                raise RuntimeError("sales unavailable")
            return [query_row()]

        result = self.runner_with(fake_query).run(request())

        self.assertEqual(result.modules["sales_funnel"].status, "failed")
        self.assertEqual(result.modules["sales_funnel"].rows, [])
        self.assertIn("sales unavailable", result.modules["sales_funnel"].error)
        self.assertEqual(result.modules["overview"].status, "success")
        snapshot = Path(result.local_snapshot)
        self.assertTrue(snapshot.is_file())
        self.assertEqual(snapshot.name, "review_pack.json")
        saved = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertEqual(saved["modules"]["sales_funnel"]["rows"], [])
        self.assertEqual(saved["modules"]["overview"]["status"], "success")
        self.assertEqual(saved["local_snapshot"], str(snapshot))
        self.assertEqual(list(snapshot.parent.glob("*.tmp")), [])

    def test_missing_optional_window_skips_query_as_not_applicable(self):
        (self.query_root / "deposit.sql").write_text(
            "SELECT {{DEPOSIT_SOURCE_START}} AS paid_time_sk "
            "FROM dws.topic_order_detail "
            "WHERE paid_time_sk = {{CURRENT_START}} LIMIT 10000",
            encoding="utf-8",
        )
        queried_modules = []

        def fake_query(module, sql):
            queried_modules.append(module)
            return [query_row()]

        result = self.runner_with(fake_query).run(request())

        self.assertEqual(result.modules["deposit"].status, "not_applicable")
        self.assertEqual(result.modules["deposit"].rows, [])
        self.assertNotIn("deposit", queried_modules)

    def test_failed_later_run_does_not_reuse_prior_rows(self):
        should_fail = False

        def fake_query(module, sql):
            if module == "overview" and should_fail:
                raise RuntimeError("overview unavailable")
            return [query_row(123)]

        runner = self.runner_with(fake_query)
        first = runner.run(request())
        should_fail = True
        second = runner.run(request())

        self.assertEqual(first.modules["overview"].status, "success")
        self.assertNotEqual(first.modules["overview"].rows, [])
        self.assertEqual(second.modules["overview"].status, "failed")
        self.assertEqual(second.modules["overview"].rows, [])

    def test_sql_executor_adapter_ignores_module_and_returns_records(self):
        from review_pack.runner import sql_executor_query_runner

        class FakeExecutor:
            def __init__(self):
                self.sqls = []

            def execute(self, sql):
                self.sqls.append(sql)
                return pd.DataFrame([query_row(88)]), "StarRocks", 0.1

        executor = FakeExecutor()
        query = sql_executor_query_runner(executor)

        rows = query("overview", "SELECT 88")

        self.assertEqual(executor.sqls, ["SELECT 88"])
        self.assertEqual(rows, [query_row(88)])


if __name__ == "__main__":
    unittest.main()
