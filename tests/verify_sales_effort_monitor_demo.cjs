const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const DEMO_DIR = path.join(ROOT, 'outputs/sales-effort-monitor-demo');
const INDEX = path.join(DEMO_DIR, 'index.html');

function read(file) {
  return fs.readFileSync(path.join(DEMO_DIR, file), 'utf8');
}

test('demo is self-contained and visibly labeled', () => {
  const html = read('index.html');
  assert.match(html, /<span class="demo-badge">演示数据<\/span>/);
  assert.doesNotMatch(html, /(?:src|href)=["']https?:\/\//i);
  assert.doesNotMatch(html, /<script[^>]+type=["']module["']/i);
});

test('all page assets are local and present', () => {
  const html = read('index.html');
  const assets = [...html.matchAll(/(?:src|href)=["']([^"']+)["']/g)]
    .map((match) => match[1]);
  assert.deepEqual(assets, ['styles.css', 'data.js', 'metrics.js', 'app.js']);
  assets.forEach((asset) => {
    assert.equal(path.basename(asset), asset, `asset must be local: ${asset}`);
    assert.ok(fs.existsSync(path.join(DEMO_DIR, asset)), `missing local asset: ${asset}`);
  });
});

test('required dashboard regions and controls are present', () => {
  const html = read('index.html');
  [
    'filter-date',
    'filter-window',
    'filter-team',
    'filter-salesperson',
    'filter-stage',
    'filter-layer',
    'reset-filters',
    'kpi-strip',
    'effort-heatmap',
    'anomaly-list',
    'effort-trend',
    'sales-ranking',
    'sales-drawer',
    'drawer-backdrop',
  ].forEach((id) => assert.match(html, new RegExp(`id=["']${id}["']`), `missing #${id}`));
});

test('dashboard contains exactly six KPI definitions and all five effort metrics', () => {
  const app = read('app.js');
  const kpiLabels = ['活跃销售', '领取用户', '外呼覆盖率', '接通率', '人均外呼次数', '平均沟通时长'];
  const metricLabels = ['综合精力', '触达用户', '外呼次数', '通话时长', '企微互动'];
  kpiLabels.forEach((label) => assert.match(app, new RegExp(`\\['${label}'`), `missing KPI ${label}`));
  metricLabels.forEach((label) => assert.match(app, new RegExp(`label: '${label}'`), `missing metric ${label}`));
  assert.equal((app.match(/class="kpi-card"/g) || []).length, 1, 'KPI cards must come from one six-item definition');
});

test('demo has no remote runtime dependency in HTML, CSS, or JavaScript', () => {
  ['index.html', 'styles.css', 'data.js', 'metrics.js', 'app.js'].forEach((file) => {
    const source = read(file);
    assert.doesNotMatch(source, /(?:https?:)?\/\//i, `${file} contains a remote URL`);
  });
});

