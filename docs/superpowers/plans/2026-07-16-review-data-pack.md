# 一键复盘数据包 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Codex 中提供活动名称、日期范围和目标后，一次取齐全部固定复盘指标，完成一致性检查，并创建一份经过回读验证的飞书电子表格。

**Architecture:** 新增独立的 `src/review_pack/` 包，不改变现有自由问答取数流程。固定指标目录、固定 SQL、查询执行、结果标准化、检查和飞书写入分开；Codex Skill 只负责收集参数和调用稳定命令，不在运行时重新生成 SQL。

**Tech Stack:** Python 3、`dataclasses/json/subprocess/unittest`、pandas、现有 `src/executor.py`、lark-cli、飞书电子表格。

## Global Constraints

- 实施前使用 `superpowers:using-git-worktrees` 创建隔离工作树；原工作树有大量用户未提交内容，不得修改、移动、删除或提交。
- 原工作树未跟踪的 `scripts/`、Python 测试和历史查询只作只读口径参考；新功能使用本计划中的独立文件。
- 第一版入口为 Codex，输出为新建飞书表格；不覆盖历史结果或既有复盘文档。
- 必填输入为活动名称、开始日期、截止日期、活动目标。
- 去年同期为本期整体向前平移一年且天数相同；闰日无法平移时直接报错。
- 核心模块同时输出私域整体、APP、销售。
- 学段固定为 `1–3 年级`、`4–6 年级`、`初中`、`高中`，未知学段进入检查结果。
- 用户分层保留新增、老未、续费、高净值汇总和高净值四类细分。
- 第一版不接页面曝光、录音、问卷或用户反馈，不自动写会议结论。
- SQL 只允许 `SELECT` 或 `WITH ... SELECT`，必须带时间过滤和 `LIMIT 10000`。
- 每个任务先写失败测试，再写最小实现，验证后只提交该任务文件。

---

## File Map

```text
src/review_pack/
├── __init__.py
├── models.py          # 输入和结果模型
├── catalog.py         # 固定指标与飞书表顺序
├── sql_loader.py      # SQL 参数渲染与安全检查
├── normalize.py       # 统一结果列与同比
├── runner.py          # 模块执行和失败隔离
├── validation.py      # 一致性检查
├── lark_writer.py     # 飞书创建与回读
└── cli.py             # 命令编排
review_pack_campaigns.json  # 活动专属来源期，不含账号或密钥
queries/review_pack/
├── overview.sql
├── active_efficiency.sql
├── user_stage.sql
├── product_structure.sql
├── deposit.sql
├── reservoir.sql
├── high_value.sql
└── sales_funnel.sql
.agents/skills/review-data-pack/SKILL.md
scripts/review_data_pack.py
tests/test_review_pack_*.py
tests/test_review_data_pack_skill.py
```

## Task 1: 输入与结果模型

**Files:**
- Create: `src/review_pack/__init__.py`
- Create: `src/review_pack/models.py`
- Test: `tests/test_review_pack_models.py`

**Interfaces:**
- Produces: `ReviewRequest.create(...) -> ReviewRequest`
- Produces: `ModuleResult`, `CheckResult`, `ReviewPackResult`
- Consumed by every later task.

- [ ] **Step 1: Write failing tests**

```python
from datetime import date
import unittest
from review_pack.models import ReviewRequest, parse_target

class ReviewRequestTest(unittest.TestCase):
    def test_same_length_last_year_period(self):
        r = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
        self.assertEqual(r.last_year_start, date(2025, 7, 1))
        self.assertEqual(r.last_year_end, date(2025, 7, 15))
        self.assertEqual(r.period_days, 15)
        self.assertEqual(r.target_amount, 120_000_000)

    def test_rejects_reversed_range(self):
        with self.assertRaisesRegex(ValueError, "截止日期不能早于开始日期"):
            ReviewRequest.create("暑促", "2026-07-15", "2026-07-01", "1.2亿")

    def test_rejects_unshiftable_leap_day(self):
        with self.assertRaisesRegex(ValueError, "去年同期无法保持相同月日"):
            ReviewRequest.create("闰日", "2024-02-29", "2024-03-01", "100万")

    def test_target_units(self):
        self.assertEqual(parse_target("3500万"), 35_000_000)
        self.assertEqual(parse_target("12000000"), 12_000_000)
```

- [ ] **Step 2: Verify failure**

Run: `PYTHONPATH=src python -m unittest tests.test_review_pack_models -v`

Expected: FAIL because `review_pack.models` is missing.

- [ ] **Step 3: Implement models**

```python
@dataclass(frozen=True)
class ReviewRequest:
    name: str
    start: date
    end: date
    last_year_start: date
    last_year_end: date
    target_amount: float
    deposit_source_start: date | None = None
    deposit_source_end: date | None = None
    reservoir_source_start: date | None = None
    reservoir_source_end: date | None = None

    @property
    def period_days(self) -> int:
        return (self.end - self.start).days + 1
```

Implement `create()` with ISO-date parsing, exact year shifting, positive target validation, optional strategy source-window pairs, and clear errors when only one end of a source window is supplied. Add these result objects so later tasks share one stable contract:

```python
@dataclass
class ModuleResult:
    module: str
    status: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    source_version: str = "v1"

@dataclass(frozen=True)
class CheckResult:
    check_id: str
    level: str
    status: str
    module: str
    message: str
    actual: float | str | None = None
    expected: float | str | None = None
    difference: float | None = None

@dataclass
class ReviewPackResult:
    request: ReviewRequest
    modules: dict[str, ModuleResult]
    checks: list[CheckResult] = field(default_factory=list)
    local_snapshot: str = ""
    lark_url: str = ""
```

- [ ] **Step 4: Verify pass**

Run: `PYTHONPATH=src python -m unittest tests.test_review_pack_models -v`

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/review_pack/__init__.py src/review_pack/models.py tests/test_review_pack_models.py
git commit -m "feat: add review pack models"
```

## Task 2: 固定指标目录

**Files:**
- Create: `src/review_pack/catalog.py`
- Create: `review_pack_campaigns.json`
- Test: `tests/test_review_pack_catalog.py`

**Interfaces:**
- Produces: `MODULE_SPECS`, `SHEET_ORDER`, `module_spec(name)`.
- Produces: `campaign_defaults(name) -> dict`，用于四个必填输入之外的定金/蓄水来源期。
- All result rows use `period, channel, dimension_type, dimension_value, metric, value, source_version, data_updated_at, definition_id`.

- [ ] **Step 1: Write failing catalog tests**

```python
import unittest
from review_pack.catalog import MODULE_SPECS, SHEET_ORDER, module_spec

class CatalogTest(unittest.TestCase):
    def test_module_and_sheet_order(self):
        self.assertEqual([m.name for m in MODULE_SPECS], [
            "overview", "active_efficiency", "user_stage", "product_structure",
            "deposit", "reservoir", "high_value", "sales_funnel",
        ])
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
```

- [ ] **Step 2: Verify failure**

Run: `PYTHONPATH=src python -m unittest tests.test_review_pack_catalog -v`

Expected: FAIL because catalog is missing.

- [ ] **Step 3: Implement immutable catalog**

```python
STAGES = ("1–3 年级", "4–6 年级", "初中", "高中")
USER_LAYERS = (
    "新增", "老未", "续费", "高净值汇总", "高净值－当年毕业",
    "高净值－历史大会员可续购", "高净值－历史大会员不可续购", "高净值－其他组合品",
)
PRODUCTS = ("组合品", "零售品", "家庭包", "从小学系列", "198", "498", "千元及以上")
SHEET_ORDER = (
    "检查结果", "经营总览", "活跃效率", "用户分层", "学段表现", "商品结构",
    "定金策略", "蓄水策略", "高净值策略", "销售承接", "指标口径", "运行记录",
)
```

Add the following immutable catalog contract:

```python
LONG_COLUMNS = (
    "period", "channel", "dimension_type", "dimension_value",
    "metric", "value", "source_version", "data_updated_at", "definition_id",
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
```

Define all eight mappings explicitly: `overview -> overview.sql -> 经营总览`; `active_efficiency -> active_efficiency.sql -> 活跃效率`; `user_stage -> user_stage.sql -> 用户分层、学段表现`（按 `dimension_type` 分流）; `product_structure -> product_structure.sql -> 商品结构`; `deposit -> deposit.sql -> 定金策略`; `reservoir -> reservoir.sql -> 蓄水策略`; `high_value -> high_value.sql -> 高净值策略`; `sales_funnel -> sales_funnel.sql -> 销售承接`.

Use these exact metric tuples in the specs:

```python
OVERVIEW_METRICS = (
    "营收", "活动目标", "目标完成额", "目标完成率", "目标差额", "时间进度",
    "营收进度与时间进度差", "服务期营收", "业务营收与服务期营收差额",
)
EFFICIENCY_METRICS = (
    "活跃人数", "付费人数", "付费金额", "付费转化率", "客单价", "ARPU",
    "活跃人数占比", "付费人数占比", "营收占比",
)
USER_STAGE_METRICS = EFFICIENCY_METRICS + (
    "组合品付费人数", "组合品订单量", "组合品营收", "组合品转化率",
    "组合品客单价", "组合品ARPU",
)
PRODUCT_METRICS = (
    "订单量", "付费人数", "营收", "订单占比", "付费人数占比", "营收占比",
    "转化率", "客单价", "ARPU",
)
DEPOSIT_METRICS = (
    "定金来源用户数", "定金订单量", "定金金额", "尾款人数", "尾款订单量",
    "尾款营收", "尾款率", "尾款营收占整体营收比例", "转组合品人数",
    "转组合品订单量", "转组合品营收", "转498人数", "转498订单量",
    "转498营收", "转其他商品人数", "转其他商品订单量", "转其他商品营收",
    "未转化人数",
)
RESERVOIR_METRICS = (
    "蓄水来源用户数", "蓄水订单量", "蓄水金额", "转大人数", "转大订单量",
    "转大营收", "转大率", "活跃蓄水用户数", "非活跃蓄水用户数",
    "活跃蓄水用户转大率", "非活跃蓄水用户转大率", "转化商品流向",
)
HIGH_VALUE_METRICS = (
    "来源用户数", "活跃人数", "付费人数", "订单量", "营收", "付费转化率",
    "客单价", "ARPU", "组合品付费人数", "组合品订单量", "组合品营收",
    "组合品转化率", "高净值营收占私域营收比例",
)
SALES_FUNNEL_METRICS = (
    "线索领取人数", "线索领取率", "电话拨打人数", "有效接通人数", "有效接通率",
    "未有效接通人数", "企微添加人数", "企微添加率", "转化人数", "转化率",
    "转化营收", "客单价", "ARPU", "有效接通后转化人数", "有效接通后转化率",
    "有效接通后营收", "有效接通后客单价", "有效接通后ARPU",
    "未有效接通后转化人数", "未有效接通后转化率", "未有效接通后营收",
    "未有效接通后客单价", "未有效接通后ARPU",
)
```

Create `review_pack_campaigns.json` with a top-level `暑促` entry containing the two tested source windows. `campaign_defaults()` reads this non-secret configuration. Unknown campaigns return an empty dict; later validation must expose missing strategy windows instead of inventing dates.

- [ ] **Step 4: Verify pass and commit**

Run: `PYTHONPATH=src python -m unittest tests.test_review_pack_catalog -v`

```bash
git add src/review_pack/catalog.py review_pack_campaigns.json tests/test_review_pack_catalog.py
git commit -m "feat: define review metric catalog"
```

## Task 3: SQL 渲染与安全检查

**Files:**
- Create: `src/review_pack/sql_loader.py`
- Test: `tests/test_review_pack_sql.py`

**Interfaces:**
- Produces: `render_sql(path, request) -> str`.
- Allowed tokens: current/last-year dates, target, deposit source dates, reservoir source dates.

- [ ] **Step 1: Write failing tests**

```python
def test_replaces_dates_and_rejects_unknown_tokens(self):
    request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
    path.write_text(
        "SELECT {{CURRENT_START}} x FROM dws.topic_order_detail "
        "WHERE paid_time_sk BETWEEN {{CURRENT_START}} AND {{CURRENT_END}} LIMIT 10000",
        encoding="utf-8",
    )
    sql = render_sql(path, request)
    self.assertIn("20260701", sql)
    self.assertNotIn("{{", sql)
```

Add this explicit unknown-token assertion:

```python
path.write_text("SELECT {{UNKNOWN}} FROM dws.topic_order_detail LIMIT 10000", encoding="utf-8")
with self.assertRaisesRegex(ValueError, "未解析模板参数"):
    render_sql(path, request)
```

- [ ] **Step 2: Verify failure**

Run: `PYTHONPATH=src python -m unittest tests.test_review_pack_sql -v`

- [ ] **Step 3: Implement renderer**

Replace only the allowlisted tokens, reject all remaining braces, then call existing `executor.validate_sql(sql, max_limit=10000)`. Strategy templates with missing source windows return a typed `NotApplicableError` instead of inserting dummy dates.

- [ ] **Step 4: Verify and commit**

Run: `PYTHONPATH=src python -m unittest tests.test_review_pack_sql -v`

```bash
git add src/review_pack/sql_loader.py tests/test_review_pack_sql.py
git commit -m "feat: render fixed review SQL"
```

## Task 4: 核心经营查询

**Files:**
- Create: `queries/review_pack/overview.sql`
- Create: `queries/review_pack/active_efficiency.sql`
- Create: `queries/review_pack/user_stage.sql`
- Create: `queries/review_pack/product_structure.sql`
- Modify: `tests/test_review_pack_sql.py`

**Interfaces:**
- Every query returns the catalog's stable long-table fields.
- Period labels: `本期`, `去年同期`; channels: `私域整体`, `APP`, `销售`.

- [ ] **Step 1: Add failing structural tests**

```python
def test_core_templates_use_confirmed_periods_and_stages(self):
    request = ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿")
    root = Path("queries/review_pack")
    sqls = {n: render_sql(root / f"{n}.sql", request) for n in
            ("overview", "active_efficiency", "user_stage", "product_structure")}
    for sql in sqls.values():
        for token in ("20260701", "20260715", "20250701", "20250715"):
            self.assertIn(token, sql)
        self.assertIn("LIMIT 10000", sql.upper())
    self.assertIn("'1–3 年级'", sqls["user_stage"])
    self.assertIn("'4–6 年级'", sqls["user_stage"])
    self.assertNotIn("1-4年级", sqls["user_stage"])
    self.assertIn("'家庭包'", sqls["product_structure"])
```

- [ ] **Step 2: Verify failure**

Run: `PYTHONPATH=src python -m unittest tests.test_review_pack_sql -v`

- [ ] **Step 3: Implement `overview.sql`**

Use `queries/update_20260701_06_private_revenue_all_amount.sql` as read-only reference. Parameterize dates, emit APP/销售 and a separately aggregated private total, unpivot revenue/orders/users, and add target/progress rows only for private total. Include service-period revenue and the business-revenue/service-period gap using the confirmed company revenue rules. Do not invent APP or sales targets.

- [ ] **Step 4: Implement `active_efficiency.sql`**

Use only `aws.business_active_user_last_14_day` for active users, pay users, pay amount, conversion, AOV and ARPU. Aggregate per user/period/channel first; calculate the private total from deduplicated users, not APP+销售 user counts.

- [ ] **Step 5: Implement `user_stage.sql`**

Use this exact mapping:

```sql
CASE
 WHEN grade_name_month IN ('一年级','二年级','三年级') THEN '1–3 年级'
 WHEN grade_name_month IN ('四年级','五年级','六年级') THEN '4–6 年级'
 WHEN grade_name_month IN ('七年级','八年级','九年级','初一','初二','初三') THEN '初中'
 WHEN grade_name_month IN ('高一','高二','高三','十年级') THEN '高中'
 ELSE '未知学段'
END
```

Use precedence `高净值 > 新增 > 老未 > 续费 > 未映射`, retain four high-value sublayers, and emit user layer, stage, and user-layer × stage sections.

- [ ] **Step 6: Implement `product_structure.sql`**

Use stable order filters `u_user IS NOT NULL`, `is_test_user = 0`, `original_amount >= 39`, private attribution. Emit 组合品/零售品 and separate topical rows for 家庭包、从小学系列、198、498、千元及以上. V1 price bands use `original_amount` and expose `price_basis=original_amount`.

- [ ] **Step 7: Verify and commit**

Run: `PYTHONPATH=src python -m unittest tests.test_review_pack_sql -v`

```bash
git add queries/review_pack/overview.sql queries/review_pack/active_efficiency.sql queries/review_pack/user_stage.sql queries/review_pack/product_structure.sql tests/test_review_pack_sql.py
git commit -m "feat: add core review queries"
```

## Task 5: 策略与销售查询

**Files:**
- Create: `queries/review_pack/deposit.sql`
- Create: `queries/review_pack/reservoir.sql`
- Create: `queries/review_pack/high_value.sql`
- Create: `queries/review_pack/sales_funnel.sql`
- Modify: `tests/test_review_pack_sql.py`

**Interfaces:**
- Strategy source windows are independent from activity dates.
- Missing source window makes that module `not_applicable`, not zero.

- [ ] **Step 1: Add failing tests**

Assert deposit and reservoir source dates render independently; activity end appears only in tail/conversion windows; all templates contain three channels; sales SQL contains both `有效接通` and `未有效接通`; WeChat absence uses status code `data_source_missing` and display text `数据源未接入`.

- [ ] **Step 2: Verify failure**

Run: `PYTHONPATH=src python -m unittest tests.test_review_pack_sql -v`

- [ ] **Step 3: Implement strategy templates**

- `deposit.sql`: follow `queries/update_20260701_06_deposit_reservoir_deep_dive.sql`; output source users/orders/amount, tail users/orders/revenue/rate, channel, user layer, stage, high-value sublayer, and flow to 组合品/498/其他/未转化.
- `reservoir.sql`: keep source-product rules explicit; output source, conversion, active/inactive conversion rates and product flow by channel/user layer/stage.
- `high_value.sql`: output all four sublayers by channel/stage/product with active, pay, orders, revenue, conversion, AOV, ARPU and share.
- `sales_funnel.sql`: follow `queries/all_stage_telesale_pool_funnel_yoy_20260701_14.sql`; output receive, dial, connect, non-connect, WeChat add and conversion metrics. Never substitute phone data for missing WeChat data.

- [ ] **Step 4: Verify and commit**

Run: `PYTHONPATH=src python -m unittest tests.test_review_pack_sql -v`

```bash
git add queries/review_pack/deposit.sql queries/review_pack/reservoir.sql queries/review_pack/high_value.sql queries/review_pack/sales_funnel.sql tests/test_review_pack_sql.py
git commit -m "feat: add review strategy and sales queries"
```

## Task 6: 结果标准化

**Files:**
- Create: `src/review_pack/normalize.py`
- Test: `tests/test_review_pack_normalize.py`

**Interfaces:**
- Produces: `pair_periods(rows, request) -> rows` with current, last-year, absolute and relative change, both date ranges, definition ID and data update time.

- [ ] **Step 1: Write failing tests**

```python
def test_pair_periods_preserves_numbers_and_handles_zero_baseline(self):
    paired = pair_periods([
        {"period":"本期","channel":"APP","dimension_type":"总览","dimension_value":"全部","metric":"营收","value":120.0},
        {"period":"去年同期","channel":"APP","dimension_type":"总览","dimension_value":"全部","metric":"营收","value":100.0},
    ], request())
    self.assertEqual(paired[0]["absolute_change"], 20.0)
    self.assertAlmostEqual(paired[0]["relative_change"], 0.2)
    self.assertEqual(paired[0]["current_date_range"], "2026-07-01/2026-07-15")
    self.assertEqual(paired[0]["last_year_date_range"], "2025-07-01/2025-07-15")
```

Add these two assertions:

```python
zero = pair_periods([
    {"period":"本期","channel":"APP","dimension_type":"总览","dimension_value":"全部","metric":"营收","value":10},
    {"period":"去年同期","channel":"APP","dimension_type":"总览","dimension_value":"全部","metric":"营收","value":0},
], request())
self.assertIsNone(zero[0]["relative_change"])

duplicate = [
    {"period":"本期","channel":"APP","dimension_type":"总览","dimension_value":"全部","metric":"营收","value":10},
    {"period":"本期","channel":"APP","dimension_type":"总览","dimension_value":"全部","metric":"营收","value":11},
]
with self.assertRaisesRegex(ValueError, "重复周期数据"):
    pair_periods(duplicate, request())
```

- [ ] **Step 2: Implement deterministic pairing**

Key rows by channel/dimension/metric/source version/definition ID; convert pandas NaN to `None`; preserve numeric values; mark missing counterpart as `missing_current` or `missing_last_year`. Copy `data_updated_at` from the source rows and derive both explicit date-range strings from `ReviewRequest`.

- [ ] **Step 3: Verify and commit**

Run: `PYTHONPATH=src python -m unittest tests.test_review_pack_normalize -v`

```bash
git add src/review_pack/normalize.py tests/test_review_pack_normalize.py
git commit -m "feat: normalize review results"
```

## Task 7: 模块执行与本地快照

**Files:**
- Create: `src/review_pack/runner.py`
- Test: `tests/test_review_pack_runner.py`

**Interfaces:**
- Produces: `ReviewPackRunner.run(request) -> ReviewPackResult`.
- Constructor injects `query_runner(module: str, sql: str)`, `query_root`, `output_root`.

- [ ] **Step 1: Write failure-isolation test**

```python
def test_one_failure_keeps_other_modules_and_snapshot(self):
    def fake_query(module, sql):
        if module == "sales_funnel":
            raise RuntimeError("sales unavailable")
        return [{"period":"本期","channel":"私域整体","dimension_type":"总览","dimension_value":"全部","metric":"营收","value":100}]
    result = runner_with(fake_query).run(request())
    self.assertEqual(result.modules["sales_funnel"].status, "failed")
    self.assertEqual(result.modules["overview"].status, "success")
    self.assertTrue(Path(result.local_snapshot).is_file())
```

- [ ] **Step 2: Implement runner**

For each catalog module: render, call `query_runner(module.name, sql)`, normalize, record `success/failed/not_applicable`; never reuse prior rows. Write UTF-8 JSON under `outputs/review_pack/<timestamp>_<safe_name>/review_pack.json` by temporary file plus atomic rename. Production adapter ignores the module argument and wraps existing `SQLExecutor.execute(sql)`.

- [ ] **Step 3: Verify and commit**

Run: `PYTHONPATH=src python -m unittest tests.test_review_pack_runner -v`

```bash
git add src/review_pack/runner.py tests/test_review_pack_runner.py
git commit -m "feat: run review modules safely"
```

## Task 8: 一致性检查

**Files:**
- Create: `src/review_pack/validation.py`
- Test: `tests/test_review_pack_validation.py`

**Interfaces:**
- Produces: `validate_pack(result, tolerance=0.01) -> list[CheckResult]`.
- Produces focused helpers `check_channel_sum(module, rows, tolerance)` and `check_formula(module, rows, tolerance)` for deterministic unit tests.
- Checks observe only; never mutate values.

- [ ] **Step 1: Write failing checks**

```python
def test_channel_mismatch_reports_difference(self):
    rows = [
        {"metric":"营收","channel":"私域整体","current_value":120},
        {"metric":"营收","channel":"APP","current_value":50},
        {"metric":"营收","channel":"销售","current_value":60},
    ]
    check = check_channel_sum("overview", rows, 0.01)[0]
    self.assertEqual(check.status, "failed")
    self.assertEqual(check.difference, 10)
```

Add one table-driven test with these exact failing inputs and expected check IDs:

```python
cases = [
    ("duplicate_key", duplicate_key_rows(), "duplicate_key"),
    ("conversion_formula", rows_with_pay_20_active_50_rate_point_5(), "formula_conversion"),
    ("missing_last_year", current_period_only_rows(), "period_complete"),
    ("negative_count", rows_with_orders_minus_1(), "non_negative"),
    ("unknown_stage", rows_with_stage_unknown(), "stage_unknown"),
]
for name, rows, check_id in cases:
    with self.subTest(name=name):
        result = pack_with_rows("overview", rows)
        failed = {item.check_id for item in validate_pack(result) if item.status == "failed"}
        self.assertIn(check_id, failed)
```

Define the five named fixtures in the test file with complete long-format rows. For the conversion case use `活跃用户=50`, `支付用户=20`, `转化率=0.5`; for the negative case use `订单量=-1`; for the stage case use `dimension_type=学段, dimension_value=未知`.

- [ ] **Step 2: Implement registry**

Implement: module status, required columns, both periods, duplicate/conflicting key, APP+销售 vs private where additive, mapped user/stage totals plus unknowns, deposit converted+unconverted conservation, connected+unconnected conservation, conversion/AOV/ARPU formulas, negative values, percentage range, and stale update date. Use warning for legitimate overlap and unavailable optional source; failed for contradictions and missing mandatory results.

- [ ] **Step 3: Verify and commit**

Run: `PYTHONPATH=src python -m unittest tests.test_review_pack_validation -v`

```bash
git add src/review_pack/validation.py tests/test_review_pack_validation.py
git commit -m "feat: validate review consistency"
```

## Task 9: 飞书创建与回读

**Files:**
- Create: `src/review_pack/lark_writer.py`
- Test: `tests/test_review_pack_lark_writer.py`

**Interfaces:**
- Produces: `LarkWorkbookWriter.write(result) -> str`.
- Injects `command_runner(argv, stdin) -> dict` for tests.

Before editing this task, read the installed `lark-shared` and `lark-sheets` skill instructions completely; their authentication, typed-write and readback rules are binding.

- [ ] **Step 1: Write failing writer tests**

```python
def sample_result():
    return ReviewPackResult(
        request=ReviewRequest.create("暑促", "2026-07-01", "2026-07-15", "1.2亿"),
        modules={
            "overview": ModuleResult("overview", "success", [{
                "period":"本期", "channel":"私域整体", "dimension_type":"总览",
                "dimension_value":"全部", "metric":"营收", "value":100,
                "source_version":"v1",
            }]),
        },
        checks=[CheckResult("module_status", "info", "passed", "overview", "模块成功")],
    )

def test_create_uses_fixed_sheet_order_and_readback(self):
    calls = []
    def fake(argv, stdin=None):
        calls.append((argv, stdin))
        if "+workbook-create" in argv:
            return {"ok": True, "data": {"spreadsheet": {"url": "https://example.feishu.cn/sheets/test"}}}
        return {"ok": True, "data": {"sheets": [{"name":"检查结果","data":[["passed"]]}]}}
    url = LarkWorkbookWriter(fake).write(sample_result())
    self.assertEqual(url, "https://example.feishu.cn/sheets/test")
    self.assertTrue(any("+table-get" in argv for argv, _ in calls))
```

Add this failure assertion, using a fake that returns an empty sheet list for `+table-get`:

```python
def fake_missing_readback(argv, stdin=None):
    if "+workbook-create" in argv:
        return {"ok": True, "data": {"spreadsheet": {"url": "https://example.feishu.cn/sheets/test"}}}
    return {"ok": True, "data": {"sheets": []}}

with self.assertRaisesRegex(RuntimeError, "回读验证失败"):
    LarkWorkbookWriter(fake_missing_readback).write(sample_result())
```

- [ ] **Step 2: Implement adapter and typed payload**

Check `lark-cli` exists and verified user auth before writing. Use `lark-cli sheets +workbook-create --title ... --sheets - --as user`, preserving numbers as numeric dtypes and applying `#,##0`, `#,##0.00`, `0.00%`. Put failed/warning checks first, use all 12 sheet names, and never expose auth output.

- [ ] **Step 3: Implement readback**

Call `lark-cli sheets +table-get --url <url> --as user`; assert all sheets and row counts, plus sentinel values from 检查结果、经营总览 and two detail sheets. On mismatch keep the local snapshot and raise.

- [ ] **Step 4: Verify and commit**

Run: `PYTHONPATH=src python -m unittest tests.test_review_pack_lark_writer -v`

```bash
git add src/review_pack/lark_writer.py tests/test_review_pack_lark_writer.py
git commit -m "feat: write verified review pack to lark"
```

## Task 10: 命令入口

**Files:**
- Create: `src/review_pack/cli.py`
- Create: `scripts/review_data_pack.py`
- Test: `tests/test_review_pack_cli.py`

**Interfaces:**
- Command: `python scripts/review_data_pack.py --name 暑促 --start 2026-07-01 --end 2026-07-15 --target 1.2亿`.
- Optional source-window flags; safe modes `--sample`, `--dry-run`.

- [ ] **Step 1: Write failing CLI test**

```python
def test_sample_dry_run_has_no_lark_write(self):
    completed = subprocess.run([
        sys.executable, "scripts/review_data_pack.py", "--name", "暑促",
        "--start", "2026-07-01", "--end", "2026-07-15", "--target", "1.2亿",
        "--sample", "--dry-run",
    ], check=True, capture_output=True, text=True)
    payload = json.loads(completed.stdout)
    self.assertTrue(payload["ok"])
    self.assertEqual(payload["last_year_period"], "2025-07-01~2025-07-15")
    self.assertNotIn("lark_url", payload)
```

- [ ] **Step 2: Implement orchestration**

Parse flags, construct request, choose sample or production runner, execute, validate, update snapshot. Dry-run prints one JSON object and never calls a write. Normal mode writes to Feishu and prints URL, check summary and failed modules. Exit codes: 2 invalid input, 3 all modules failed, 4 Feishu write/readback failed.

When optional strategy-window flags are omitted, load them from `campaign_defaults(activity_name)`. This keeps the user-facing required input at exactly four values. For an unknown activity with no preset, keep strategy modules visible as failed configuration checks and explain which source windows must be configured; never report zero as a successful result.

- [ ] **Step 3: Verify and commit**

Run: `PYTHONPATH=src python -m unittest tests.test_review_pack_cli -v`

```bash
git add src/review_pack/cli.py scripts/review_data_pack.py tests/test_review_pack_cli.py
git commit -m "feat: add one-click review command"
```

## Task 11: Codex Skill

**Files:**
- Create: `.agents/skills/review-data-pack/SKILL.md`
- Test: `tests/test_review_data_pack_skill.py`

**Interfaces:**
- Triggers: `生成复盘数据包`, `一次取齐复盘指标`, `跑活动复盘数据`.
- Calls only the stable script; never generates SQL itself.

Before editing `SKILL.md`, invoke the available `skill-creator` and `superpowers:writing-skills` instructions and follow their validation requirements.

- [ ] **Step 1: Write failing skill contract test**

```python
def test_skill_uses_stable_command_and_returns_lark_link(self):
    text = Path(".agents/skills/review-data-pack/SKILL.md").read_text(encoding="utf-8")
    for value in ("生成复盘数据包", "scripts/review_data_pack.py", "--name", "--start", "--end", "--target", "飞书链接"):
        self.assertIn(value, text)
```

- [ ] **Step 2: Write Skill instructions**

Collect only missing required inputs; echo both date ranges; confirm lark-cli installation/auth before write; run stable command; wait through completion; return only link/check summary/failed modules; never modify existing documents; explain missing strategy windows as not applicable.

- [ ] **Step 3: Verify and commit**

Run: `python -m unittest tests.test_review_data_pack_skill -v`

```bash
git add .agents/skills/review-data-pack/SKILL.md tests/test_review_data_pack_skill.py
git commit -m "feat: add review data pack skill"
```

## Task 12: 全量验证、真实冒烟和文档

**Files:**
- Modify: `README.md`
- Create: `docs/review-data-pack-operations.md`

- [ ] **Step 1: Run focused tests**

Run: `PYTHONPATH=src python -m unittest discover -s tests -p 'test_review_pack*.py' -v`

Expected: all review-pack tests PASS.

- [ ] **Step 2: Run complete Python tests**

Run: `PYTHONPATH=src python -m unittest discover -s tests -p 'test_*.py' -v`

Expected: all tests PASS. Record unrelated pre-existing untracked test failures separately; do not hide them.

- [ ] **Step 3: Run sample end-to-end dry run**

```bash
PYTHONPATH=src python scripts/review_data_pack.py \
  --name 暑促 --start 2026-07-01 --end 2026-07-15 --target 1.2亿 \
  --deposit-source-start 2026-06-24 --deposit-source-end 2026-06-30 \
  --reservoir-source-start 2026-05-22 --reservoir-source-end 2026-06-30 \
  --sample --dry-run
```

Expected: exit 0, correct two periods, all eight modules represented, snapshot exists, no lark URL.

- [ ] **Step 4: Run real database-only smoke test**

Run the same command without `--sample` and retain `--dry-run`.

Expected: every available module succeeds; unavailable source is explicit. Compare ten sentinels with verified July queries: total/APP/sales revenue, active users, conversion, ARPU, one user layer, one stage, deposit tail rate, sales receive rate.

- [ ] **Step 5: Run real Feishu creation and readback**

After `lark-cli auth status --json --verify` confirms a verified user, run without `--dry-run`.

Expected: one new workbook, 12 sheets, matching sentinels in 检查结果、经营总览、用户分层、销售承接; no existing document modified.

- [ ] **Step 6: Document usage and recovery**

README text:

```text
在 Codex 中说：生成复盘数据包：暑促，2026/7/1–7/15，目标 1.2 亿。
系统会一次取齐固定指标、检查冲突并返回一份新的飞书表格。
```

Operations doc covers flags, exit codes, snapshot path, source windows, reruns and failed-module display.

- [ ] **Step 7: Final verification and commit**

Run:

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_*.py' -v
git diff --check
git status --short
```

Expected: tests PASS; no whitespace errors; only planned files changed in isolated worktree.

```bash
git add README.md docs/review-data-pack-operations.md
git commit -m "docs: explain one-click review data pack"
```

## Final Review Gate

Before completion, invoke `superpowers:verification-before-completion` and report test pass count, real dry-run module status, created Flybook URL and readback result, unavailable sources, and confirmation that the original dirty worktree and existing Flybook documents were untouched.
