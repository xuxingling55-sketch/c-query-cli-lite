from datetime import datetime
from decimal import Decimal
from pathlib import Path
import json
import tempfile
import unittest

from review_pack.catalog import SHEET_ORDER
from review_pack.lark_writer import (
    LarkWorkbookWriter,
    _sentinel_matches,
    _workbook_payload,
)
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
            if "--sheet-name" in argv:
                return _targeted_readback(expected_payload, argv)
            return {"ok": True, "data": _full_readback(expected_payload)}
        raise AssertionError(argv)

    return fake


def _column_letter(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _full_readback(payload, *, truncate=False):
    copied = json.loads(json.dumps(payload))
    for sheet in copied["sheets"]:
        last_column = _column_letter(len(sheet["columns"]))
        sheet["range"] = f"A1:{last_column}{len(sheet['data']) + 1}"
        if truncate and len(sheet["data"]) > 2:
            sheet["data"] = sheet["data"][:2] + [sheet["data"][2][:3]]
    return copied


def _targeted_readback(payload, argv):
    name = argv[argv.index("--sheet-name") + 1]
    requested_range = argv[argv.index("--range") + 1]
    sheet = next(sheet for sheet in payload["sheets"] if sheet["name"] == name)
    row_number = int(requested_range.split(":", 1)[0][1:])
    return {
        "ok": True,
        "data": {
            "sheets": [
                {
                    "name": name,
                    "columns": [f"col{index}" for index in range(1, len(sheet["columns"]) + 1)],
                    "data": [sheet["data"][row_number - 2]],
                    "range": requested_range,
                }
            ]
        },
    }


def _result_with_sample_rows() -> ReviewPackResult:
    result = sample_result()
    for module_name in ("overview", "user_stage", "sales_funnel"):
        original = result.modules[module_name].rows[0]
        result.modules[module_name].rows = [
            {**original, "dimension_value": f"样本{index}", "current_value": index}
            for index in range(1, 6)
        ]
    result.checks = [
        CheckResult(f"check-{index}", "info", "passed", "overview", f"检查{index}")
        for index in range(1, 6)
    ]
    return result


class LarkWorkbookWriterTest(unittest.TestCase):
    def test_numeric_sentinel_never_treats_bool_as_number(self):
        sheet = {"columns": ["value"], "dtypes": {"value": "int64"}}

        self.assertFalse(_sentinel_matches(sheet, [1], [True]))
        self.assertFalse(_sentinel_matches(sheet, [True], [1]))

    def test_large_integer_and_integral_decimal_changes_are_exact(self):
        int_sheet = {"columns": ["value"], "dtypes": {"value": "int64"}}
        decimal_sheet = {"columns": ["value"], "dtypes": {"value": "float64"}}

        self.assertFalse(
            _sentinel_matches(int_sheet, [10**12], [10**12 + 1])
        )
        self.assertFalse(
            _sentinel_matches(
                decimal_sheet,
                [Decimal("1000000000000")],
                [Decimal("1000000000001")],
            )
        )

    def test_long_integer_text_must_be_exactly_numerically_equal(self):
        sheet = {"columns": ["value"], "dtypes": {"value": "object"}}

        self.assertTrue(
            _sentinel_matches(
                sheet,
                [123456789012345678901234567890],
                ["123456789012345678901234567890"],
            )
        )
        self.assertFalse(
            _sentinel_matches(
                sheet,
                [123456789012345678901234567890],
                ["123456789012345678901234567891"],
            )
        )

    def test_float_tolerance_is_fixed_not_relative_to_value_size(self):
        sheet = {"columns": ["value"], "dtypes": {"value": "float64"}}

        self.assertTrue(_sentinel_matches(sheet, [0.25], [0.2500000000000004]))
        self.assertFalse(
            _sentinel_matches(sheet, [1_000_000_000_000.0], [1_000_000_000_001.0])
        )

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
            if "+table-get" in argv and "--sheet-name" in argv:
                response["data"]["sheets"][0]["data"][0][0] = "被改写"
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
            if "+table-get" in argv and "--sheet-name" in argv:
                for sheet in response["data"]["sheets"]:
                    name = argv[argv.index("--sheet-name") + 1]
                    payload = json.loads(
                        next(stdin for call, stdin in calls if "+workbook-create" in call)
                    )
                    expected = next(item for item in payload["sheets"] if item["name"] == name)
                    date_columns = {
                        index for index, column in enumerate(expected["columns"])
                        if expected["dtypes"].get(column) == "datetime64[ns]"
                    }
                    for row in sheet["data"]:
                        for index in date_columns:
                            if row[index] is not None:
                                row[index] = row[index][:10]
            return response

        self.assertEqual(LarkWorkbookWriter(fake).write(sample_result()), URL)

    def test_snapshot_iso_datetime_string_matches_readback_date_for_updated_at(self):
        calls = []
        base = successful_runner(calls)
        result = sample_result()
        for module in result.modules.values():
            for row in module.rows:
                row["data_updated_at"] = "2026-07-16T19:12:49"

        def fake(argv, stdin=None):
            response = base(argv, stdin)
            if "+table-get" in argv and "--sheet-name" in argv:
                name = argv[argv.index("--sheet-name") + 1]
                if name in {"经营总览", "用户分层", "销售承接"}:
                    response["data"]["sheets"][0]["data"][0][12] = "2026-07-16"
            return response

        self.assertEqual(LarkWorkbookWriter(fake).write(result), URL)

    def test_object_columns_accept_lark_string_form_of_written_numeric_values(self):
        calls = []
        base = successful_runner(calls)

        def fake(argv, stdin=None):
            response = base(argv, stdin)
            if "+table-get" in argv and "--sheet-name" in argv:
                name = argv[argv.index("--sheet-name") + 1]
                if name == "检查结果":
                    payload = json.loads(
                        next(value for call, value in calls if "+workbook-create" in call)
                    )
                    expected = next(
                        sheet for sheet in payload["sheets"] if sheet["name"] == name
                    )
                    row_number = int(argv[argv.index("--range") + 1].split(":")[0][1:])
                    expected_value = expected["data"][row_number - 2][5]
                    if expected_value is not None:
                        response["data"]["sheets"][0]["data"][0][5] = str(expected_value)
            return response

        result = sample_result()
        result.checks[0] = CheckResult(
            "passed", "info", "passed", "overview", "模块成功", actual=59749.0
        )
        result.checks[1] = CheckResult(
            "warning", "warning", "warning", "user_stage", "需要关注", actual="未知"
        )

        self.assertEqual(LarkWorkbookWriter(fake).write(result), URL)

    def test_iso_z_datetime_matches_same_readback_date(self):
        calls = []
        base = successful_runner(calls)

        def fake(argv, stdin=None):
            response = base(argv, stdin)
            if "+table-get" in argv and "--sheet-name" in argv:
                name = argv[argv.index("--sheet-name") + 1]
                if name == "经营总览":
                    sheet = response["data"]["sheets"][0]
                    sheet["data"][0][12] = "2026-07-16T23:59:59Z"
            return response

        self.assertEqual(LarkWorkbookWriter(fake).write(sample_result()), URL)

    def test_float_round_trip_noise_does_not_fail_readback(self):
        calls = []
        base = successful_runner(calls)

        def fake(argv, stdin=None):
            response = base(argv, stdin)
            if "+table-get" in argv and "--sheet-name" in argv:
                if argv[argv.index("--sheet-name") + 1] == "经营总览":
                    response["data"]["sheets"][0]["data"][0][7] = 0.2500000000000004
            return response

        self.assertEqual(LarkWorkbookWriter(fake).write(sample_result()), URL)

    def test_material_numeric_change_still_fails_readback(self):
        calls = []
        base = successful_runner(calls)

        def fake(argv, stdin=None):
            response = base(argv, stdin)
            if "+table-get" in argv and "--sheet-name" in argv:
                if argv[argv.index("--sheet-name") + 1] == "经营总览":
                    response["data"]["sheets"][0]["data"][0][7] = 0.251
            return response

        with self.assertRaisesRegex(RuntimeError, "回读验证失败"):
            LarkWorkbookWriter(fake).write(sample_result())

    def test_invalid_datetime_suffix_fails_readback(self):
        calls = []
        base = successful_runner(calls)

        def fake(argv, stdin=None):
            response = base(argv, stdin)
            if "+table-get" in argv and "--sheet-name" in argv:
                name = argv[argv.index("--sheet-name") + 1]
                if name == "经营总览":
                    sheet = response["data"]["sheets"][0]
                    sheet["data"][0][12] = "2026-07-16-invalid"
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

    def test_truncated_full_readback_uses_ranges_then_checks_first_middle_last_rows(self):
        result = _result_with_sample_rows()
        payload = _workbook_payload(result)
        calls = []

        def fake(argv, stdin=None):
            calls.append((argv, stdin))
            if "+table-get" in argv and "--sheet-name" not in argv:
                return {"ok": True, "data": _full_readback(payload, truncate=True)}
            if "+table-get" in argv:
                return _targeted_readback(payload, argv)
            raise AssertionError(argv)

        self.assertEqual(LarkWorkbookWriter(fake).verify(URL, result), URL)
        targeted = [argv for argv, _ in calls if "--sheet-name" in argv]
        by_sheet = {}
        for argv in targeted:
            by_sheet.setdefault(argv[argv.index("--sheet-name") + 1], []).append(
                argv[argv.index("--range") + 1]
            )
            self.assertIn("--no-header", argv)
            self.assertEqual(argv[-4:], ["--as", "user", "--format", "json"])
        self.assertEqual(set(by_sheet), {"检查结果", "经营总览", "用户分层", "销售承接"})
        self.assertEqual(by_sheet["检查结果"], ["A2:H2", "A4:H4", "A6:H6"])
        self.assertEqual(by_sheet["经营总览"], ["A2:N2", "A4:N4", "A6:N6"])

    def test_verify_rejects_wrong_used_range_even_when_prefix_data_looks_valid(self):
        result = sample_result()
        payload = _workbook_payload(result)
        readback = _full_readback(payload)
        readback["sheets"][1]["range"] = "A1:N99"

        def fake(argv, stdin=None):
            return {"ok": True, "data": readback}

        with self.assertRaisesRegex(RuntimeError, "回读验证失败"):
            LarkWorkbookWriter(fake).verify(URL, payload)

    def test_verify_rejects_missing_targeted_middle_or_last_row(self):
        result = _result_with_sample_rows()
        payload = _workbook_payload(result)

        for missing_range in ("A4:N4", "A6:N6"):
            with self.subTest(missing_range=missing_range):
                def fake(argv, stdin=None):
                    if "--sheet-name" not in argv:
                        return {
                            "ok": True,
                            "data": _full_readback(payload, truncate=True),
                        }
                    response = _targeted_readback(payload, argv)
                    if argv[argv.index("--sheet-name") + 1] == "用户分层" and argv[
                        argv.index("--range") + 1
                    ] == missing_range:
                        response["data"]["sheets"][0]["data"] = []
                    return response

                with self.assertRaisesRegex(RuntimeError, "回读验证失败"):
                    LarkWorkbookWriter(fake).verify(URL, payload)

    def test_verify_rejects_wrong_targeted_range(self):
        result = sample_result()
        payload = _workbook_payload(result)

        def fake(argv, stdin=None):
            if "--sheet-name" not in argv:
                return {"ok": True, "data": _full_readback(payload)}
            response = _targeted_readback(payload, argv)
            response["data"]["sheets"][0]["range"] = "A3:H3"
            return response

        with self.assertRaisesRegex(RuntimeError, "回读验证失败"):
            LarkWorkbookWriter(fake).verify(URL, payload)

    def test_verify_handles_aa_columns_in_used_and_targeted_ranges(self):
        result = sample_result()
        result.modules["overview"].rows[0].update(
            {f"extra_{index}": index for index in range(1, 14)}
        )
        payload = _workbook_payload(result)
        calls = []

        def fake(argv, stdin=None):
            calls.append((argv, stdin))
            if "--sheet-name" not in argv:
                return {"ok": True, "data": _full_readback(payload)}
            return _targeted_readback(payload, argv)

        self.assertEqual(LarkWorkbookWriter(fake).verify(URL, payload), URL)
        overview = next(
            argv for argv, _ in calls
            if "--sheet-name" in argv and argv[argv.index("--sheet-name") + 1] == "经营总览"
        )
        self.assertEqual(overview[overview.index("--range") + 1], "A2:AA2")

    def test_verify_rejects_failed_targeted_call(self):
        result = sample_result()
        payload = _workbook_payload(result)

        def fake(argv, stdin=None):
            if "--sheet-name" not in argv:
                return {"ok": True, "data": _full_readback(payload)}
            return {"ok": False, "error": {"message": "secret"}}

        with self.assertRaisesRegex(RuntimeError, "回读验证失败") as caught:
            LarkWorkbookWriter(fake).verify(URL, payload)
        self.assertNotIn("secret", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
