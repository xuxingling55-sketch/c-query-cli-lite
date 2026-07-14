const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const M = require('../outputs/sales-effort-monitor-demo/metrics.js');
const D = require('../outputs/sales-effort-monitor-demo/data.js');

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

test('simulated data is deterministic and has the required size', () => {
  const first = D.generate('demo-seed');
  const second = D.generate('demo-seed');
  const different = D.generate('another-seed');

  assert.deepEqual(first, second);
  assert.notDeepEqual(first.dailyFacts.slice(0, 20), different.dailyFacts.slice(0, 20));
  assert.equal(first.dates.length, 14);
  assert.equal(first.teams.length, 4);
  assert.equal(first.salespeople.length, 24);
  assert.equal(first.users.length, 600);
  assert.equal(first.dailyFacts.length, 14 * 600);
});

test('generated facts include required dimensions and measures', () => {
  const dataset = D.generate(20260714);
  const row = dataset.dailyFacts[0];
  const required = [
    'date', 'teamId', 'salespersonId', 'userId', 'stage', 'grade', 'userLayer',
    'clueReceipts', 'outboundCalls', 'connectedCalls', 'callMinutes',
    'wecomInteractions', 'followedUp',
  ];
  required.forEach((key) => assert.ok(Object.hasOwn(row, key), `missing ${key}`));
  dataset.dailyFacts.forEach((fact) => {
    assert.ok(fact.connectedCalls <= fact.outboundCalls);
    assert.ok(fact.followedUp === 0 || fact.connectedCalls > 0);
    ['clueReceipts', 'outboundCalls', 'connectedCalls', 'callMinutes', 'wecomInteractions', 'followedUp']
      .forEach((key) => assert.ok(Number.isFinite(fact[key]) && fact[key] >= 0, `invalid ${key}`));
  });
});

test('simulated scenarios create visible and explainable differences', () => {
  const dataset = D.generate('scenario-check');
  const teamByScenario = Object.fromEntries(dataset.teams.map((team) => [team.scenario, team.id]));
  const rowsFor = (scenario) => dataset.dailyFacts.filter((row) => row.teamId === teamByScenario[scenario]);

  const focused = rowsFor('highValueFocus');
  const highValue = M.aggregateSummary(focused.filter((row) => row.userLayer === '定金高净值'));
  const other = M.aggregateSummary(focused.filter((row) => row.userLayer !== '定金高净值'));
  assert.ok(highValue.callsPerContactedUser > other.callsPerContactedUser * 1.4);

  const underweight = rowsFor('lowPrimaryUnderweight');
  const lowPrimary = M.aggregateSummary(underweight.filter((row) => row.stage === '小低'));
  const otherStages = M.aggregateSummary(underweight.filter((row) => row.stage !== '小低'));
  assert.ok(lowPrimary.callsPerContactedUser < otherStages.callsPerContactedUser * 0.75);

  const stable = M.aggregateSummary(rowsFor('stable'));
  const gap = M.aggregateSummary(rowsFor('followupGap'));
  assert.ok(gap.followupRate < stable.followupRate * 0.7);
});

test('summary aggregates facts and guards rates', () => {
  const summary = M.aggregateSummary([
    {
      clueReceipts: 2, outboundCalls: 4, connectedCalls: 2,
      callMinutes: 20, wecomInteractions: 3, followedUp: 1,
      userId: 'u1', salespersonId: 's1',
    },
    {
      clueReceipts: 1, outboundCalls: 2, connectedCalls: 1,
      callMinutes: 10, wecomInteractions: 1, followedUp: 1,
      userId: 'u2', salespersonId: 's1',
    },
  ]);

  assert.equal(summary.clueReceipts, 3);
  assert.equal(summary.outboundCalls, 6);
  assert.equal(summary.connectedCalls, 3);
  assert.equal(summary.callMinutes, 30);
  assert.equal(summary.wecomInteractions, 4);
  assert.equal(summary.followedUp, 2);
  assert.equal(summary.connectionRate, 0.5);
  assert.equal(summary.followupRate, 2 / 3);
  assert.equal(summary.userCount, 2);
  assert.equal(summary.salespersonCount, 1);
});

test('heatmap, trend, and ranking produce dashboard-ready groups', () => {
  const rows = [
    { date: '2026-07-01', salespersonId: 's1', stage: '小低', outboundCalls: 3, connectedCalls: 1, callMinutes: 5, clueReceipts: 1, wecomInteractions: 1, followedUp: 1, userId: 'u1' },
    { date: '2026-07-01', salespersonId: 's2', stage: '小高', outboundCalls: 5, connectedCalls: 2, callMinutes: 9, clueReceipts: 2, wecomInteractions: 2, followedUp: 1, userId: 'u2' },
    { date: '2026-07-02', salespersonId: 's1', stage: '小低', outboundCalls: 4, connectedCalls: 2, callMinutes: 8, clueReceipts: 1, wecomInteractions: 1, followedUp: 1, userId: 'u1' },
  ];

  const heatmap = M.buildHeatmap(rows, 'outboundCalls');
  const trend = M.buildTrend(rows, 'connectedCalls');
  const ranking = M.rankSalespeople(rows);

  assert.deepEqual(heatmap.map((cell) => [cell.salespersonId, cell.stage, cell.value]), [
    ['s1', '小低', 7],
    ['s2', '小高', 5],
  ]);
  assert.deepEqual(trend.map((point) => [point.date, point.value]), [
    ['2026-07-01', 3],
    ['2026-07-02', 2],
  ]);
  assert.equal(ranking.length, 2);
  assert.equal(ranking[0].salespersonId, 's1');
  assert.ok(Number.isFinite(ranking[0].effortScore));
});

test('data and metrics expose browser globals without Node modules', () => {
  const context = vm.createContext({});
  const outputDir = path.resolve(__dirname, '../outputs/sales-effort-monitor-demo');
  vm.runInContext(fs.readFileSync(path.join(outputDir, 'data.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(outputDir, 'metrics.js'), 'utf8'), context);

  assert.equal(typeof context.SalesEffortData.generate, 'function');
  assert.equal(typeof context.SalesEffortMetrics.aggregateSummary, 'function');
  assert.equal(context.SalesEffortData.generate('browser').users.length, 600);
});

test('anomaly detection returns every supported typed record', () => {
  const rows = [];
  for (let day = 1; day <= 4; day += 1) {
    const date = `2026-07-0${day}`;
    rows.push({
      date, teamId: 't1', salespersonId: 's-share', userId: `share-${day}`,
      stage: day < 4 ? '小低' : '小高', userLayer: '其他付费',
      clueReceipts: day < 4 ? 12 : 1, outboundCalls: day < 4 ? 12 : 1,
      connectedCalls: day < 4 ? 6 : 1, callMinutes: day < 4 ? 30 : 5,
      wecomInteractions: 2, followedUp: 1,
    });
  }
  rows.push(
    { date: '2026-07-04', teamId: 't1', salespersonId: 's-risk', userId: 'hv', stage: '高中', userLayer: '定金高净值', clueReceipts: 1, outboundCalls: 3, connectedCalls: 0, callMinutes: 0, wecomInteractions: 0, followedUp: 0 },
    { date: '2026-07-04', teamId: 't1', salespersonId: 's-risk', userId: 'no-follow', stage: '初中', userLayer: '其他付费', clueReceipts: 1, outboundCalls: 1, connectedCalls: 1, callMinutes: 2, wecomInteractions: 0, followedUp: 0 },
    { date: '2026-07-04', teamId: 't1', salespersonId: 's-risk', userId: 'depth', stage: '小高', userLayer: '其他付费', clueReceipts: 1, outboundCalls: 1, connectedCalls: 0, callMinutes: 0, wecomInteractions: 0, followedUp: 0 },
  );

  const types = new Set(M.detectAnomalies(rows).map((item) => item.type));
  [
    'share_drop',
    'high_value_unreached',
    'connected_without_followup',
    'low_effective_depth',
    'single_stage_concentration',
  ].forEach((type) => assert.ok(types.has(type), `missing anomaly ${type}`));
});
