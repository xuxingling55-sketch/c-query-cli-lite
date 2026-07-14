(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.SalesEffortMetrics = api;
  }
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const ADDITIVE_METRICS = [
    'clueReceipts',
    'outboundCalls',
    'connectedCalls',
    'callMinutes',
    'wecomInteractions',
    'followedUp',
  ];

  function number(value) {
    return Number.isFinite(Number(value)) ? Number(value) : 0;
  }

  function safeRate(numerator, denominator) {
    return denominator > 0 ? numerator / denominator : null;
  }

  function compositeEffort(row) {
    return Math.round(100 * (
      number(row.normalizedCallMinutes) * 0.30
      + number(row.normalizedReachedUsers) * 0.25
      + number(row.normalizedOutboundCalls) * 0.20
      + number(row.normalizedWecomInteractions) * 0.15
      + number(row.normalizedClueReceipts) * 0.10
    ));
  }

  function applyFilters(dataset, filters) {
    const rows = Array.isArray(dataset) ? dataset : ((dataset && dataset.dailyFacts) || []);
    const active = filters || {};
    const scalarDimensions = ['teamId', 'salespersonId', 'stage', 'grade', 'userLayer', 'userId'];
    return rows.filter((row) => {
      if (active.date && row.date !== active.date) return false;
      if (active.dateFrom && row.date < active.dateFrom) return false;
      if (active.dateTo && row.date > active.dateTo) return false;
      for (const dimension of scalarDimensions) {
        const expected = active[dimension];
        if (expected == null || expected === '' || expected === 'all') continue;
        if (Array.isArray(expected) && !expected.includes(row[dimension])) return false;
        if (!Array.isArray(expected) && row[dimension] !== expected) return false;
      }
      return true;
    });
  }

  function aggregateSummary(rows) {
    const summary = Object.fromEntries(ADDITIVE_METRICS.map((metric) => [metric, 0]));
    const users = new Set();
    const clueUsers = new Set();
    const outboundUsers = new Set();
    const reachedUsers = new Set();
    const wecomUsers = new Set();
    const followedUpUsers = new Set();
    const salespeople = new Set();
    (rows || []).forEach((row) => {
      ADDITIVE_METRICS.forEach((metric) => {
        summary[metric] += number(row[metric]);
      });
      if (row.userId != null) users.add(row.userId);
      if (row.salespersonId != null) salespeople.add(row.salespersonId);
      if (number(row.clueReceipts) > 0 && row.userId != null) clueUsers.add(row.userId);
      if (number(row.outboundCalls) > 0 && row.userId != null) outboundUsers.add(row.userId);
      if (number(row.connectedCalls) > 0 && row.userId != null) reachedUsers.add(row.userId);
      if (number(row.wecomInteractions) > 0 && row.userId != null) wecomUsers.add(row.userId);
      if (number(row.followedUp) > 0 && row.userId != null) followedUpUsers.add(row.userId);
    });
    summary.userCount = users.size;
    summary.clueUsers = clueUsers.size;
    summary.outboundUsers = outboundUsers.size;
    summary.reachedUsers = reachedUsers.size;
    summary.wecomUsers = wecomUsers.size;
    summary.followedUpUsers = followedUpUsers.size;
    summary.salespersonCount = salespeople.size;
    summary.connectionRateByCalls = safeRate(summary.connectedCalls, summary.outboundCalls);
    summary.connectionRateByUsers = safeRate(summary.reachedUsers, summary.outboundUsers);
    summary.connectionRate = summary.connectionRateByUsers;
    summary.followupRate = safeRate(summary.followedUpUsers, summary.reachedUsers);
    summary.callsPerContactedUser = safeRate(summary.outboundCalls, summary.outboundUsers);
    summary.minutesPerReachedUser = safeRate(summary.callMinutes, summary.reachedUsers);
    return summary;
  }

  function summaryMetric(summary, metric) {
    return Object.hasOwn(summary, metric) ? summary[metric] : 0;
  }

  function groupRows(rows, keyBuilder) {
    const groups = new Map();
    (rows || []).forEach((row) => {
      const key = keyBuilder(row);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(row);
    });
    return groups;
  }

  function effortMaxima(items) {
    const metrics = ['callMinutes', 'reachedUsers', 'outboundCalls', 'wecomInteractions', 'clueReceipts'];
    return Object.fromEntries(metrics.map((metric) => [
      metric,
      Math.max(0, ...items.map((item) => number(item.summary[metric]))),
    ]));
  }

  function normalized(value, maximum) {
    return maximum > 0 ? value / maximum : 0;
  }

  function addEffortScores(items) {
    const maxima = effortMaxima(items);
    return items.map((item) => ({
      ...item,
      effortScore: compositeEffort({
        normalizedCallMinutes: normalized(item.summary.callMinutes, maxima.callMinutes),
        normalizedReachedUsers: normalized(item.summary.reachedUsers, maxima.reachedUsers),
        normalizedOutboundCalls: normalized(item.summary.outboundCalls, maxima.outboundCalls),
        normalizedWecomInteractions: normalized(item.summary.wecomInteractions, maxima.wecomInteractions),
        normalizedClueReceipts: normalized(item.summary.clueReceipts, maxima.clueReceipts),
      }),
    }));
  }

  function groupMetrics(rows, keyBuilder, dimensions, metric) {
    const groups = groupRows(rows, keyBuilder);
    let items = Array.from(groups.values(), (group) => ({
      ...dimensions(group[0]),
      summary: aggregateSummary(group),
    }));
    if (metric === 'effortScore') items = addEffortScores(items);
    return items.map((item) => ({
      ...item,
      value: metric === 'effortScore' ? item.effortScore : summaryMetric(item.summary, metric),
    }));
  }

  function buildHeatmap(rows, metric) {
    return groupMetrics(
      rows,
      (row) => `${row.stage}\u0000${row.userLayer}`,
      (row) => ({ stage: row.stage, userLayer: row.userLayer }),
      metric,
    ).sort((a, b) => (
      String(a.stage).localeCompare(String(b.stage), 'zh-CN')
      || String(a.userLayer).localeCompare(String(b.userLayer), 'zh-CN')
    ));
  }

  function buildTrend(rows, metric) {
    return groupMetrics(rows, (row) => row.date, (row) => ({ date: row.date }), metric)
      .sort((a, b) => String(a.date).localeCompare(String(b.date)));
  }

  function rankSalespeople(rows) {
    const groups = groupRows(rows, (row) => row.salespersonId);
    const summaries = Array.from(groups.values(), (group) => ({
      salespersonId: group[0].salespersonId,
      teamId: group[0].teamId,
      summary: aggregateSummary(group),
    }));
    return addEffortScores(summaries)
      .sort((a, b) => b.effortScore - a.effortScore || String(a.salespersonId).localeCompare(String(b.salespersonId)));
  }

  function anomaly(type, row, details) {
    return {
      id: `${type}-${row.date || 'period'}-${row.salespersonId || 'all'}-${row.userId || row.stage || 'group'}`,
      type,
      date: row.date || null,
      teamId: row.teamId || null,
      salespersonId: row.salespersonId || null,
      userId: row.userId || null,
      stage: row.stage || null,
      userLayer: row.userLayer || null,
      ...details,
    };
  }

  function detectAnomalies(rows) {
    const input = rows || [];
    if (!input.length) return [];
    const anomalies = [];

    input.forEach((row) => {
      if (row.userLayer === '定金高净值' && number(row.outboundCalls) > 0 && number(row.connectedCalls) === 0) {
        anomalies.push(anomaly('high_value_unreached', row, { severity: 'high', value: number(row.outboundCalls) }));
      }
      if (number(row.connectedCalls) > 0 && number(row.followedUp) === 0) {
        anomalies.push(anomaly('connected_without_followup', row, { severity: 'medium', value: number(row.connectedCalls) }));
      }
      if (number(row.outboundCalls) > 0 && number(row.connectedCalls) === 0 && number(row.outboundCalls) <= 1) {
        anomalies.push(anomaly('low_effective_depth', row, {
          severity: 'medium',
          value: number(row.outboundCalls),
          label: '未接通用户拨打不足',
          description: '未接通用户的外呼次数低于 2 次',
        }));
      }
    });

    const byPerson = groupRows(input, (row) => row.salespersonId || 'all');
    byPerson.forEach((personRows, salespersonId) => {
      const stageGroups = groupRows(personRows, (row) => row.stage || '未知');
      const stageCalls = Array.from(stageGroups, ([stage, group]) => ({ stage, calls: aggregateSummary(group).outboundCalls }));
      const totalCalls = stageCalls.reduce((sum, item) => sum + item.calls, 0);
      const dominant = stageCalls.sort((a, b) => b.calls - a.calls)[0];
      if (dominant && totalCalls >= 8 && dominant.calls / totalCalls >= 0.75) {
        anomalies.push(anomaly('single_stage_concentration', personRows[0], {
          salespersonId,
          stage: dominant.stage,
          severity: 'low',
          value: dominant.calls / totalCalls,
        }));
      }

      const dates = [...new Set(personRows.map((row) => row.date))].sort();
      const latestDate = dates[dates.length - 1];
      if (dates.length < 2) return;
      const latestRows = personRows.filter((row) => row.date === latestDate);
      const priorRows = personRows.filter((row) => row.date !== latestDate);
      const latestTotal = aggregateSummary(latestRows).outboundCalls;
      const priorTotal = aggregateSummary(priorRows).outboundCalls;
      if (priorTotal <= 0) return;
      const stages = new Set(personRows.map((row) => row.stage));
      stages.forEach((stage) => {
        const priorStageCalls = aggregateSummary(priorRows.filter((row) => row.stage === stage)).outboundCalls;
        const latestStageCalls = aggregateSummary(latestRows.filter((row) => row.stage === stage)).outboundCalls;
        const priorShare = safeRate(priorStageCalls, priorTotal) || 0;
        const latestShare = safeRate(latestStageCalls, latestTotal) || 0;
        if (priorStageCalls >= 4 && priorShare - latestShare >= 0.2) {
          anomalies.push(anomaly('share_drop', personRows[0], {
            date: latestDate,
            salespersonId,
            stage,
            severity: 'medium',
            value: latestShare - priorShare,
            previousShare: priorShare,
            currentShare: latestShare,
          }));
        }
      });
    });

    return anomalies;
  }

  return {
    safeRate,
    compositeEffort,
    applyFilters,
    aggregateSummary,
    buildHeatmap,
    buildTrend,
    rankSalespeople,
    detectAnomalies,
  };
}));
