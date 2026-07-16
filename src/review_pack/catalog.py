"""Fixed module, dimension, metric, and worksheet catalog for review packs."""

from dataclasses import dataclass
import json
from pathlib import Path


STAGES = ("1–3 年级", "4–6 年级", "初中", "高中")
USER_LAYERS = (
    "新增",
    "老未",
    "续费",
    "高净值汇总",
    "高净值－当年毕业",
    "高净值－历史大会员可续购",
    "高净值－历史大会员不可续购",
    "高净值－其他组合品",
)
PRODUCTS = ("组合品", "零售品", "家庭包", "从小学系列", "198", "498", "千元及以上")
SHEET_ORDER = (
    "检查结果",
    "经营总览",
    "活跃效率",
    "用户分层",
    "学段表现",
    "商品结构",
    "定金策略",
    "蓄水策略",
    "高净值策略",
    "销售承接",
    "指标口径",
    "运行记录",
)
LONG_COLUMNS = (
    "period",
    "channel",
    "dimension_type",
    "dimension_value",
    "metric",
    "value",
    "source_version",
    "data_updated_at",
    "definition_id",
)

OVERVIEW_METRICS = (
    "营收",
    "活动目标",
    "目标完成额",
    "目标完成率",
    "目标差额",
    "时间进度",
    "营收进度与时间进度差",
    "服务期营收",
    "业务营收与服务期营收差额",
)
EFFICIENCY_METRICS = (
    "活跃人数",
    "付费人数",
    "付费金额",
    "付费转化率",
    "客单价",
    "ARPU",
    "活跃人数占比",
    "付费人数占比",
    "营收占比",
)
USER_STAGE_METRICS = EFFICIENCY_METRICS + (
    "组合品付费人数",
    "组合品订单量",
    "组合品营收",
    "组合品转化率",
    "组合品客单价",
    "组合品ARPU",
)
PRODUCT_METRICS = (
    "订单量",
    "付费人数",
    "活跃付费人数",
    "活跃人数",
    "营收",
    "订单占比",
    "付费人数占比",
    "营收占比",
    "转化率",
    "客单价",
    "ARPU",
)
DEPOSIT_METRICS = (
    "定金来源用户数",
    "定金订单量",
    "定金金额",
    "尾款人数",
    "尾款订单量",
    "尾款营收",
    "尾款率",
    "尾款营收占整体营收比例",
    "转组合品人数",
    "转组合品订单量",
    "转组合品营收",
    "转498人数",
    "转498订单量",
    "转498营收",
    "转其他商品人数",
    "转其他商品订单量",
    "转其他商品营收",
    "未转化人数",
)
RESERVOIR_METRICS = (
    "蓄水来源用户数",
    "蓄水订单量",
    "蓄水金额",
    "转大人数",
    "转大订单量",
    "转大营收",
    "转大率",
    "活跃蓄水用户数",
    "非活跃蓄水用户数",
    "活跃蓄水用户转大率",
    "非活跃蓄水用户转大率",
    "转化商品流向",
)
HIGH_VALUE_METRICS = (
    "来源用户数",
    "活跃人数",
    "付费人数",
    "订单量",
    "营收",
    "付费转化率",
    "客单价",
    "ARPU",
    "组合品付费人数",
    "组合品订单量",
    "组合品营收",
    "组合品转化率",
    "高净值营收占私域营收比例",
)
SALES_FUNNEL_METRICS = (
    "线索领取人数",
    "线索领取率",
    "电话拨打人数",
    "有效接通人数",
    "有效接通率",
    "未有效接通人数",
    "企微添加人数",
    "企微添加率",
    "转化人数",
    "转化率",
    "转化营收",
    "客单价",
    "ARPU",
    "有效接通后转化人数",
    "有效接通后转化率",
    "有效接通后营收",
    "有效接通后客单价",
    "有效接通后ARPU",
    "未有效接通后转化人数",
    "未有效接通后转化率",
    "未有效接通后营收",
    "未有效接通后客单价",
    "未有效接通后ARPU",
)


@dataclass(frozen=True)
class ModuleSpec:
    name: str
    sql_file: str
    sheet_names: tuple[str, ...]
    required_columns: tuple[str, ...] = LONG_COLUMNS
    channels: tuple[str, ...] = ()
    stages: tuple[str, ...] = ()
    user_layers: tuple[str, ...] = ()
    products: tuple[str, ...] = ()
    metrics: tuple[str, ...] = ()


_CHANNELS = ("私域整体", "APP", "销售")
MODULE_SPECS = (
    ModuleSpec("overview", "overview.sql", ("经营总览",), metrics=OVERVIEW_METRICS),
    ModuleSpec(
        "active_efficiency",
        "active_efficiency.sql",
        ("活跃效率",),
        channels=_CHANNELS,
        metrics=EFFICIENCY_METRICS,
    ),
    ModuleSpec(
        "user_stage",
        "user_stage.sql",
        ("用户分层", "学段表现"),
        channels=_CHANNELS,
        stages=STAGES,
        user_layers=USER_LAYERS,
        metrics=USER_STAGE_METRICS,
    ),
    ModuleSpec(
        "product_structure",
        "product_structure.sql",
        ("商品结构",),
        products=PRODUCTS,
        metrics=PRODUCT_METRICS,
    ),
    ModuleSpec("deposit", "deposit.sql", ("定金策略",), metrics=DEPOSIT_METRICS),
    ModuleSpec("reservoir", "reservoir.sql", ("蓄水策略",), metrics=RESERVOIR_METRICS),
    ModuleSpec(
        "high_value",
        "high_value.sql",
        ("高净值策略",),
        user_layers=USER_LAYERS[3:],
        metrics=HIGH_VALUE_METRICS,
    ),
    ModuleSpec(
        "sales_funnel",
        "sales_funnel.sql",
        ("销售承接",),
        metrics=SALES_FUNNEL_METRICS,
    ),
)

_MODULE_BY_NAME = {module.name: module for module in MODULE_SPECS}
_CAMPAIGN_CONFIG = Path(__file__).resolve().parents[2] / "review_pack_campaigns.json"


def module_spec(name: str) -> ModuleSpec:
    """Return the immutable specification for a named review module."""
    return _MODULE_BY_NAME[name]


def campaign_defaults(name: str) -> dict:
    """Return configured source windows, or no defaults for unknown campaigns."""
    with _CAMPAIGN_CONFIG.open(encoding="utf-8") as config_file:
        campaigns = json.load(config_file)
    return campaigns.get(name, {})
