(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.SalesEffortData = api;
  }
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const TEAM_DEFINITIONS = [
    { id: 'team-1', name: '启航一组', scenario: 'stable' },
    { id: 'team-2', name: '卓越二组', scenario: 'highValueFocus' },
    { id: 'team-3', name: '成长三组', scenario: 'lowPrimaryUnderweight' },
    { id: 'team-4', name: '远航四组', scenario: 'followupGap' },
  ];
  const STAGES = ['小低', '小高', '初中', '高中'];
  const GRADES = {
    小低: ['一年级', '二年级', '三年级'],
    小高: ['四年级', '五年级', '六年级'],
    初中: ['初一', '初二', '初三'],
    高中: ['高一', '高二', '高三'],
  };
  const USER_LAYERS = ['定金高净值', '定金蓄水', '定金其他', '其他蓄水', '其他付费', '老未新增'];
  const SURNAMES = ['陈', '林', '王', '李', '赵', '周', '吴', '徐', '孙', '胡', '朱', '高'];
  const GIVEN_NAMES = ['晨', '悦', '宁', '航', '佳', '宇', '楠', '欣', '然', '琪', '睿', '彤'];

  function hashSeed(seed) {
    const text = String(seed == null ? 'sales-effort-demo' : seed);
    let hash = 2166136261;
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
  }

  function createRandom(seed) {
    let state = hashSeed(seed) || 0x6d2b79f5;
    return function random() {
      state += 0x6d2b79f5;
      let value = state;
      value = Math.imul(value ^ (value >>> 15), value | 1);
      value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
      return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
    };
  }

  function probability(random, chance) {
    return random() < Math.max(0, Math.min(1, chance));
  }

  function makeDates() {
    return Array.from({ length: 14 }, (_, index) => `2026-07-${String(index + 1).padStart(2, '0')}`);
  }

  function scenarioMultiplier(scenario, stage, userLayer) {
    if (scenario === 'highValueFocus') {
      return userLayer === '定金高净值' ? 1.6 : 0.9;
    }
    if (scenario === 'lowPrimaryUnderweight') {
      return stage === '小低' ? 0.58 : 1.08;
    }
    return 1;
  }

  function generate(seed) {
    const random = createRandom(seed);
    const dates = makeDates();
    const teams = TEAM_DEFINITIONS.map((team) => ({ ...team }));
    const salespeople = [];

    teams.forEach((team, teamIndex) => {
      for (let memberIndex = 0; memberIndex < 6; memberIndex += 1) {
        const globalIndex = teamIndex * 6 + memberIndex;
        salespeople.push({
          id: `sales-${String(globalIndex + 1).padStart(2, '0')}`,
          name: `${SURNAMES[globalIndex % SURNAMES.length]}${GIVEN_NAMES[(globalIndex * 5 + 2) % GIVEN_NAMES.length]}`,
          teamId: team.id,
          scenario: team.scenario,
        });
      }
    });

    const users = Array.from({ length: 600 }, (_, userIndex) => {
      const salesperson = salespeople[userIndex % salespeople.length];
      const stage = STAGES[(userIndex * 7 + Math.floor(userIndex / 24)) % STAGES.length];
      const gradeList = GRADES[stage];
      const layerRoll = random();
      let layerIndex;
      if (layerRoll < 0.12) layerIndex = 0;
      else if (layerRoll < 0.24) layerIndex = 1;
      else if (layerRoll < 0.34) layerIndex = 2;
      else if (layerRoll < 0.51) layerIndex = 3;
      else if (layerRoll < 0.76) layerIndex = 4;
      else layerIndex = 5;
      return {
        id: `user-${String(userIndex + 1).padStart(3, '0')}`,
        teamId: salesperson.teamId,
        salespersonId: salesperson.id,
        stage,
        grade: gradeList[userIndex % gradeList.length],
        userLayer: USER_LAYERS[layerIndex],
      };
    });

    const peopleById = Object.fromEntries(salespeople.map((person) => [person.id, person]));
    const dailyFacts = [];
    dates.forEach((date, dayIndex) => {
      users.forEach((user, userIndex) => {
        const person = peopleById[user.salespersonId];
        const multiplier = scenarioMultiplier(person.scenario, user.stage, user.userLayer);
        const weekdayFactor = dayIndex % 7 >= 5 ? 0.78 : 1;
        const dayFactor = 0.92 + dayIndex * 0.012;
        const highValueFactor = user.userLayer === '定金高净值' ? 1.18 : 1;
        const activity = multiplier * weekdayFactor * dayFactor * highValueFactor;
        const receivesClue = probability(random, 0.28 * activity);
        const clueReceipts = receivesClue ? 1 : 0;
        const getsOutbound = receivesClue || probability(random, 0.19 * activity);
        const baseCalls = getsOutbound ? 1 + Math.floor(random() * (activity > 1.2 ? 4 : 3)) : 0;
        const outboundCalls = baseCalls + (getsOutbound && random() < Math.max(0, activity - 1) * 0.35 ? 1 : 0);
        const connectionChance = 0.31 + (user.stage === '高中' ? 0.06 : 0) + (user.userLayer === '定金高净值' ? 0.05 : 0);
        const connectedCalls = outboundCalls > 0 && probability(random, connectionChance)
          ? 1 + (outboundCalls > 2 && probability(random, 0.1) ? 1 : 0)
          : 0;
        const callMinutes = connectedCalls > 0
          ? Math.round((3 + random() * 15 + connectedCalls * 2) * 10) / 10
          : 0;
        const wecomInteractions = connectedCalls > 0
          ? Math.floor(random() * 4) + (probability(random, 0.38) ? 1 : 0)
          : (probability(random, 0.06 * activity) ? 1 : 0);
        const followupChance = person.scenario === 'followupGap' ? 0.38 : 0.74;
        const followedUp = connectedCalls > 0 && probability(random, followupChance) ? 1 : 0;

        dailyFacts.push({
          date,
          teamId: user.teamId,
          salespersonId: user.salespersonId,
          userId: user.id,
          stage: user.stage,
          grade: user.grade,
          userLayer: user.userLayer,
          clueReceipts,
          outboundCalls,
          connectedCalls,
          callMinutes,
          wecomInteractions,
          followedUp,
        });
      });
    });

    return { dates, teams, salespeople, users, dailyFacts };
  }

  return {
    generate,
    dimensions: {
      stages: STAGES.slice(),
      grades: Object.fromEntries(Object.entries(GRADES).map(([stage, grades]) => [stage, grades.slice()])),
      userLayers: USER_LAYERS.slice(),
    },
  };
}));
