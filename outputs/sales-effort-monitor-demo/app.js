(function () {
  'use strict';

  const METRIC_OPTIONS = [
    { key: 'effortScore', label: '综合精力', unit: '分' },
    { key: 'reachedUsers', label: '触达用户', unit: '人' },
    { key: 'outboundCalls', label: '外呼次数', unit: '次' },
    { key: 'callMinutes', label: '通话时长', unit: '分钟' },
    { key: 'wecomInteractions', label: '企微互动', unit: '次' },
  ];
  const ANOMALY_META = {
    high_value_unreached: ['高价值用户未触达', '已外呼但尚未接通，建议优先再次联系'],
    connected_without_followup: ['接通后未跟进', '已经接通，但没有后续跟进记录'],
    low_effective_depth: ['未接通用户拨打不足', '未接通用户仅外呼 1 次'],
    single_stage_concentration: ['精力集中于单一学段', '该销售多数外呼集中在一个学段'],
    share_drop: ['学段精力占比下降', '相较前期，该学段外呼占比明显下降'],
  };
  const USER_SURNAMES = ['陈', '林', '王', '李', '赵', '周', '吴', '徐', '孙', '胡'];

  const state = {
    date: null,
    window: 1,
    teamId: 'all',
    salespersonId: 'all',
    stage: 'all',
    userLayer: 'all',
    metric: 'effortScore',
    heatCell: null,
    anomalyLimit: 5,
    drawerOpen: false,
    drawerQuery: '',
  };
  let dataset;
  let Data;
  let Metrics;
  let lastFocusedElement = null;

  const $ = (selector) => document.querySelector(selector);
  const byId = (id) => document.getElementById(id);
  const formatNumber = (value, digits) => new Intl.NumberFormat('zh-CN', {
    maximumFractionDigits: digits == null ? 0 : digits,
    minimumFractionDigits: digits == null ? 0 : digits,
  }).format(Number(value) || 0);
  const formatPercent = (value, digits) => value == null ? '—' : `${formatNumber(value * 100, digits == null ? 1 : digits)}%`;
  const formatDate = (date) => `${Number(date.slice(5, 7))}月${Number(date.slice(8, 10))}日`;
  const unique = (items) => [...new Set(items)];

  function optionList(items, allLabel, selected, valueKey, labelKey) {
    const all = `<option value="all">${allLabel}</option>`;
    return all + items.map((item) => {
      const value = valueKey ? item[valueKey] : item;
      const label = labelKey ? item[labelKey] : item;
      return `<option value="${escapeHtml(value)}"${value === selected ? ' selected' : ''}>${escapeHtml(label)}</option>`;
    }).join('');
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>'"]/g, (character) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
    }[character]));
  }

  function teamName(id) {
    return dataset.teams.find((team) => team.id === id)?.name || '全部团队';
  }

  function salespersonName(id) {
    return dataset.salespeople.find((person) => person.id === id)?.name || '全部销售';
  }

  function baseDimensionFilters() {
    return {
      teamId: state.teamId,
      salespersonId: state.salespersonId,
      stage: state.stage,
      userLayer: state.userLayer,
    };
  }

  function intersectRows(rows, filters, heatCell, applyFilters) {
    const baseRows = applyFilters(rows, filters || {});
    return heatCell ? applyFilters(baseRows, heatCell) : baseRows;
  }

  function periodDates(offset) {
    const endIndex = dataset.dates.indexOf(state.date) - (offset || 0);
    const startIndex = Math.max(0, endIndex - state.window + 1);
    if (endIndex < 0) return [];
    return dataset.dates.slice(startIndex, endIndex + 1);
  }

  function filterPeriodRows(rows, dates, filters, heatCell, applyFilters) {
    const dateSet = new Set(dates);
    const periodRows = rows.filter((row) => dateSet.has(row.date));
    return intersectRows(periodRows, filters, heatCell, applyFilters);
  }

  function rowsForPeriod(offset, includeHeatCell) {
    return filterPeriodRows(
      dataset.dailyFacts,
      periodDates(offset),
      baseDimensionFilters(),
      includeHeatCell === false ? null : state.heatCell,
      Metrics.applyFilters,
    );
  }

  function allTrendRows() {
    return intersectRows(dataset.dailyFacts, baseDimensionFilters(), state.heatCell, Metrics.applyFilters);
  }

  function metricValue(item, metric) {
    return metric === 'effortScore' ? item.effortScore : item.summary[metric];
  }

  function compare(current, previous, inverse) {
    if (!previous) return { className: 'change-flat', text: '暂无对比' };
    const delta = (current - previous) / previous;
    const direction = delta > 0.005 ? '↑' : delta < -0.005 ? '↓' : '—';
    const positive = inverse ? delta < 0 : delta > 0;
    return {
      className: Math.abs(delta) <= 0.005 ? 'change-flat' : positive ? 'change-up' : 'change-down',
      text: `${direction} ${formatPercent(Math.abs(delta), 1)} 较前期`,
    };
  }

  function renderFilters() {
    byId('filter-date').innerHTML = dataset.dates.map((date) => `<option value="${date}"${date === state.date ? ' selected' : ''}>${formatDate(date)}</option>`).join('');
    byId('filter-window').value = String(state.window);
    byId('filter-team').innerHTML = optionList(dataset.teams, '全部团队', state.teamId, 'id', 'name');
    const people = state.teamId === 'all' ? dataset.salespeople : dataset.salespeople.filter((person) => person.teamId === state.teamId);
    byId('filter-salesperson').innerHTML = optionList(people, '全部销售', state.salespersonId, 'id', 'name');
    byId('filter-stage').innerHTML = optionList(Data.dimensions.stages, '全部学段', state.stage);
    byId('filter-layer').innerHTML = optionList(Data.dimensions.userLayers, '全部用户分层', state.userLayer);

    const labels = [state.window === 1 ? formatDate(state.date) : `${formatDate(periodDates()[0])}—${formatDate(state.date)}`];
    if (state.teamId !== 'all') labels.push(teamName(state.teamId));
    if (state.salespersonId !== 'all') labels.push(salespersonName(state.salespersonId));
    if (state.stage !== 'all') labels.push(state.stage);
    if (state.userLayer !== 'all') labels.push(state.userLayer);
    if (state.heatCell) labels.push(`${state.heatCell.stage} × ${state.heatCell.userLayer}`);
    byId('filter-summary').textContent = `当前范围：${labels.join(' · ')}`;
    byId('period-label').textContent = state.window === 1 ? '与上一日比较' : `与前 ${state.window} 日比较`;
    byId('data-status').textContent = `${formatDate(dataset.dates.at(-1))} 演示快照`;
  }

  function renderKpis(rows) {
    const summary = Metrics.aggregateSummary(rows);
    const previous = Metrics.aggregateSummary(rowsForPeriod(state.window));
    const activeSales = summary.salespersonCount;
    const kpis = [
      ['活跃销售', activeSales, '人', compare(activeSales, previous.salespersonCount)],
      ['领取用户', summary.clueUsers, '人', compare(summary.clueUsers, previous.clueUsers)],
      ['外呼覆盖率', summary.outboundUsers / Math.max(summary.userCount, 1), '%', compare(summary.outboundUsers / Math.max(summary.userCount, 1), previous.outboundUsers / Math.max(previous.userCount, 1))],
      ['接通率', summary.connectionRate, '%', compare(summary.connectionRate || 0, previous.connectionRate || 0)],
      ['人均外呼次数', summary.callsPerContactedUser, '次', compare(summary.callsPerContactedUser || 0, previous.callsPerContactedUser || 0)],
      ['平均沟通时长', summary.minutesPerReachedUser, '分钟', compare(summary.minutesPerReachedUser || 0, previous.minutesPerReachedUser || 0)],
    ];
    byId('kpi-strip').innerHTML = kpis.map(([label, value, unit, change]) => {
      const shown = unit === '%' ? formatPercent(value, 1) : `${formatNumber(value, unit === '人' ? 0 : 1)}${unit}`;
      return `<article class="kpi-card"><span class="kpi-label">${label}</span><strong>${shown}</strong><span class="kpi-change ${change.className}">${change.text}</span></article>`;
    }).join('');
  }

  function heatColor(value, maximum) {
    const ratio = maximum ? value / maximum : 0;
    const start = [237, 247, 247];
    const end = [65, 174, 179];
    const mix = Math.max(0.06, ratio);
    return `rgb(${start.map((channel, index) => Math.round(channel + (end[index] - channel) * mix)).join(',')})`;
  }

  function renderHeatmap(rows) {
    const metric = METRIC_OPTIONS.find((item) => item.key === state.metric);
    const values = Metrics.buildHeatmap(rows, state.metric);
    const lookup = new Map(values.map((item) => [`${item.stage}|${item.userLayer}`, item]));
    const maximum = Math.max(0, ...values.map((item) => item.value));
    const stageHeaders = Data.dimensions.stages.map((stage) => `<div class="heat-col">${stage}</div>`).join('');
    const cells = Data.dimensions.userLayers.map((layer) => {
      const row = Data.dimensions.stages.map((stage) => {
        const item = lookup.get(`${stage}|${layer}`);
        const value = item?.value || 0;
        const selected = state.heatCell?.stage === stage && state.heatCell?.userLayer === layer;
        const title = `${stage} · ${layer}：${formatNumber(value, metric.key === 'callMinutes' ? 1 : 0)}${metric.unit}`;
        return `<button type="button" class="heat-cell${selected ? ' selected' : ''}" style="background:${heatColor(value, maximum)}" data-stage="${stage}" data-layer="${layer}" title="${title}" aria-label="${title}"><strong>${formatNumber(value, metric.key === 'callMinutes' ? 1 : 0)}</strong><span>${metric.unit}</span></button>`;
      }).join('');
      return `<div class="heat-row">${layer}</div>${row}`;
    }).join('');
    byId('effort-heatmap').innerHTML = `
      <div class="panel-title"><div><h2>精力结构</h2><p>点击格子联动趋势、异常和销售排行</p></div><div class="metric-tabs" role="tablist">${METRIC_OPTIONS.map((item) => `<button type="button" role="tab" data-metric="${item.key}" class="${item.key === state.metric ? 'active' : ''}" aria-selected="${item.key === state.metric}">${item.label}</button>`).join('')}</div></div>
      <div class="heatmap-wrap"><div class="heatmap"><div class="heat-corner">用户分层 / 学段</div>${stageHeaders}${cells}</div></div>
      <div class="heat-legend"><span>较少</span><span class="legend-scale"><i></i><i></i><i></i><i></i></span><span>较多</span>${state.metric === 'effortScore' ? '<span>· 综合精力按通话、触达、外呼、企微、领取加权</span>' : ''}</div>`;
  }

  function anomalyDescription(item) {
    const meta = ANOMALY_META[item.type] || ['需要关注', '该范围出现异常变化'];
    const who = item.salespersonId ? salespersonName(item.salespersonId) : teamName(item.teamId);
    const context = [who, item.stage, item.userLayer].filter(Boolean).join(' · ');
    return { title: meta[0], description: `${context ? `${context}，` : ''}${item.description || meta[1]}` };
  }

  function renderAnomalies(rows) {
    const severityOrder = { high: 0, medium: 1, low: 2 };
    const anomalies = Metrics.detectAnomalies(rows).sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity]);
    const shown = anomalies.slice(0, state.anomalyLimit);
    const content = shown.length ? shown.map((item) => {
      const copy = anomalyDescription(item);
      return `<button type="button" class="anomaly-item severity-${item.severity}" data-team="${item.teamId || ''}" data-salesperson="${item.salespersonId || ''}" data-stage="${item.stage || ''}" data-layer="${item.userLayer || ''}" data-anomaly="${item.type}"><span class="severity-bar"></span><span><strong>${copy.title}</strong><p>${escapeHtml(copy.description)}</p></span><time>${item.date ? formatDate(item.date) : '本期'}</time></button>`;
    }).join('') : '<div class="empty-state"><strong>当前范围没有明显异常</strong><span>可扩大观察窗口或清空筛选</span></div>';
    const hasMore = anomalies.length > shown.length;
    byId('anomaly-list').innerHTML = `<div class="panel-title"><div><h2>需要关注</h2><p>${anomalies.length} 条信号，按紧急程度排序</p></div><span class="anomaly-count" aria-live="polite">已展示 ${shown.length} / ${anomalies.length} 条</span></div><div class="anomaly-stack" id="anomaly-stack" role="list">${content}</div>${hasMore ? `<button type="button" class="anomaly-more" data-action="more-anomalies" aria-controls="anomaly-stack" aria-expanded="false">再看 ${Math.min(5, anomalies.length - shown.length)} 条</button>` : ''}`;
  }

  function trendSvg(points) {
    const width = 1000;
    const height = 242;
    const margin = { top: 18, right: 26, bottom: 36, left: 45 };
    const values = points.map((point) => point.value || 0);
    const maximum = Math.max(1, ...values) * 1.12;
    const baseline = values.reduce((sum, value) => sum + value, 0) / Math.max(values.length, 1);
    const x = (index) => margin.left + index * ((width - margin.left - margin.right) / Math.max(points.length - 1, 1));
    const y = (value) => margin.top + (maximum - value) / maximum * (height - margin.top - margin.bottom);
    const line = points.map((point, index) => `${index ? 'L' : 'M'}${x(index).toFixed(1)},${y(point.value).toFixed(1)}`).join(' ');
    const area = `${line} L${x(points.length - 1)},${height - margin.bottom} L${x(0)},${height - margin.bottom} Z`;
    const grids = [0, .25, .5, .75, 1].map((ratio) => {
      const gridY = y(maximum * ratio);
      return `<line class="grid-line" x1="${margin.left}" y1="${gridY}" x2="${width - margin.right}" y2="${gridY}"/><text class="axis-label" x="${margin.left - 9}" y="${gridY + 3}" text-anchor="end">${formatNumber(maximum * ratio, 0)}</text>`;
    }).join('');
    const labels = points.map((point, index) => index % 2 === 0 || index === points.length - 1 ? `<text class="axis-label" x="${x(index)}" y="${height - 13}" text-anchor="middle">${point.date.slice(5).replace('-', '/')}</text>` : '').join('');
    const dots = points.map((point, index) => `<circle class="trend-dot" cx="${x(index)}" cy="${y(point.value)}" r="3"><title>${formatDate(point.date)}：${formatNumber(point.value, state.metric === 'callMinutes' ? 1 : 0)}</title></circle>`).join('');
    return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="14天精力趋势">${grids}<line class="baseline" x1="${margin.left}" y1="${y(baseline)}" x2="${width - margin.right}" y2="${y(baseline)}"/><path class="trend-area" d="${area}"/><path class="trend-line" d="${line}"/>${dots}${labels}</svg>`;
  }

  function renderTrend() {
    const metric = METRIC_OPTIONS.find((item) => item.key === state.metric);
    const points = Metrics.buildTrend(allTrendRows(), state.metric);
    byId('effort-trend').innerHTML = `<div class="panel-title"><div><h2>14 天变化趋势</h2><p>${metric.label} · 当前筛选范围</p></div></div>${points.length ? `<div class="trend-chart">${trendSvg(points)}</div><div class="trend-legend"><span>每日实际</span><span class="baseline-key">14 日均值</span></div>` : emptyState()}`;
  }

  function renderRanking(rows) {
    const ranking = Metrics.rankSalespeople(rows).slice(0, 12);
    const body = ranking.map((item, index) => {
      const summary = item.summary;
      return `<tr data-salesperson="${item.salespersonId}" tabindex="0" role="button" aria-label="查看 ${escapeHtml(salespersonName(item.salespersonId))} 的销售详情"><td class="rank-no">${String(index + 1).padStart(2, '0')}</td><td class="sales-name">${salespersonName(item.salespersonId)}</td><td>${teamName(item.teamId)}</td><td><span class="score-pill">${item.effortScore}</span></td><td>${summary.outboundUsers}</td><td>${summary.outboundCalls}</td><td>${formatPercent(summary.connectionRate)}</td><td>${formatNumber(summary.callMinutes, 1)}</td><td>${summary.wecomInteractions}</td></tr>`;
    }).join('');
    byId('sales-ranking').innerHTML = `<div class="panel-title"><div><h2>销售精力排行</h2><p>综合精力用于排序，点击姓名查看个人构成</p></div></div>${ranking.length ? `<div class="ranking-wrap"><table class="ranking-table"><thead><tr><th>排名</th><th>销售</th><th>团队</th><th>综合精力</th><th>外呼用户</th><th>外呼次数</th><th>接通率</th><th>通话分钟</th><th>企微互动</th></tr></thead><tbody>${body}</tbody></table></div>` : emptyState()}`;
  }

  function activeFilterSummary() {
    const labels = [];
    if (state.teamId !== 'all') labels.push(`团队：${teamName(state.teamId)}`);
    if (state.salespersonId !== 'all') labels.push(`销售：${salespersonName(state.salespersonId)}`);
    if (state.stage !== 'all') labels.push(`学段：${state.stage}`);
    if (state.userLayer !== 'all') labels.push(`用户分层：${state.userLayer}`);
    if (state.heatCell) labels.push(`热力格：${state.heatCell.stage} × ${state.heatCell.userLayer}`);
    return labels.length ? labels.join('；') : '当前日期与观察窗口';
  }

  function emptyState() {
    return `<div class="empty-state"><strong>当前筛选没有匹配数据</strong><span>可能冲突的条件：${escapeHtml(activeFilterSummary())}</span><button type="button" class="text-button" data-action="reset">清空筛选</button></div>`;
  }

  function distribution(rows, dimension, labels) {
    const total = Metrics.aggregateSummary(rows).outboundCalls;
    return labels.map((label) => {
      const value = Metrics.aggregateSummary(rows.filter((row) => row[dimension] === label)).outboundCalls;
      const share = total ? value / total : 0;
      return `<div class="distribution-row"><span>${label}</span><i style="width:${Math.max(2, share * 100)}%"></i><em>${formatPercent(share, 0)}</em></div>`;
    }).join('');
  }

  function userDisplayName(userId) {
    const number = Number(String(userId).replace(/\D/g, '')) || 0;
    return `${USER_SURNAMES[number % USER_SURNAMES.length]}同学家长`;
  }

  function effortComposition(summary) {
    const items = [
      ['通话时长', summary.callMinutes, '分钟', 30],
      ['触达用户', summary.reachedUsers, '人', 25],
      ['外呼次数', summary.outboundCalls, '次', 20],
      ['企微互动', summary.wecomInteractions, '次', 15],
      ['领取用户', summary.clueUsers, '人', 10],
    ];
    return items.map(([label, value, unit, weight]) => `<div class="composition-row"><span>${label}</span><i><b style="width:${weight * 2.6}%"></b></i><em>${formatNumber(value, label === '通话时长' ? 1 : 0)}${unit} · 权重 ${weight}%</em></div>`).join('');
  }

  function buildUserRows(rows) {
    const groups = new Map();
    rows.forEach((row) => {
      if (!groups.has(row.userId)) groups.set(row.userId, []);
      groups.get(row.userId).push(row);
    });
    const anomalyByUser = new Map();
    Metrics.detectAnomalies(rows).forEach((item) => {
      if (!item.userId) return;
      if (!anomalyByUser.has(item.userId)) anomalyByUser.set(item.userId, new Set());
      anomalyByUser.get(item.userId).add(item.type);
    });
    return Array.from(groups, ([userId, userRows]) => {
      const summary = Metrics.aggregateSummary(userRows);
      const anomalyTypes = [...(anomalyByUser.get(userId) || [])];
      return {
        userId,
        name: userDisplayName(userId),
        stage: userRows[0].stage,
        userLayer: userRows[0].userLayer,
        summary,
        anomalyTypes,
        anomalyLabels: anomalyTypes.map((type) => ANOMALY_META[type]?.[0] || type),
      };
    }).sort((a, b) => b.summary.outboundCalls - a.summary.outboundCalls || a.userId.localeCompare(b.userId));
  }

  function renderDrawer(focusTarget) {
    const drawer = byId('sales-drawer');
    if (!state.drawerOpen || state.salespersonId === 'all') {
      drawer.classList.remove('open');
      drawer.setAttribute('aria-hidden', 'true');
      byId('drawer-backdrop').hidden = true;
      return;
    }
    const person = dataset.salespeople.find((item) => item.id === state.salespersonId);
    if (!person) return;
    const rows = rowsForPeriod();
    const summary = Metrics.aggregateSummary(rows);
    const context = [];
    if (state.teamId !== 'all') context.push(teamName(state.teamId));
    if (state.stage !== 'all') context.push(state.stage);
    if (state.userLayer !== 'all') context.push(state.userLayer);
    if (state.heatCell) context.push(`${state.heatCell.stage} × ${state.heatCell.userLayer}`);
    const contextLabel = context.length ? context.join(' · ') : '全部学段 · 全部用户分层';
    const trendPoints = Metrics.buildTrend(allTrendRows(), state.metric);
    const allUsers = buildUserRows(rows);
    const query = state.drawerQuery.trim().toLowerCase();
    const users = allUsers.filter((user) => [user.name, user.userId, ...user.anomalyTypes, ...user.anomalyLabels].join(' ').toLowerCase().includes(query));
    const userBody = users.slice(0, 80).map((user) => `<tr><td><strong>${escapeHtml(user.name)}</strong><span>${escapeHtml(user.userId)}</span></td><td>${user.stage}</td><td>${user.userLayer}</td><td>${user.summary.outboundCalls}</td><td>${formatPercent(user.summary.connectionRate)}</td><td>${user.anomalyLabels.length ? user.anomalyLabels.map((label) => `<mark>${escapeHtml(label)}</mark>`).join('') : '<span class="status-normal">正常跟进</span>'}</td></tr>`).join('');
    drawer.innerHTML = `<div class="drawer-actions"><button type="button" class="back-button" data-action="back-overview">← 返回总览</button><button type="button" class="icon-button" data-action="close-drawer" aria-label="关闭详情" title="关闭">×</button></div>
      <div class="drawer-head"><div><span class="section-kicker">销售详情 · 当前筛选范围</span><h2>${escapeHtml(person.name)}</h2><p>${teamName(person.teamId)} · 销售编号 ${escapeHtml(person.id)}</p><p>${formatDate(periodDates()[0])}—${formatDate(state.date)}</p><p class="drawer-context">${escapeHtml(contextLabel)}</p></div></div>
      <div class="drawer-kpis"><div><span>综合精力</span><strong>${Metrics.rankSalespeople(rows)[0]?.effortScore || 0}</strong></div><div><span>外呼用户</span><strong>${summary.outboundUsers}</strong></div><div><span>外呼次数</span><strong>${summary.outboundCalls}</strong></div><div><span>接通率</span><strong>${formatPercent(summary.connectionRate)}</strong></div><div><span>通话分钟</span><strong>${formatNumber(summary.callMinutes, 1)}</strong></div><div><span>企微互动</span><strong>${summary.wecomInteractions}</strong></div></div>
      <section class="mini-section"><h3>精力构成</h3><p class="section-note">实际投入与综合精力权重</p>${effortComposition(summary)}</section>
      <section class="mini-section"><h3>学段精力分布</h3>${distribution(rows, 'stage', Data.dimensions.stages)}</section>
      <section class="mini-section"><h3>用户分层分布</h3>${distribution(rows, 'userLayer', Data.dimensions.userLayers)}</section>
      <section class="mini-section"><h3>14 天趋势</h3><p class="section-note">${METRIC_OPTIONS.find((item) => item.key === state.metric).label}</p>${trendPoints.length ? `<div class="drawer-trend">${trendSvg(trendPoints)}</div>` : emptyState()}</section>
      <section class="mini-section user-detail"><div class="user-detail-head"><div><h3>用户明细</h3><p class="section-note">${users.length} / ${allUsers.length} 位用户</p></div><label><span class="sr-only">搜索用户</span><input id="drawer-search" type="search" value="${escapeHtml(state.drawerQuery)}" placeholder="搜索姓名、用户ID、异常类型"></label></div>${userBody ? `<div class="user-table-wrap"><table class="user-table"><thead><tr><th>用户</th><th>学段</th><th>分层</th><th>外呼</th><th>接通率</th><th>异常</th></tr></thead><tbody>${userBody}</tbody></table></div>` : '<div class="drawer-empty">没有匹配的用户，请换个关键词</div>'}</section>`;
    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
    byId('drawer-backdrop').hidden = false;
    if (focusTarget) requestAnimationFrame(() => drawer.querySelector(focusTarget)?.focus());
  }

  function openSalesperson(id, trigger) {
    const person = dataset.salespeople.find((item) => item.id === id);
    if (!person) return;
    lastFocusedElement = trigger || document.activeElement;
    setFilters({ teamId: person.teamId, salespersonId: id, drawerOpen: true, drawerQuery: '' }, { drawerFocus: '[data-action="close-drawer"]' });
  }

  function closeDrawer() {
    const returnTarget = lastFocusedElement;
    lastFocusedElement = null;
    setFilters({ drawerOpen: false, drawerQuery: '' }, { drawerOnly: true });
    requestAnimationFrame(() => {
      if (returnTarget && document.contains(returnTarget)) returnTarget.focus();
      else {
        const salespersonId = returnTarget?.dataset?.salesperson;
        const matchingRow = [...document.querySelectorAll('#sales-ranking [data-salesperson]')].find((row) => row.dataset.salesperson === salespersonId);
        (matchingRow || byId('filter-salesperson')).focus();
      }
    });
  }

  function backToOverview() {
    lastFocusedElement = null;
    setFilters({ salespersonId: 'all', drawerOpen: false, drawerQuery: '' });
    requestAnimationFrame(() => byId('filter-salesperson').focus());
  }

  function render() {
    try {
      renderFilters();
      const baseRows = rowsForPeriod(0, false);
      const linkedRows = intersectRows(baseRows, {}, state.heatCell, Metrics.applyFilters);
      renderKpis(linkedRows);
      renderHeatmap(baseRows);
      if (linkedRows.length) renderAnomalies(linkedRows);
      else byId('anomaly-list').innerHTML = `<div class="panel-title"><div><h2>需要关注</h2><p>当前范围</p></div></div>${emptyState()}`;
      renderTrend();
      renderRanking(linkedRows);
      renderDrawer();
    } catch (error) {
      console.error(error);
      document.querySelector('main').innerHTML = `<div class="error-state"><strong>演示数据未能加载</strong><span>请重新打开页面</span><button type="button" class="text-button" onclick="location.reload()">重新加载</button></div>`;
    }
  }

  function setFilters(patch, options) {
    Object.assign(state, patch || {});
    if (patch && Object.keys(patch).some((key) => ['teamId', 'salespersonId', 'stage', 'userLayer', 'date', 'window', 'heatCell'].includes(key))) {
      state.anomalyLimit = 5;
    }
    if (state.teamId !== 'all' && state.salespersonId !== 'all') {
      const person = dataset.salespeople.find((item) => item.id === state.salespersonId);
      if (!person || person.teamId !== state.teamId) {
        state.salespersonId = 'all';
        state.drawerOpen = false;
      }
    }
    if (state.salespersonId === 'all' && !(patch && patch.drawerOpen)) state.drawerOpen = false;
    if (options?.drawerOnly) renderDrawer(options.drawerFocus);
    else {
      render();
      if (options?.drawerFocus) renderDrawer(options.drawerFocus);
    }
  }

  function selectHeatCell(cell) {
    const same = state.heatCell && state.heatCell.stage === cell.stage && state.heatCell.userLayer === cell.userLayer;
    setFilters({ heatCell: same ? null : { stage: cell.stage, userLayer: cell.userLayer } });
  }

  function resetFilters() {
    setFilters({
      date: dataset.dates.at(-1), window: 1, teamId: 'all', salespersonId: 'all', stage: 'all', userLayer: 'all', metric: 'effortScore', heatCell: null, anomalyLimit: 5, drawerOpen: false, drawerQuery: '',
    });
  }

  function bindEvents() {
    byId('filter-date').addEventListener('change', (event) => setFilters({ date: event.target.value }));
    byId('filter-window').addEventListener('change', (event) => setFilters({ window: Number(event.target.value) }));
    byId('filter-team').addEventListener('change', (event) => setFilters({ teamId: event.target.value }));
    byId('filter-salesperson').addEventListener('change', (event) => setFilters({ salespersonId: event.target.value }));
    byId('filter-stage').addEventListener('change', (event) => setFilters({ stage: event.target.value }));
    byId('filter-layer').addEventListener('change', (event) => setFilters({ userLayer: event.target.value }));
    byId('reset-filters').addEventListener('click', resetFilters);
    byId('drawer-backdrop').addEventListener('click', closeDrawer);
    document.addEventListener('click', (event) => {
      const metric = event.target.closest('[data-metric]');
      if (metric) setFilters({ metric: metric.dataset.metric });
      const heatCell = event.target.closest('.heat-cell');
      if (heatCell) selectHeatCell({ stage: heatCell.dataset.stage, userLayer: heatCell.dataset.layer });
      const ranking = event.target.closest('#sales-ranking [data-salesperson]');
      if (ranking) openSalesperson(ranking.dataset.salesperson, ranking);
      const anomaly = event.target.closest('.anomaly-item');
      if (anomaly) {
        lastFocusedElement = anomaly;
        const patch = {
          teamId: anomaly.dataset.team || 'all',
          salespersonId: anomaly.dataset.salesperson || 'all',
          stage: anomaly.dataset.stage || 'all',
          userLayer: anomaly.dataset.layer || 'all',
          heatCell: null,
          drawerQuery: anomaly.dataset.anomaly || '',
          drawerOpen: Boolean(anomaly.dataset.salesperson),
        };
        setFilters(patch, patch.drawerOpen ? { drawerFocus: '[data-action="close-drawer"]' } : undefined);
        if (!patch.drawerOpen) requestAnimationFrame(() => byId('sales-ranking').scrollIntoView({ behavior: 'smooth', block: 'start' }));
      }
      const action = event.target.closest('[data-action]')?.dataset.action;
      if (action === 'more-anomalies') setFilters({ anomalyLimit: state.anomalyLimit + 5 });
      if (action === 'reset') resetFilters();
      if (action === 'close-drawer') closeDrawer();
      if (action === 'back-overview') backToOverview();
    });
    document.addEventListener('input', (event) => {
      if (event.target.id !== 'drawer-search') return;
      const cursor = event.target.selectionStart;
      setFilters({ drawerQuery: event.target.value }, { drawerOnly: true, drawerFocus: '#drawer-search' });
      requestAnimationFrame(() => {
        const input = byId('drawer-search');
        if (input) input.setSelectionRange(cursor, cursor);
      });
    });
    document.addEventListener('keydown', (event) => {
      const ranking = event.target.closest?.('#sales-ranking [data-salesperson]');
      if (ranking && (event.key === 'Enter' || event.key === ' ')) {
        event.preventDefault();
        openSalesperson(ranking.dataset.salesperson, ranking);
        return;
      }
      if (!state.drawerOpen) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        closeDrawer();
        return;
      }
      if (event.key !== 'Tab') return;
      const focusable = [...byId('sales-drawer').querySelectorAll('button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])')];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
  }

  function init() {
    Data = window.SalesEffortData;
    Metrics = window.SalesEffortMetrics;
    if (!Data || !Metrics) throw new Error('Missing local data modules');
    dataset = Data.generate('sales-effort-demo');
    state.date = dataset.dates.at(-1);
    bindEvents();
    render();
  }

  window.SalesEffortApp = {
    render, setFilters, selectHeatCell, openSalesperson, resetFilters, intersectRows, filterPeriodRows, state,
  };
  window.addEventListener('DOMContentLoaded', init);
}());
