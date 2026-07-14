const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const M = require('../outputs/sales-effort-monitor-demo/metrics.js');
const D = require('../outputs/sales-effort-monitor-demo/data.js');

test('composite effort uses the agreed weights', () => {
  const dimensions = [
    ['normalizedCallMinutes', 30],
    ['normalizedReachedUsers', 25],
    ['normalizedOutboundCalls', 20],
    ['normalizedWecomInteractions', 15],
    ['normalizedClueReceipts', 10],
  ];
  dimensions.forEach(([dimension, expected]) => {
    assert.equal(M.compositeEffort({ [dimension]: 1 }), expected, dimension);
  });
  assert.equal(M.compositeEffort(Object.fromEntries(dimensions.map(([key]) => [key, 1]))), 100);
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

test('heat cell intersects with the active stage and user-layer filters', () => {
  const context = vm.createContext({
    window: { addEventListener() {} },
  });
  context.globalThis = context;
  const appPath = path.resolve(__dirname, '../outputs/sales-effort-monitor-demo/app.js');
  vm.runInContext(fs.readFileSync(appPath, 'utf8'), context);
  assert.deepEqual(
    Object.keys(context.window.SalesEffortApp.state).filter((key) => [
      'date', 'window', 'teamId', 'salespersonId', 'stage', 'userLayer', 'metric', 'heatCell',
    ].includes(key)),
    ['date', 'window', 'teamId', 'salespersonId', 'stage', 'userLayer', 'metric', 'heatCell'],
  );
  const rows = [
    { teamId: 't1', stage: '小低', userLayer: '老未新增' },
    { teamId: 't1', stage: '小低', userLayer: '其他付费' },
    { teamId: 't1', stage: '小高', userLayer: '老未新增' },
    { teamId: 't2', stage: '小低', userLayer: '老未新增' },
  ];

  const result = context.window.SalesEffortApp.intersectRows(
    rows,
    { teamId: 't1', stage: '小低' },
    { stage: '小低', userLayer: '老未新增' },
    M.applyFilters,
  );
  assert.deepEqual(result, [rows[0]]);

  const conflict = context.window.SalesEffortApp.intersectRows(
    rows,
    { stage: '小高' },
    { stage: '小低', userLayer: '老未新增' },
    M.applyFilters,
  );
  assert.deepEqual(conflict, []);
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
      userId: 'u1', salespersonId: 's1',
    },
    {
      clueReceipts: 0, outboundCalls: 0, connectedCalls: 0,
      callMinutes: 0, wecomInteractions: 0, followedUp: 0,
      userId: 'u2', salespersonId: 's1',
    },
  ]);

  assert.equal(summary.clueReceipts, 3);
  assert.equal(summary.outboundCalls, 6);
  assert.equal(summary.connectedCalls, 3);
  assert.equal(summary.callMinutes, 30);
  assert.equal(summary.wecomInteractions, 4);
  assert.equal(summary.followedUp, 2);
  assert.equal(summary.clueUsers, 1);
  assert.equal(summary.outboundUsers, 1);
  assert.equal(summary.reachedUsers, 1);
  assert.equal(summary.wecomUsers, 1);
  assert.equal(summary.followedUpUsers, 1);
  assert.equal(summary.connectionRateByCalls, 0.5);
  assert.equal(summary.connectionRateByUsers, 1);
  assert.equal(summary.connectionRate, 1);
  assert.equal(summary.followupRate, 1);
  assert.equal(summary.callsPerContactedUser, 6);
  assert.equal(summary.userCount, 2);
  assert.equal(summary.salespersonCount, 1);
});

test('summary returns null for rates with no eligible users or calls', () => {
  const summary = M.aggregateSummary([
    { userId: 'u1', salespersonId: 's1', outboundCalls: 0, connectedCalls: 0 },
  ]);
  assert.equal(summary.outboundUsers, 0);
  assert.equal(summary.reachedUsers, 0);
  assert.equal(summary.connectionRateByCalls, null);
  assert.equal(summary.connectionRateByUsers, null);
  assert.equal(summary.connectionRate, null);
  assert.equal(summary.callsPerContactedUser, null);
  assert.equal(summary.minutesPerReachedUser, null);
});

test('heatmap, trend, and ranking produce dashboard-ready groups', () => {
  const rows = [
    { date: '2026-07-01', salespersonId: 's1', stage: '小低', userLayer: '新增', outboundCalls: 3, connectedCalls: 1, callMinutes: 5, clueReceipts: 1, wecomInteractions: 1, followedUp: 1, userId: 'u1' },
    { date: '2026-07-01', salespersonId: 's2', stage: '小高', userLayer: '高净值', outboundCalls: 5, connectedCalls: 2, callMinutes: 9, clueReceipts: 2, wecomInteractions: 2, followedUp: 1, userId: 'u2' },
    { date: '2026-07-02', salespersonId: 's1', stage: '小低', userLayer: '新增', outboundCalls: 4, connectedCalls: 2, callMinutes: 8, clueReceipts: 1, wecomInteractions: 1, followedUp: 1, userId: 'u1' },
  ];

  const heatmap = M.buildHeatmap(rows, 'outboundCalls');
  const trend = M.buildTrend(rows, 'connectedCalls');
  const ranking = M.rankSalespeople(rows);

  assert.deepEqual(heatmap.map((cell) => [cell.stage, cell.userLayer, cell.value]), [
    ['小低', '新增', 7],
    ['小高', '高净值', 5],
  ]);
  assert.deepEqual(trend.map((point) => [point.date, point.value]), [
    ['2026-07-01', 3],
    ['2026-07-02', 2],
  ]);
  assert.equal(ranking.length, 2);
  assert.equal(ranking[0].salespersonId, 's1');
  assert.ok(Number.isFinite(ranking[0].effortScore));
});

test('effort score is normalized consistently within each current result range', () => {
  const rows = [
    { date: '2026-07-01', salespersonId: 's1', stage: '小低', userLayer: '新增', userId: 'u1', callMinutes: 10, connectedCalls: 1, outboundCalls: 2, wecomInteractions: 2, clueReceipts: 1 },
    { date: '2026-07-02', salespersonId: 's2', stage: '小高', userLayer: '高净值', userId: 'u2', callMinutes: 10, connectedCalls: 1, outboundCalls: 2, wecomInteractions: 2, clueReceipts: 1 },
    { date: '2026-07-02', salespersonId: 's2', stage: '小高', userLayer: '高净值', userId: 'u3', callMinutes: 10, connectedCalls: 1, outboundCalls: 2, wecomInteractions: 2, clueReceipts: 1 },
  ];
  const heatmap = M.buildHeatmap(rows, 'effortScore');
  const trend = M.buildTrend(rows, 'effortScore');
  const ranking = M.rankSalespeople(rows);

  assert.deepEqual(heatmap.map((item) => item.value), [50, 100]);
  assert.deepEqual(trend.map((item) => item.value), [50, 100]);
  assert.deepEqual(ranking.map((item) => item.effortScore), [100, 50]);
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

  const lowDepth = M.detectAnomalies(rows).find((item) => item.type === 'low_effective_depth');
  assert.equal(lowDepth.label, '未接通用户拨打不足');
  assert.match(lowDepth.description, /低于 2 次/);
});

test('unconnected low call depth triggers below two calls only', () => {
  const base = {
    date: '2026-07-01', teamId: 't1', salespersonId: 's1', stage: '小低',
    userLayer: '新增', connectedCalls: 0, callMinutes: 0, followedUp: 0,
  };
  const anomalies = M.detectAnomalies([
    { ...base, userId: 'one', outboundCalls: 1 },
    { ...base, userId: 'two', outboundCalls: 2 },
    { ...base, userId: 'zero', outboundCalls: 0 },
  ]).filter((item) => item.type === 'low_effective_depth');
  assert.deepEqual(anomalies.map((item) => item.userId), ['one']);
});
