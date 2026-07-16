from pathlib import Path
import re
import unittest


SKILL_PATH = Path(".agents/skills/review-data-pack/SKILL.md")
OPENAI_YAML_PATH = Path(".agents/skills/review-data-pack/agents/openai.yaml")


class ReviewDataPackSkillContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SKILL_PATH.read_text(encoding="utf-8")

    def test_skill_uses_stable_command_and_returns_lark_link(self):
        for value in (
            "生成复盘数据包",
            "一次取齐复盘指标",
            "跑活动复盘数据",
            "scripts/review_data_pack.py",
            "--name",
            "--start",
            "--end",
            "--target",
            "飞书链接",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.text)

    def test_collects_only_the_four_missing_required_inputs(self):
        for value in ("活动名称", "开始日期", "截止日期", "活动目标"):
            with self.subTest(value=value):
                self.assertIn(value, self.text)
        self.assertIn("只询问缺失项", self.text)
        self.assertIn("不得索取策略来源期", self.text)

    def test_preflights_lark_and_distinguishes_preview_from_formal_run(self):
        for value in (
            "command -v lark-cli",
            "lark-cli auth status --json --verify",
            "--sample --dry-run",
            "示例数据",
            "正式模式",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.text)

    def test_reports_date_ranges_and_concise_formal_result(self):
        for value in (
            "活动期",
            "同比期",
            "检查摘要",
            "失败模块",
            "只汇报",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.text)

    def test_formal_output_contract_has_one_template_with_exactly_three_fields(self):
        result_contract = self.text.split("## 结果合同", 1)[1].split(
            "## 快速检查", 1
        )[0]
        self.assertIn("### 正式模式", result_contract)
        self.assertIn("### 预演模式", result_contract)
        formal = result_contract.split("### 正式模式", 1)[1].split(
            "### 预演模式", 1
        )[0]

        templates = re.findall(r"```text\n(.*?)\n```", formal, flags=re.DOTALL)
        self.assertEqual(len(templates), 1)
        lines = [line.strip() for line in templates[0].splitlines() if line.strip()]
        self.assertEqual(
            [line.split("：", 1)[0] for line in lines],
            ["飞书链接", "检查摘要", "失败模块"],
        )
        self.assertIn("未生成", lines[0])
        self.assertIn("错误类型", lines[2])
        self.assertIn("恢复建议", lines[2])
        self.assertIn("无论成功或失败", formal)
        self.assertIn("只汇报且必须恰好汇报以下三项", formal)
        self.assertIn("不得增加第四项", formal)
        self.assertIn("回读失败但 `lark_url` 已返回", formal)
        self.assertIn("不得重跑创建", formal)

    def test_formal_contract_has_no_conflicting_extra_output_instructions(self):
        for phrase in (
            "正式模式成功时",
            "正式成功",
            "其他模块仍按实际状态汇报",
            "正式模式若失败",
            "简要说明错误类型和可恢复信息",
        ):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, self.text)

    def test_forbids_sql_and_existing_document_changes(self):
        self.assertIn("不得生成或改写 SQL", self.text)
        self.assertIn("不得修改现有文档", self.text)

    def test_unknown_campaign_never_turns_sample_data_into_real_results(self):
        for value in (
            "配置缺失",
            "不适用",
            "不得把示例数据表述为真实结果",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.text)

    def test_openai_interface_metadata_is_present(self):
        text = OPENAI_YAML_PATH.read_text(encoding="utf-8")
        self.assertIn('display_name: "生成复盘数据包"', text)
        self.assertIn("$review-data-pack", text)


if __name__ == "__main__":
    unittest.main()
