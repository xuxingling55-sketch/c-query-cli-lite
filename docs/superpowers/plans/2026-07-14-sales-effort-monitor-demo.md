# Sales Effort Monitor Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a directly openable, interactive sales effort monitoring demo with simulated data, cross-filters, anomaly detection, and team-to-sales-to-user drilldown.

**Architecture:** The demo is a standalone static web application under `outputs/sales-effort-monitor-demo/`. Data generation and metric aggregation are isolated in browser-compatible JavaScript modules with Node tests; the view layer consumes only aggregated selectors and keeps filter state in one store. No backend, build tool, or external network dependency is required.

**Tech Stack:** HTML5, CSS3, vanilla JavaScript, SVG charts, Node.js built-in test runner.

## Global Constraints

- All displayed data is simulated and the page must visibly show “演示数据”.
- The default view serves both business owners and sales managers.
- Do not define target effort ratios; comparisons use yesterday, recent 7-day average, and peer distribution only.
- Composite effort weights are: call duration 30%, reached users 25%, outbound calls 20%, WeCom interactions 15%, clue receipts 10%.
- Primary drilldown is team → salesperson → user detail.
- The page must open from the local filesystem without installing dependencies or starting a server.
- Desktop and narrow-screen layouts must not overlap or clip content.

---

### Task 1: Simulated Data And Metric Engine

**Files:**
- Create: `outputs/sales-effort-monitor-demo/data.js`
- Create: `outputs/sales-effort-monitor-demo/metrics.js`
- Create: `tests/sales_effort_monitor_metrics.test.cjs`

**Interfaces:**
- Produces: `SalesEffortData.generate(seed)` returning `{ dates, teams, salespeople, users, dailyFacts }`.
- Produces: `SalesEffortMetrics.applyFilters(dataset, filters)`, `aggregateSummary(rows)`, `buildHeatmap(rows, metric)`, `buildTrend(rows, metric)`, `rankSalespeople(rows)`, and `detectAnomalies(rows)`.
- Consumers: Tasks 2 and 3 use these browser globals directly.

- [ ] **Step 1: Write failing metric tests**

```javascript
const test = require('node:test');
const assert = require('node:assert/strict');
const M = require('../outputs/sales-effort-monitor-demo/metrics.js');

test('composite effort uses the agreed weights', () => {
  const score = M.compositeEffort({
    normalizedCallMinutes: 1,
    normalizedReachedUsers: 1,
    normalizedOutboundCalls: 1,
    normalizedWecomInteractions: 1,
    normalizedClueReceipts: 1,
  });
  assert.equal(score, 100);
});

test('zero denominators return null rates', () => {
  assert.equal(M.safeRate(3, 0), null);
});

test('team and segment filters intersect', () => {
  const rows = [
    { teamId: 't1', stage: '小低' },
    { teamId: 't1', stage: '小高' },
    { teamId: 't2', stage: '小低' },
  ];
  assert.deepEqual(
    M.applyFilters(rows, { teamId: 't1', stage: '小低' }),
    [rows[0]],
  );
});
```

- [ ] **Step 2: Run tests and verify failure**

Run: `node --test tests/sales_effort_monitor_metrics.test.cjs`

Expected: FAIL because `metrics.js` does not exist.

- [ ] **Step 3: Implement deterministic simulated data**

Create a seeded generator for 14 dates, 4 teams, 24 salespeople, and 600 users. Include dimensions `date`, `teamId`, `salespersonId`, `stage`, `grade`, and `userLayer`; include facts `clueReceipts`, `outboundCalls`, `connectedCalls`, `callMinutes`, `wecomInteractions`, and `followedUp`.

Encode four visible scenarios in the generated facts:

```javascript
const scenarioMultiplier = {
  stable: 1,
  highValueFocus: userLayer === '定金高净值' ? 1.6 : 0.9,
  lowPrimaryUnderweight: stage === '小低' ? 0.58 : 1.08,
  followupGap: 1,
};
```

- [ ] **Step 4: Implement metric functions**

Use a UMD wrapper so the same file works in Node and the browser. Implement guarded rates and the agreed weighted score:

```javascript
function safeRate(numerator, denominator) {
  return denominator > 0 ? numerator / denominator : null;
}

function compositeEffort(row) {
  return Math.round(100 * (
    row.normalizedCallMinutes * 0.30 +
    row.normalizedReachedUsers * 0.25 +
    row.normalizedOutboundCalls * 0.20 +
    row.normalizedWecomInteractions * 0.15 +
    row.normalizedClueReceipts * 0.10
  ));
}
```

`detectAnomalies` must return typed records for `share_drop`, `high_value_unreached`, `connected_without_followup`, `low_effective_depth`, and `single_stage_concentration`.

- [ ] **Step 5: Run metric tests**

Run: `node --test tests/sales_effort_monitor_metrics.test.cjs`

Expected: all tests PASS.

- [ ] **Step 6: Commit the data engine**

```bash
git add outputs/sales-effort-monitor-demo/data.js outputs/sales-effort-monitor-demo/metrics.js tests/sales_effort_monitor_metrics.test.cjs
git commit -m "feat: add sales effort demo data engine"
```

### Task 2: Monitoring Overview Interface

**Files:**
- Create: `outputs/sales-effort-monitor-demo/index.html`
- Create: `outputs/sales-effort-monitor-demo/styles.css`
- Create: `outputs/sales-effort-monitor-demo/app.js`

**Interfaces:**
- Consumes: `window.SalesEffortData` and `window.SalesEffortMetrics` from Task 1.
- Produces: `window.SalesEffortApp` with `render()`, `setFilters(patch)`, `selectHeatCell(cell)`, `openSalesperson(id)`, and `resetFilters()`.

- [ ] **Step 1: Add the semantic page shell**

The document loads local scripts only and includes these regions:

```html
<header class="app-header">...</header>
<section class="filter-bar" aria-label="筛选条件">...</section>
<main>
  <section id="kpi-strip" aria-label="核心状态"></section>
  <section class="analysis-grid">
    <div id="effort-heatmap"></div>
    <div id="anomaly-list"></div>
  </section>
  <section id="effort-trend"></section>
  <section id="sales-ranking"></section>
</main>
<aside id="sales-drawer" aria-hidden="true"></aside>
```

- [ ] **Step 2: Implement the visual system**

Define a restrained operational palette and stable dimensions:

```css
:root {
  --ink: #20282b;
  --muted: #69767a;
  --line: #dce4e6;
  --surface: #ffffff;
  --canvas: #f4f7f7;
  --cyan: #078f97;
  --cyan-soft: #dff1f1;
  --amber: #c58a16;
  --danger: #c5513c;
}
```

Use cards only for KPI tiles and repeated anomaly items. Keep chart sections unframed. At widths below 760px, stack analysis sections, make filters wrap, and present the sales drawer as a full-screen layer.

- [ ] **Step 3: Render KPI, heatmap, trend, anomalies, and ranking**

Implement SVG-based charts with direct labels and tooltips. The heatmap rows are user layers and columns are stages. Its metric switch must support composite effort, reached users, outbound calls, call minutes, and WeCom interactions.

- [ ] **Step 4: Verify direct file opening**

Run: `open outputs/sales-effort-monitor-demo/index.html`

Expected: the page loads without a server, displays six KPI tiles, the heatmap, trend, anomaly list, and ranking table, and visibly shows “演示数据”.

- [ ] **Step 5: Commit the overview**

```bash
git add outputs/sales-effort-monitor-demo/index.html outputs/sales-effort-monitor-demo/styles.css outputs/sales-effort-monitor-demo/app.js
git commit -m "feat: build sales effort monitoring overview"
```

### Task 3: Filters And Drilldown Workflow

**Files:**
- Modify: `outputs/sales-effort-monitor-demo/app.js`
- Modify: `outputs/sales-effort-monitor-demo/styles.css`
- Modify: `tests/sales_effort_monitor_metrics.test.cjs`

**Interfaces:**
- Consumes: filter and selector functions from Task 1.
- Produces: a consistent `state` object with `date`, `window`, `teamId`, `salespersonId`, `stage`, `userLayer`, `metric`, and `heatCell`.

- [ ] **Step 1: Add failing tests for drilldown selectors**

```javascript
test('heat cell filters both stage and user layer', () => {
  const result = M.applyFilters(rows, {
    heatCell: { stage: '小低', userLayer: '老未新增' },
  });
  assert.ok(result.every((r) => r.stage === '小低' && r.userLayer === '老未新增'));
});
```

- [ ] **Step 2: Run tests and verify failure**

Run: `node --test tests/sales_effort_monitor_metrics.test.cjs`

Expected: the new heat-cell test FAILS.

- [ ] **Step 3: Implement unified filter state**

Every control calls `setFilters(patch)`. A single `render()` computes filtered rows once and passes them to all view renderers. Clicking the active heat cell again clears it.

- [ ] **Step 4: Implement sales detail drawer**

The drawer contains salesperson identity, effort composition, stage distribution, user-layer distribution, 14-day trend, and a searchable user table. Include close and back controls with keyboard focus management.

- [ ] **Step 5: Implement anomaly navigation and empty state**

Clicking an anomaly applies its team, salesperson, stage, or user-layer filters before opening the relevant detail. When no rows remain, show the conflicting filter summary and a “清空筛选” button.

- [ ] **Step 6: Run all unit tests**

Run: `node --test tests/sales_effort_monitor_metrics.test.cjs`

Expected: all tests PASS.

- [ ] **Step 7: Commit interactions**

```bash
git add outputs/sales-effort-monitor-demo/app.js outputs/sales-effort-monitor-demo/styles.css tests/sales_effort_monitor_metrics.test.cjs
git commit -m "feat: add sales effort filters and drilldown"
```

### Task 4: Browser QA And Handoff

**Files:**
- Create: `tests/verify_sales_effort_monitor_demo.cjs`
- Create: `outputs/sales-effort-monitor-demo/README.md`
- Modify: `outputs/sales-effort-monitor-demo/index.html` if QA finds layout or accessibility defects.
- Modify: `outputs/sales-effort-monitor-demo/styles.css` if QA finds overlap or responsive defects.

**Interfaces:**
- Consumes: the completed static demo.
- Produces: repeatable structural checks and a concise handoff note.

- [ ] **Step 1: Add structural verification**

The Node test reads `index.html` and asserts local assets, required regions, the demo-data label, and absence of remote scripts:

```javascript
test('demo is self-contained and visibly labeled', () => {
  const html = fs.readFileSync(INDEX, 'utf8');
  assert.match(html, /演示数据/);
  assert.match(html, /id="effort-heatmap"/);
  assert.doesNotMatch(html, /https?:\/\//);
});
```

- [ ] **Step 2: Run all automated checks**

Run: `node --test tests/sales_effort_monitor_metrics.test.cjs tests/verify_sales_effort_monitor_demo.cjs`

Expected: all tests PASS.

- [ ] **Step 3: Inspect desktop and mobile views**

Open the page in a browser at 1440×900 and 390×844. Exercise team filtering, metric switching, heat-cell selection, anomaly navigation, sales drawer, search, reset, and empty state. Capture screenshots and verify no overlap, clipping, blank charts, or unreadable labels.

- [ ] **Step 4: Reconcile displayed totals**

Compare KPI values against `aggregateSummary(app.filteredRows)` in the browser console. Confirm heatmap totals and ranking totals use the same filtered row set.

- [ ] **Step 5: Add handoff instructions**

Document that `index.html` opens directly, all data is simulated, and the future live-data integration point is `data.js` while metric contracts remain unchanged.

- [ ] **Step 6: Commit QA artifacts**

```bash
git add tests/verify_sales_effort_monitor_demo.cjs outputs/sales-effort-monitor-demo/README.md outputs/sales-effort-monitor-demo/index.html outputs/sales-effort-monitor-demo/styles.css
git commit -m "test: verify sales effort monitor demo"
```

## Self-Review Results

- Spec coverage: filters, KPI strip, heatmap, trends, anomaly types, three-level drilldown, simulated-data notice, responsive behavior, empty/error states, and QA are each covered by a task.
- Placeholder scan: no deferred implementation markers remain.
- Interface consistency: Tasks 2 and 3 consume the exact globals and selector names produced by Task 1; Task 4 verifies the same DOM region identifiers defined by Task 2.
