from datetime import datetime
from pathlib import Path
import json
import tempfile
import unittest

from review_pack.catalog import SHEET_ORDER
from review_pack.lark_writer import LarkWorkbookWriter
from review_pack.models import CheckResult, ModuleResult, ReviewPackResult, ReviewRequest


URL = "https://example.feishu.cn/sheets/test"


def auth_status(identity="user", **user_overrides):
    user = {
        "verified": True,
        "available": True,
        "status": "ready",
        "tokenStatus": "valid",
    }
    user.update(user_overrides)
    return {"verified": True, "identity": identity, "identities": {"user": user}}


def sample_result(snapshot: str = "") -> ReviewPackResult:
    common = {
        "channel": "私域整体",
        "current_value": 100,
        "last_year_value": 80,
        "absolute_change": 20,
        "relative_change": 0.25,
        "period_status": "complete",
        "current_date_range": "2026-07-01/2026-07-15",
        "last_year_date_range": "2025-07-01/2025-07-15",
        "source_version": "v1",
        "data_updated_at": datetime(2026, 7, 16, 9, 30),
        "definition_id": "revenue-v1",
    }
    result = ReviewPackResult(
        request=ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿"),
        modules={
            "overview": ModuleResult(
                "overview",
                "success",
                [{**common, "dimension_type": "总览", "dimension_value": "全部", "metric": "营收"}],
            ),
            "user_stage": ModuleResult(
                "user_stage",
                "success",
                [
                    {**common, "dimension_type": "用户层级", "dimension_value": "新增", "metric": "活跃人数"},
                    {**common, "dimension_type": "学段", "dimension_value": "初中", "metric": "活跃人数"},
                ],
            ),
            "sales_funnel": ModuleResult(
                "sales_funnel",
                "success",
                [{**common, "dimension_type": "销售", "dimension_value": "全部", "metric": "转化营收"}],
            ),
        },
        checks=[
            CheckResult("passed", "info", "passed", "overview", "模块成功"),
            CheckResult("warning", "warning", "warning", "user_stage", "需要关注"),
            CheckResult("failed", "error", "failed", "sales_funnel", "检查失败"),
        ],
        local_snapshot=snapshot,
    )
    return result


def successful_runner(calls: list[tuple[list[str], str | None]]):
    expected_payload = None

    def fake(argv, stdin=None):
        nonlocal expected_payload
        calls.append((argv, stdin))
        if argv[1:3] == ["auth", "status"]:
            return auth_status()
        if "+workbook-create" in argv:
            expected_payload = json.loads(stdin)
            return {"ok": True, "data": {"spreadsheet": {"url": URL}}}
        if "+table-get" in argv:
            return {"ok": True, "data": expected_payload}
        raise AssertionError(argv)

    return fake


class LarkWorkbookWriterTest(unittest.TestCase):
    def test_create_uses_fixed_sheet_order_typed_payload_and_readback(self):
        calls = []
        result = sample_result()

        url = LarkWorkbookWriter(successful_runner(calls)).write(result)

        self.assertEqual(url, URL)
        self.assertEqual(result.lark_url, URL)
        create_argv, create_stdin = next(
            call for call in calls if "+workbook-create" in call[0]
        )
        self.assertIsInstance(create_argv, list)
        self.assertEqual(
            create_argv,
            [
                "lark-cli",
                "sheets",
                "+workbook-create",
                "--title",
                "暑促_复盘数据包_2026-07-01_2026-07-15",
                "--sheets",
                "-",
                "--styles",
                create_argv[create_argv.index("--styles") + 1],
                "--as",
                "user",
                "--format",
                "json",
            ],
        )
        payload = json.loads(create_stdin)
        styles = json.loads(create_argv[create_argv.index("--styles") + 1])
        self.assertEqual([sheet["name"] for sheet in payload["sheets"]], list(SHEET_ORDER))
        self.assertEqual([style["name"] for style in styles["styles"]], list(SHEET_ORDER))
        by_name = {sheet["name"]: sheet for sheet in payload["sheets"]}
        styles_by_name = {style["name"]: style for style in styles["styles"]}
        self.assertEqual(by_name["用户分层"]["data"][0][2], "新增")
        self.assertEqual(by_name["学段表现"]["data"][0][2], "初中")
        self.assertEqual(by_name["检查结果"]["data"][0][2], "failed")
        self.assertEqual(by_name["检查结果"]["data"][1][2], "warning")
        self.assertEqual(by_name["经营总览"]["dtypes"]["current_value"], "int64")
        self.assertEqual(by_name["经营总览"]["formats"]["current_value"], "#,##0")
        self.assertEqual(by_name["经营总览"]["formats"]["relative_change"], "0.00%")
        self.assertEqual(by_name["运行记录"]["formats"]["target_amount"], "#,##0.00")
        overview_formats = {
            style["range"]: style["number_format"]
            for style in styles_by_name["经营总览"]["cell_styles"]
            if "number_format" in style
        }
        self.assertEqual(overview_formats["E2:G2"], "#,##0.00")
        read_argv, read_stdin = next(call for call in calls if "+table-get" in call[0])
        self.assertEqual(
            read_argv,
            [
                "lark-cli", "sheets", "+table-get", "--url", URL,
                "--as", "user", "--format", "json",
            ],
        )
        self.assertIsNone(read_stdin)

    def test_missing_readback_keeps_snapshot_and_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "review_pack.json"
            snapshot.write_text('{"kept": true}\n', encoding="utf-8")
            result = sample_result(str(snapshot))

            def fake(argv, stdin=None):
                if argv[1:3] == ["auth", "status"]:
                    return auth_status()
                if "+workbook-create" in argv:
                    return {"ok": True, "data": {"spreadsheet": {"url": URL}}}
                return {"ok": True, "data": {"sheets": []}}

            with self.assertRaisesRegex(RuntimeError, "回读验证失败"):
                LarkWorkbookWriter(fake).write(result)

            self.assertTrue(snapshot.is_file())
            self.assertEqual(result.local_snapshot, str(snapshot))
            self.assertEqual(result.lark_url, "")

    def test_readback_detects_row_count_and_sentinel_changes(self):
        calls = []
        base = successful_runner(calls)

        def fake(argv, stdin=None):
            response = base(argv, stdin)
            if "+table-get" in argv:
                response["data"]["sheets"][1]["data"][0][0] = "被改写"
            return response

        with self.assertRaisesRegex(RuntimeError, "回读验证失败"):
            LarkWorkbookWriter(fake).write(sample_result())

    def test_auth_must_be_verified_user_before_create(self):
        invalid_statuses = (
            {"identity": "user", "identities": {}},
            auth_status(verified=False),
            auth_status(available=False),
            auth_status(status="expired"),
            auth_status(tokenStatus="invalid"),
        )
        for status in invalid_statuses:
            with self.subTest(status=status):
                calls = []

                def fake(argv, stdin=None):
                    calls.append((argv, stdin))
                    return status

                with self.assertRaisesRegex(RuntimeError, "飞书用户认证不可用"):
                    LarkWorkbookWriter(fake).write(sample_result())

                self.assertFalse(any("+workbook-create" in argv for argv, _ in calls))

    def test_bot_default_with_verified_user_token_is_allowed(self):
        calls = []
        base = successful_runner(calls)

        def fake(argv, stdin=None):
            if argv[1:3] == ["auth", "status"]:
                calls.append((argv, stdin))
                return auth_status(identity="bot", status="active")
            return base(argv, stdin)

        self.assertEqual(LarkWorkbookWriter(fake).write(sample_result()), URL)

    def test_date_only_table_get_values_match_written_datetimes(self):
        calls = []
        base = successful_runner(calls)

        def fake(argv, stdin=None):
            response = base(argv, stdin)
            if "+table-get" in argv:
                for sheet in response["data"]["sheets"]:
                    date_columns = {
                        index
                        for index, column in enumerate(sheet["columns"])
                        if sheet["dtypes"].get(column) == "datetime64[ns]"
                    }
                    for row in sheet["data"]:
                        for index in date_columns:
                            if row[index] is not None:
                                row[index] = row[index][:10]
            return response

        self.assertEqual(LarkWorkbookWriter(fake).write(sample_result()), URL)

    def test_iso_z_datetime_matches_same_readback_date(self):
        calls = []
        base = successful_runner(calls)

        def fake(argv, stdin=None):
            response = base(argv, stdin)
            if "+table-get" in argv:
                sheet = response["data"]["sheets"][1]
                index = sheet["columns"].index("data_updated_at")
                sheet["data"][0][index] = "2026-07-16T23:59:59Z"
            return response

        self.assertEqual(LarkWorkbookWriter(fake).write(sample_result()), URL)

    def test_invalid_datetime_suffix_fails_readback(self):
        calls = []
        base = successful_runner(calls)

        def fake(argv, stdin=None):
            response = base(argv, stdin)
            if "+table-get" in argv:
                sheet = response["data"]["sheets"][1]
                index = sheet["columns"].index("data_updated_at")
                sheet["data"][0][index] = "2026-07-16-invalid"
            return response

        with self.assertRaisesRegex(RuntimeError, "回读验证失败"):
            LarkWorkbookWriter(fake).write(sample_result())

    def test_percentage_metrics_get_percentage_row_styles(self):
        result = sample_result()
        for metric in ("目标完成率", "付费转化率", "营收占比"):
            row = dict(result.modules["overview"].rows[0])
            row.update(
                metric=metric,
                current_value=0.8,
                last_year_value=0.7,
                absolute_change=0.1,
                relative_change=1 / 7,
            )
            result.modules["overview"].rows.append(row)
        calls = []

        LarkWorkbookWriter(successful_runner(calls)).write(result)

        create_argv = next(argv for argv, _ in calls if "+workbook-create" in argv)
        styles = json.loads(create_argv[create_argv.index("--styles") + 1])
        overview = next(style for style in styles["styles"] if style["name"] == "经营总览")
        row_formats = {
            style["range"]: style["number_format"]
            for style in overview["cell_styles"]
            if "number_format" in style
        }
        for row_number in (3, 4, 5):
            self.assertEqual(row_formats[f"E{row_number}:H{row_number}"], "0.00%")

    def test_create_and_read_commands_require_ok_true_without_leaking_details(self):
        secret = "access_token=very-secret"

        def fake(argv, stdin=None):
            if argv[1:3] == ["auth", "status"]:
                return auth_status()
            return {"ok": False, "error": {"message": secret}}

        with self.assertRaises(RuntimeError) as caught:
            LarkWorkbookWriter(fake).write(sample_result())

        self.assertNotIn(secret, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
