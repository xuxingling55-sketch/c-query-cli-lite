from __future__ import annotations

import json
from pathlib import Path
import unittest


class CEndPrivateMetricsReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = (
            Path(__file__).resolve().parents[1]
            / "independent_reports"
            / "c_end_private_metrics"
        )

    def test_monitor_contract(self) -> None:
        monitor = json.loads((self.root / "monitor.yaml").read_text(encoding="utf-8"))

        self.assertEqual(monitor["id"], "c-end-private-metrics")
        self.assertEqual(monitor["path"], "/c-end-private-metrics/")
        self.assertEqual(
            monitor["auth"],
            {"mode": "login", "project_id": "c-end-private-metrics"},
        )
        self.assertEqual(monitor["runtime"]["type"], "static")
        self.assertFalse(monitor["refresh"]["enabled"])
        self.assertEqual(
            monitor["preview"]["path"],
            "/_preview/c-end-private-metrics/",
        )
        self.assertEqual(
            monitor["preview"]["auth_project_id"],
            "c-end-private-metrics-preview",
        )
        self.assertEqual(monitor["preview"]["data_mode"], "snapshot")

    def test_metric_and_release_docs_cover_required_boundaries(self) -> None:
        metric = (self.root / "docs" / "metric.md").read_text(encoding="utf-8")
        readme = (self.root / "README.md").read_text(encoding="utf-8")

        for term in ("业务日期", "数据粒度", "来源表", "敏感字段", "分母为 0"):
            self.assertIn(term, metric)
        for term in ("生成快照", "Preview", "正式发布", "回滚"):
            self.assertIn(term, readme)


if __name__ == "__main__":
    unittest.main()
