# C 端私域关键指标独立看板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 C 端私域关键指标页面整理成一套可独立提交、预览和发布的静态快照看板。

**Architecture:** 保留 `scripts/key_metrics_dashboard_push.py` 中已经验证的指标计算和页面渲染，新增独立报表输出能力，把页面、外部 JSON 快照和当次 SQL 写入 `independent_reports/c_end_private_metrics/`。浏览器优先读取 `./data/report.json`，页面内置数据仅作为加载失败时的兜底；数仓配置只从本地 `config.json` 或环境变量读取。

**Tech Stack:** Python 3、标准库、静态 HTML/CSS/JavaScript、JSON、`unittest`

## Global Constraints

- 项目编号固定为 `c-end-private-metrics`。
- 正式路径固定为 `/c-end-private-metrics/`，Preview 路径固定为 `/_preview/c-end-private-metrics/`。
- `auth.mode` 固定为 `login`，`runtime.type` 固定为 `static`。
- `preview.data_mode` 固定为 `snapshot`，`refresh.enabled` 固定为 `false`。
- 第一版不改变现有指标口径，不增加实时查询后端，不启用定时刷新。
- 页面、数据和资源只使用相对路径。
- 发布目录不得包含数据库凭据、个人信息或订单明细。
- 保留现有飞书卡片和妙搭发布行为；新增独立报表参数不能改变旧命令的默认结果。

## File Structure

- Modify: `scripts/key_metrics_dashboard_push.py` — 安全读取数据配置，并生成独立报表页面、JSON 快照和 SQL。
- Modify: `tests/test_key_metrics_dashboard_push.py` — 覆盖配置安全、快照加载和独立报表生成。
- Create: `independent_reports/c_end_private_metrics/monitor.yaml` — NX 独立报表合同。
- Create: `independent_reports/c_end_private_metrics/docs/metric.md` — 指标口径、日期与安全边界。
- Create: `independent_reports/c_end_private_metrics/public/index.html` — 生成后的静态看板。
- Create: `independent_reports/c_end_private_metrics/public/data/report.json` — 生成后的脱敏汇总快照。
- Create: `independent_reports/c_end_private_metrics/sql/report.sql` — 生成快照时使用的查询 SQL。
- Create: `independent_reports/c_end_private_metrics/README.md` — 更新、检查、Preview 和发布说明。
- Create: `tests/test_c_end_private_metrics_report.py` — 独立报表合同与产物验收。

---

### Task 1: 移除脚本内数据库凭据并建立安全配置入口

**Files:**
- Modify: `scripts/key_metrics_dashboard_push.py`
- Modify: `tests/test_key_metrics_dashboard_push.py`

**Interfaces:**
- Consumes: 项目根目录下不提交的 `config.json`，或 `SR_HOST`、`SR_PORT`、`SR_USER`、`SR_PASSWORD`、`SR_DATABASE` 环境变量。
- Produces: `load_db_config(config_path: Path | None = None) -> Dict[str, Any]`，供 `fetch_metrics` 和命令入口使用。

- [ ] **Step 1: 写入失败测试**

```python
def test_load_db_config_reads_local_config_without_embedded_credentials(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "config.json"
        path.write_text(json.dumps({"starrocks": {
            "host": "db.local", "port": 9030, "user": "reader",
            "password": "secret", "database": "analytics"
        }}), encoding="utf-8")
        config = push.load_db_config(path)
    self.assertEqual(config["starrocks"]["host"], "db.local")
    self.assertNotIn("EMBEDDED_DB_CONFIG", Path(push.__file__).read_text(encoding="utf-8"))

def test_load_db_config_rejects_missing_values(self) -> None:
    with self.assertRaisesRegex(RuntimeError, "缺少 StarRocks"):
        push.load_db_config(Path("/path/that/does/not/exist"))
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python3 -m unittest tests.test_key_metrics_dashboard_push.KeyMetricsDashboardPushTest.test_load_db_config_reads_local_config_without_embedded_credentials tests.test_key_metrics_dashboard_push.KeyMetricsDashboardPushTest.test_load_db_config_rejects_missing_values -v`

Expected: FAIL，提示 `load_db_config` 尚不存在。

- [ ] **Step 3: 实现最小安全配置读取**

```python
def load_db_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    path = config_path or PROJECT_ROOT / "config.json"
    if path.is_file():
        config = json.loads(path.read_text(encoding="utf-8"))
    else:
        config = {
            "starrocks": {
                "host": os.environ.get("SR_HOST", ""),
                "port": int(os.environ.get("SR_PORT", "9030")),
                "user": os.environ.get("SR_USER", ""),
                "password": os.environ.get("SR_PASSWORD", ""),
                "database": os.environ.get("SR_DATABASE", ""),
            }
        }
    missing = [key for key in ("host", "user", "password", "database") if not config.get("starrocks", {}).get(key)]
    if missing:
        raise RuntimeError("缺少 StarRocks 配置：" + "、".join(missing))
    return config
```

同时删除脚本中的固定账号配置，并让真实查询调用 `load_db_config()`。

- [ ] **Step 4: 运行测试并确认通过**

Run: `python3 -m unittest tests.test_key_metrics_dashboard_push -v`

Expected: PASS，且旧指标测试全部继续通过。

- [ ] **Step 5: 提交**

```bash
git add scripts/key_metrics_dashboard_push.py tests/test_key_metrics_dashboard_push.py
git commit -m "fix: secure key metrics database config"
```

### Task 2: 生成外部快照并让页面优先读取相对路径

**Files:**
- Modify: `scripts/key_metrics_dashboard_push.py`
- Modify: `tests/test_key_metrics_dashboard_push.py`

**Interfaces:**
- Consumes: `dashboard_payload(metrics) -> Dict[str, Any]`。
- Produces: `build_html(metrics, snapshot_url: Optional[str] = None) -> str`。
- Produces: `write_static_report(metrics, output_dir: Path) -> Dict[str, Path]`，返回 `html`、`snapshot`、`sql` 三个文件路径。

- [ ] **Step 1: 写入失败测试**

```python
def test_write_static_report_creates_page_snapshot_and_sql(self) -> None:
    metrics = push.sample_metrics(date(2026, 7, 26))
    with tempfile.TemporaryDirectory() as temp_dir:
        paths = push.write_static_report(metrics, Path(temp_dir))
        html_text = paths["html"].read_text(encoding="utf-8")
        payload = json.loads(paths["snapshot"].read_text(encoding="utf-8"))
        sql_text = paths["sql"].read_text(encoding="utf-8")
    self.assertIn('fetch("./data/report.json"', html_text)
    self.assertEqual(payload["report_day"], "2026-07-26")
    self.assertTrue(sql_text.lstrip().startswith("WITH"))
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python3 -m unittest tests.test_key_metrics_dashboard_push.KeyMetricsDashboardPushTest.test_write_static_report_creates_page_snapshot_and_sql -v`

Expected: FAIL，提示 `write_static_report` 尚不存在。

- [ ] **Step 3: 实现页面读取和三个产物**

```python
def write_static_report(metrics: Dict[str, Any], output_dir: Path) -> Dict[str, Path]:
    public_dir = output_dir / "public"
    data_dir = public_dir / "data"
    sql_dir = output_dir / "sql"
    data_dir.mkdir(parents=True, exist_ok=True)
    sql_dir.mkdir(parents=True, exist_ok=True)
    html_path = public_dir / "index.html"
    snapshot_path = data_dir / "report.json"
    sql_path = sql_dir / "report.sql"
    html_path.write_text(build_html(metrics, snapshot_url="./data/report.json"), encoding="utf-8")
    snapshot_path.write_text(json.dumps(dashboard_payload(metrics), ensure_ascii=False, indent=2), encoding="utf-8")
    sql_path.write_text(key_metrics_sql(metrics["report_day"]).strip() + ";\n", encoding="utf-8")
    return {"html": html_path, "snapshot": snapshot_path, "sql": sql_path}
```

在页面中增加 `loadSnapshot()`：优先请求 `snapshot_url`，校验 `version >= fallbackPayload.version` 后渲染；失败时显示“快照加载失败，当前展示页面内置数据”，并继续使用内置数据。

- [ ] **Step 4: 运行测试并确认通过**

Run: `python3 -m unittest tests.test_key_metrics_dashboard_push -v`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add scripts/key_metrics_dashboard_push.py tests/test_key_metrics_dashboard_push.py
git commit -m "feat: generate independent dashboard snapshot"
```

### Task 3: 建立 NX 独立报表合同和口径文档

**Files:**
- Create: `independent_reports/c_end_private_metrics/monitor.yaml`
- Create: `independent_reports/c_end_private_metrics/docs/metric.md`
- Create: `independent_reports/c_end_private_metrics/README.md`
- Create: `tests/test_c_end_private_metrics_report.py`

**Interfaces:**
- Consumes: 项目编号 `c-end-private-metrics` 和 Task 2 的输出目录结构。
- Produces: 可被 NX 读取的静态项目合同，以及可由本地测试验证的文档与安全边界。

- [ ] **Step 1: 写入失败测试**

```python
class CEndPrivateMetricsReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1] / "independent_reports" / "c_end_private_metrics"

    def test_monitor_contract(self) -> None:
        monitor = json.loads((self.root / "monitor.yaml").read_text(encoding="utf-8"))
        self.assertEqual(monitor["id"], "c-end-private-metrics")
        self.assertEqual(monitor["path"], "/c-end-private-metrics/")
        self.assertEqual(monitor["auth"], {"mode": "login", "project_id": "c-end-private-metrics"})
        self.assertEqual(monitor["runtime"]["type"], "static")
        self.assertFalse(monitor["refresh"]["enabled"])
        self.assertEqual(monitor["preview"]["path"], "/_preview/c-end-private-metrics/")
        self.assertEqual(monitor["preview"]["auth_project_id"], "c-end-private-metrics-preview")
        self.assertEqual(monitor["preview"]["data_mode"], "snapshot")
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python3 -m unittest tests.test_c_end_private_metrics_report -v`

Expected: FAIL，提示 `monitor.yaml` 不存在。

- [ ] **Step 3: 写入完整合同和说明**

`monitor.yaml` 使用 JSON 内容，核心字段如下：

```json
{
  "id": "c-end-private-metrics",
  "name": "问鼎·C 端私域数据趋势看板",
  "category": "BI REPORT",
  "description": "展示 C 端私域营收、流量、定金、蓄水和高净值续费表现。",
  "path": "/c-end-private-metrics/",
  "owner": "BI",
  "repo": "market/bi/c-end-private-metrics",
  "meta": ["快照数据", "手动更新"],
  "auth": {"mode": "login", "project_id": "c-end-private-metrics"},
  "runtime": {"type": "static", "health_path": "/", "cpu": 0.5, "memory_mb": 256},
  "refresh": {"enabled": false, "entrypoint": "scripts/build-report.sh", "business_date_arg": "--business-date", "schedule": null, "old_schedule_location": null},
  "production": {"enabled": true, "rollout": "auto-after-main", "first_business_date": null},
  "secrets": [],
  "runtime_data_dirs": ["data", "outputs", "state", "public/reports"],
  "preview": {"enabled": true, "runtime": "static", "path": "/_preview/c-end-private-metrics/", "auth_project_id": "c-end-private-metrics-preview", "data_mode": "snapshot"}
}
```

`docs/metric.md` 明确指标范围、数据日期、来源表、过滤条件、分母为零规则及敏感字段禁入规则；`README.md` 给出生成、检查、MR、Preview 和正式发布步骤。

- [ ] **Step 4: 运行合同测试**

Run: `python3 -m unittest tests.test_c_end_private_metrics_report -v`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add independent_reports/c_end_private_metrics/monitor.yaml independent_reports/c_end_private_metrics/docs/metric.md independent_reports/c_end_private_metrics/README.md tests/test_c_end_private_metrics_report.py
git commit -m "feat: add c-end private metrics report contract"
```

### Task 4: 增加命令入口并生成真实快照

**Files:**
- Modify: `scripts/key_metrics_dashboard_push.py`
- Modify: `tests/test_key_metrics_dashboard_push.py`
- Create: `independent_reports/c_end_private_metrics/public/index.html`
- Create: `independent_reports/c_end_private_metrics/public/data/report.json`
- Create: `independent_reports/c_end_private_metrics/sql/report.sql`

**Interfaces:**
- Consumes: `--standalone-output PATH`、`--date YYYY-MM-DD`、现有 `--sample`。
- Produces: 退出码 0 和完整独立报表目录；真实模式使用本地 `config.json`，样例模式不访问数仓。

- [ ] **Step 1: 写入参数与产物失败测试**

```python
def test_parse_args_accepts_standalone_output(self) -> None:
    with patch.object(sys, "argv", ["push", "--sample", "--standalone-output", "report"]):
        args = push.parse_args()
    self.assertEqual(args.standalone_output, "report")
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python3 -m unittest tests.test_key_metrics_dashboard_push.KeyMetricsDashboardPushTest.test_parse_args_accepts_standalone_output -v`

Expected: FAIL，提示未知参数。

- [ ] **Step 3: 实现独立输出参数**

```python
parser.add_argument(
    "--standalone-output",
    help="生成 NX 独立报表目录；写入 public/index.html、public/data/report.json 和 sql/report.sql",
)
```

在 `main()` 中调用：

```python
if args.standalone_output:
    write_static_report(metrics, Path(args.standalone_output))
```

- [ ] **Step 4: 生成真实快照并执行检查**

Run:

```bash
python3 scripts/key_metrics_dashboard_push.py \
  --date 2026-07-26 \
  --standalone-output independent_reports/c_end_private_metrics \
  --skip-card
python3 -m json.tool independent_reports/c_end_private_metrics/monitor.yaml >/dev/null
python3 -m json.tool independent_reports/c_end_private_metrics/public/data/report.json >/dev/null
python3 -m unittest tests.test_key_metrics_dashboard_push tests.test_c_end_private_metrics_report -v
```

Expected: 命令全部退出 0，真实快照非空，测试全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add scripts/key_metrics_dashboard_push.py tests/test_key_metrics_dashboard_push.py independent_reports/c_end_private_metrics/public independent_reports/c_end_private_metrics/sql/report.sql
git commit -m "feat: build c-end private metrics dashboard"
```

### Task 5: 完成独立报表产物、安全和移动端验收

**Files:**
- Modify: `tests/test_c_end_private_metrics_report.py`
- Modify: `independent_reports/c_end_private_metrics/README.md`

**Interfaces:**
- Consumes: Task 4 生成的完整目录。
- Produces: 对相对路径、非空快照、敏感信息、数据日期、移动端规则的自动验收。

- [ ] **Step 1: 写入完整产物测试**

```python
def test_generated_artifacts_are_safe_and_portable(self) -> None:
    html = (self.root / "public/index.html").read_text(encoding="utf-8")
    payload = json.loads((self.root / "public/data/report.json").read_text(encoding="utf-8"))
    combined = html + json.dumps(payload, ensure_ascii=False)
    self.assertTrue(payload["daily"])
    self.assertRegex(payload["report_day"], r"^2026-07-\d{2}$")
    self.assertIn('fetch("./data/report.json"', html)
    self.assertIn("@media (max-width:760px)", html)
    self.assertNotIn("SR_PASSWORD", combined)
    self.assertNotRegex(combined, r"(?i)(password|access[_-]?token)[\"']?\s*[:=]\s*[\"'][^\"']+")
```

- [ ] **Step 2: 运行测试并确认当前差距**

Run: `python3 -m unittest tests.test_c_end_private_metrics_report -v`

Expected: 若任一安全或便携性要求未满足则 FAIL；否则直接 PASS。

- [ ] **Step 3: 修正发现的问题并补充验收说明**

如果测试失败，只修改对应页面生成逻辑或文档。`README.md` 最终列出：

```text
1. 生成快照
2. 运行 JSON、指标和产物测试
3. 提交功能分支与 MR
4. 验收 /_preview/c-end-private-metrics/
5. 合并并验收 /c-end-private-metrics/
```

- [ ] **Step 4: 运行完整验证**

Run:

```bash
python3 -m unittest tests.test_key_metrics_dashboard_push tests.test_c_end_private_metrics_report -v
python3 -m json.tool independent_reports/c_end_private_metrics/monitor.yaml >/dev/null
python3 -m json.tool independent_reports/c_end_private_metrics/public/data/report.json >/dev/null
git diff --check
```

Expected: 所有测试 PASS，两个 JSON 文件均可解析，`git diff --check` 无输出。

- [ ] **Step 5: 提交**

```bash
git add tests/test_c_end_private_metrics_report.py independent_reports/c_end_private_metrics/README.md
git commit -m "test: verify independent dashboard release"
```
