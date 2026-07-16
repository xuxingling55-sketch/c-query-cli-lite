import unittest

from review_pack.catalog import (
    MODULE_SPECS,
    SHEET_ORDER,
    campaign_defaults,
    module_spec,
)


class CatalogTest(unittest.TestCase):
    def test_module_and_sheet_order(self):
        self.assertEqual(
            [module.name for module in MODULE_SPECS],
            [
                "overview",
                "active_efficiency",
                "user_stage",
                "product_structure",
                "deposit",
                "reservoir",
                "high_value",
                "sales_funnel",
            ],
        )
        self.assertEqual(SHEET_ORDER[0], "检查结果")
        self.assertEqual(SHEET_ORDER[-1], "运行记录")
        self.assertEqual(len(SHEET_ORDER), 12)

    def test_confirmed_dimensions(self):
        spec = module_spec("user_stage")
        self.assertEqual(spec.channels, ("私域整体", "APP", "销售"))
        self.assertEqual(spec.stages, ("1–3 年级", "4–6 年级", "初中", "高中"))
        self.assertIn("高净值－历史大会员可续购", spec.user_layers)
        self.assertIn("高净值－其他组合品", spec.user_layers)

    def test_summer_campaign_has_strategy_source_windows(self):
        defaults = campaign_defaults("暑促")
        self.assertEqual(defaults["deposit_source"], ["2026-06-24", "2026-06-30"])
        self.assertEqual(defaults["reservoir_source"], ["2026-05-22", "2026-06-30"])


if __name__ == "__main__":
    unittest.main()
