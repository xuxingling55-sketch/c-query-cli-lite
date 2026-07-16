import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from review_pack.catalog import MODULE_SPECS
from review_pack.models import ModuleResult, ReviewPackResult


SCRIPT = Path("scripts/review_data_pack.py")
BASE_ARGS = [
    "--name",
    "暑促",
    "--start",
    "2026-07-01",
    "--end",
    "2026-07-15",
    "--target",
    "1.2亿",
]


class FakeRunner:
    def __init__(self, statuses=None, snapshot=""):
        self.statuses = statuses or {}
        self.snapshot = snapshot

    def run(self, request):
        modules = {
            spec.name: ModuleResult(
                spec.name,
                self.statuses.get(spec.name, "success"),
                rows=[
                    {
                        "period": "本期",
                        "channel": "私域整体",
                        "dimension_type": "总览",
                        "dimension_value": "全部",
                        "metric": spec.metrics[0],
                        "value": 1,
                        "current_value": 1,
                        "last_year_value": 1,
                        "source_version": "v1",
                        "data_updated_at": "2026-07-15",
                        "definition_id": "sample-v1",
                    }
                ],
            )
            for spec in MODULE_SPECS
        }
        for module in modules.values():
            if module.status != "success":
                module.rows = []
                module.error = "test failure"
        return ReviewPackResult(request, modules, local_snapshot=self.snapshot)


def run_main(args, runner, writer_factory=None):
    from review_pack.cli import main

    output = io.StringIO()
    code = main(
        args,
        runner_factory=lambda sample: runner,
        writer_factory=writer_factory,
        stdout=output,
    )
    return code, json.loads(output.getvalue())


class ReviewPackCliTest(unittest.TestCase):
    def setUp(self):
        self.output_root = Path("outputs/review_pack")
        self.existing_outputs = (
            set(self.output_root.iterdir()) if self.output_root.is_dir() else set()
        )

    def tearDown(self):
        if not self.output_root.is_dir():
            return
        for path in set(self.output_root.iterdir()) - self.existing_outputs:
            shutil.rmtree(path)
        if not any(self.output_root.iterdir()):
            self.output_root.rmdir()
            parent = self.output_root.parent
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()

    def test_sample_dry_run_has_no_lark_write(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), *BASE_ARGS, "--sample", "--dry-run"],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["last_year_period"], "2025-07-01~2025-07-15")
        self.assertEqual(payload["check_summary"]["failed"], 0)
        self.assertNotIn("lark_url", payload)

    def test_campaign_defaults_fill_optional_strategy_windows(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), *BASE_ARGS, "--sample", "--dry-run"],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["source_windows"]["deposit"], "2026-06-24~2026-06-30")
        self.assertEqual(payload["source_windows"]["reservoir"], "2026-05-22~2026-06-30")

    def test_unknown_activity_reports_missing_strategy_configuration(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--name",
                "未知活动",
                "--start",
                "2026-07-01",
                "--end",
                "2026-07-15",
                "--target",
                "100万",
                "--sample",
                "--dry-run",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["modules"]["deposit"], "not_applicable")
        self.assertEqual(payload["modules"]["reservoir"], "not_applicable")
        self.assertIn("deposit", payload["failed_modules"])
        self.assertIn("reservoir", payload["failed_modules"])
        messages = " ".join(payload["configuration_errors"])
        self.assertIn("--deposit-source-start", messages)
        self.assertIn("--reservoir-source-start", messages)

    def test_invalid_input_returns_exit_code_2_and_json_error(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--name",
                "暑促",
                "--start",
                "2026-07-15",
                "--end",
                "2026-07-01",
                "--target",
                "1.2亿",
                "--sample",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertFalse(json.loads(completed.stdout)["ok"])

    def test_reversed_strategy_window_returns_json_exit_2(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                *BASE_ARGS,
                "--deposit-source-start",
                "2026-06-30",
                "--deposit-source-end",
                "2026-06-01",
                "--sample",
            ],
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["error_type"], "invalid_input")
        self.assertEqual(completed.stderr, "")

    def test_argument_errors_are_one_json_object_without_usage(self):
        cases = (["--name", "暑促"], [*BASE_ARGS, "--unknown-option"])
        for args in cases:
            with self.subTest(args=args):
                completed = subprocess.run(
                    [sys.executable, str(SCRIPT), *args],
                    capture_output=True,
                    text=True,
                )
                payload = json.loads(completed.stdout)
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(payload["error_type"], "invalid_input")
                self.assertEqual(completed.stdout.count("\n"), 1)
                self.assertEqual(completed.stderr, "")
                self.assertNotIn("usage:", completed.stdout.lower())

    def test_all_modules_failed_returns_3_without_lark_write(self):
        writes = []
        runner = FakeRunner({spec.name: "failed" for spec in MODULE_SPECS})
        code, payload = run_main(
            BASE_ARGS,
            runner,
            writer_factory=lambda: writes.append("constructed"),
        )
        self.assertEqual(code, 3)
        self.assertFalse(payload["ok"])
        self.assertEqual(writes, [])

    def test_dry_run_and_sample_each_skip_lark_writer(self):
        for safety_flag in ("--dry-run", "--sample"):
            with self.subTest(safety_flag=safety_flag):
                writes = []
                code, payload = run_main(
                    [*BASE_ARGS, safety_flag],
                    FakeRunner(),
                    writer_factory=lambda: writes.append("constructed"),
                )
                self.assertEqual(code, 0)
                self.assertTrue(payload["ok"])
                self.assertEqual(writes, [])
                self.assertNotIn("lark_url", payload)

    def test_normal_mode_writes_and_prints_summary(self):
        class Writer:
            def write(self, result):
                return "https://example.feishu.cn/sheets/review"

        code, payload = run_main(
            BASE_ARGS,
            FakeRunner({"sales_funnel": "failed"}),
            writer_factory=Writer,
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["lark_url"], "https://example.feishu.cn/sheets/review")
        self.assertIn("sales_funnel", payload["failed_modules"])
        self.assertIn("check_summary", payload)

    def test_lark_write_or_readback_failure_returns_4(self):
        class Writer:
            def write(self, result):
                raise RuntimeError("回读验证失败")

        code, payload = run_main(BASE_ARGS, FakeRunner(), writer_factory=Writer)
        self.assertEqual(code, 4)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_type"], "lark_write_failed")

    def test_snapshot_failure_after_lark_success_does_not_return_4(self):
        class Writer:
            def write(self, result):
                return "https://example.feishu.cn/sheets/created-once"

        with patch(
            "review_pack.cli._update_snapshot",
            side_effect=(None, OSError("disk full")),
        ):
            code, payload = run_main(BASE_ARGS, FakeRunner(), writer_factory=Writer)

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(
            payload["lark_url"], "https://example.feishu.cn/sheets/created-once"
        )
        self.assertEqual(len(payload["snapshot_warnings"]), 1)

    def test_runner_output_and_exception_details_are_not_exposed(self):
        from contextlib import redirect_stderr, redirect_stdout
        from review_pack.cli import main

        secret = "password=TOP_SECRET"

        class NoisyRunner:
            def run(self, request):
                print(secret)
                print(secret, file=sys.stderr)
                raise RuntimeError(secret)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(
                BASE_ARGS,
                runner_factory=lambda sample: NoisyRunner(),
                stdout=stdout,
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 3)
        self.assertEqual(payload["error_type"], "runner_failed")
        self.assertEqual(stdout.getvalue().count("\n"), 1)
        self.assertNotIn(secret, stdout.getvalue())
        self.assertNotIn(secret, stderr.getvalue())

    def test_validation_is_persisted_back_to_existing_snapshot(self):
        with TemporaryDirectory() as directory:
            snapshot = Path(directory) / "review_pack.json"
            snapshot.write_text("{}\n", encoding="utf-8")
            code, payload = run_main(
                [*BASE_ARGS, "--dry-run"], FakeRunner(snapshot=str(snapshot))
            )
            saved = json.loads(snapshot.read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertEqual(saved["local_snapshot"], payload["local_snapshot"])
        self.assertGreater(len(saved["checks"]), 0)


if __name__ == "__main__":
    unittest.main()
