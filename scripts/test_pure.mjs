/**
 * scripts/test_pure.mjs — 纯函数回归（阶段8）
 *
 * 不依赖浏览器：直接 require 三个 UMD 模块，用真实数据 + synthetic 夹具跑断言。
 * 运行：node scripts/test_pure.mjs
 * 退出码：0 全通过；1 有失败。
 */

import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { readFileSync } from 'node:fs';
import path from 'node:path';

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const Marey = require(path.join(root, 'js/marey-chart.js'));
const Line = require(path.join(root, 'js/line-diagram.js'));
const Interactions = require(path.join(root, 'js/interactions.js'));

const real = JSON.parse(readFileSync(path.join(root, 'data/processed/shita_timetable_2026-10-20_data-v2.json'), 'utf8'));
const USABLE = real.trains.filter(t => t.validation.usable_for_frontend).length;
const tiny = JSON.parse(readFileSync(path.join(root, 'data/test-fixtures/synthetic_crossday_tiny.json'), 'utf8'));

const results = [];
function check(name, fn) {
  try {
    fn();
    results.push({ name, ok: true });
    console.log(`PASS | ${name}`);
  } catch (e) {
    results.push({ name, ok: false, error: e.message });
    console.log(`FAIL | ${name} | ${e.message}`);
  }
}
function eq(actual, expected, label) {
  if (actual !== expected) throw new Error(`${label || ''} 期望 ${expected}，实际 ${actual}`);
}
function near(actual, expected, tol, label) {
  if (Math.abs(actual - expected) > tol) throw new Error(`${label || ''} 期望 ${expected}±${tol}，实际 ${actual}`);
}

// ------------------------------------------------------------ Marey 纯函数
check('Marey：夹具轴只有 3 站', () => {
  const axis = Marey.buildAxis(tiny.stations, {});
  eq(axis.rows.map(r => r.label).join(','), '石家庄,阳泉北,太原');
});

check('Marey：跨日 00:10 = 1450，不回绕', () => {
  const axis = Marey.buildAxis(tiny.stations, {});
  const s = Marey.buildSeries(tiny.trains[0], axis, {});
  const xs = s.segments[0].map(p => p.x);
  eq(xs.indexOf(1450) !== -1, true, '缺少 1450 点');
  eq(Math.min(...xs), 1430);
});

check('Marey：未映射站断线', () => {
  const place = (seq, x) => ({ line: 'shita', sequence: seq, x: x, y: 0.5, role: 'intermediate',
    branch_of: null, branch_order: null, link: 'main', label: 'above' });
  const stations = [
    { name: 'A', station_id: 'st:A', is_highlighted: false, place: place(1, 0.2), stats: { stop_records: 1 } },
    { name: 'B', station_id: 'st:B', is_highlighted: false, place: place(2, 0.8), stats: { stop_records: 1 } }
  ];
  const axis = Marey.buildAxis(stations, {});
  const train = {
    train_id: 'tr:X', train_no: 'X', direction: 'up', train_type: 't',
    validation: { usable_for_frontend: true, status: 'validated', flags: [] },
    stops: [
      { station: 'A', station_order: 1, abs_minute: { arr: null, dep: 100 } },
      { station: 'Z', station_order: 2, abs_minute: { arr: 120, dep: 121 } },
      { station: 'B', station_order: 3, abs_minute: { arr: 150, dep: null } }
    ]
  };
  const s = Marey.buildSeries(train, axis, {});
  eq(s.segments.length, 2, '段数');
});

check('Marey：纵轴行数 ≥ 7，太原/太原南、石家庄/石家庄北分开', () => {
  const axis = Marey.buildAxis(real.stations, {});
  const labels = axis.rows.map(r => r.label);
  if (labels.indexOf('太原') === -1 || labels.indexOf('太原南') === -1) throw new Error('太原未分开：' + labels.join(','));
  if (labels.indexOf('石家庄') === -1 || labels.indexOf('石家庄北') === -1) throw new Error('石家庄未分开：' + labels.join(','));
  // 行数随支线办客站增减（v2 起含昔阳），只锁定下限与核心结构
  if (labels.length < 7) throw new Error('行数不足：' + labels.join(','));
  const sjzIdx = labels.indexOf('石家庄');
  const sjzbIdx = labels.indexOf('石家庄北');
  if (Math.abs(sjzIdx - sjzbIdx) !== 1) throw new Error('石家庄北应紧邻石家庄行');
  if (labels.indexOf('太原') > labels.indexOf('太原南')) throw new Error('太原应在太原南上方');
});

check('Line：石家庄北为联络线、阳泉东为阳大支线', () => {
  const layout = Line.buildLayout(real.stations, {});
  eq(layout.byStationName['石家庄北'].link, 'connecting');
  eq(layout.byStationName['石家庄北'].branchOf, '获鹿');
  eq(layout.byStationName['阳泉东'].link, 'regional');
  eq(layout.byStationName['阳泉东'].branchOf, '阳泉北');
});

check('Line：上北下南（太原在太原南上方、石家庄北在石家庄上方）', () => {
  const layout = Line.buildLayout(real.stations, {});
  const ty = layout.byStationName['太原'], tyn = layout.byStationName['太原南'];
  const sjz = layout.byStationName['石家庄'], sjzb = layout.byStationName['石家庄北'];
  if (!(ty.y < tyn.y)) throw new Error('太原 y=' + ty.y + ' 应小于太原南 y=' + tyn.y);
  if (!(sjzb.y < sjz.y)) throw new Error('石家庄北 y=' + sjzb.y + ' 应小于石家庄 y=' + sjz.y);
  if (!(ty.x < sjzb.x)) throw new Error('太原应在石家庄西侧');
});

check('Line：所有轨道边横平竖直（无斜线）', () => {
  const layout = Line.buildLayout(real.stations, {});
  const bad = layout.edges.filter(e => {
    for (let i = 1; i < e.geom.length; i++) {
      const a = e.geom[i - 1], b = e.geom[i];
      if (a.x !== b.x && a.y !== b.y) return true;
    }
    return false;
  });
  eq(bad.length, 0, '斜边 ' + bad.map(e => e.a + '->' + e.b).join(','));
  if (layout.edges.length < 10) throw new Error('轨道边过少 ' + layout.edges.length);
});

check('Line：阳泉北→石家庄北 经获鹿走石太普铁，不经过石家庄站', () => {
  const layout = Line.buildLayout(real.stations, {});
  const r = layout.route('st:阳泉北', 'st:石家庄北');
  const names = r.geom.map(pt => Math.round(pt.x) + ',' + Math.round(pt.y));
  const at = name => r.geom.some(pt => Math.abs(pt.x - layout.byStationName[name].x) < 0.01 &&
    Math.abs(pt.y - layout.byStationName[name].y) < 0.01);
  if (!at('获鹿')) throw new Error('路径未经过获鹿：' + names.join(' -> '));
  if (at('石家庄')) throw new Error('路径不应经过石家庄：' + names.join(' -> '));
});

check('Line：运行中的车底点严格落在轨道上（0 像素偏差）', () => {
  const layout = Line.buildLayout(real.stations, {});
  const byTrain = {};
  real.segments.forEach(g => { (byTrain[g.train_id] = byTrain[g.train_id] || []).push(g); });
  const distToTrack = (px, py) => {
    let best = Infinity;
    layout.edges.forEach(e => {
      for (let i = 1; i < e.geom.length; i++) {
        const a = e.geom[i - 1], b = e.geom[i];
        const dx = b.x - a.x, dy = b.y - a.y, len2 = dx * dx + dy * dy;
        let t = len2 ? ((px - a.x) * dx + (py - a.y) * dy) / len2 : 0;
        t = Math.max(0, Math.min(1, t));
        best = Math.min(best, Math.hypot(px - (a.x + dx * t), py - (a.y + dy * t)));
      }
    });
    return best;
  };
  let samples = 0, maxOff = 0;
  real.trains.filter(t => t.validation.usable_for_frontend).forEach(t => {
    const pack = Line.buildLegs(t, layout, byTrain[t.train_id] || []);
    if (!pack.legs.length) return;
    for (let tm = pack.firstStart; tm <= pack.lastEnd; tm += 5) {
      const p = Line.computePosition(pack, tm);
      if (p.state !== 'moving') continue;
      samples += 1;
      maxOff = Math.max(maxOff, distToTrack(p.x, p.y));
    }
  });
  if (samples < 500) throw new Error('样本过少 ' + samples);
  if (maxOff > 0.01) throw new Error('偏离轨道 ' + maxOff.toFixed(3) + 'px');
});

check('Marey：时间域按 coverage 取整', () => {
  const d = Marey.computeDomain({ abs_minute_min: 14, abs_minute_max: 2663 }, {});
  eq(d[0], 0); eq(d[1], 2700);
});

// ------------------------------------------------------------ 线路图纯函数
const tinyLayout = Line.buildLayout(tiny.stations, {});
const tinyPack = Line.buildLegs(tiny.trains[0], tinyLayout, tiny.segments);

check('Line：区间腿 3 段（run/dwell/run）', () => {
  eq(tinyPack.legs.map(l => l.type).join(','), 'run,dwell,run');
  eq(tinyPack.legs[0].start, 1430);
  eq(tinyPack.legs[0].end, 1450);
});

check('Line：跨日 00:00 位于区间中点', () => {
  const p = Line.computePosition(tinyPack, 1440);
  eq(p.state, 'moving');
  near(p.progress, 0.5, 1e-9, 'progress');
});

check('Line：停站固定', () => {
  const p = Line.computePosition(tinyPack, 1451);
  eq(p.state, 'stopped');
  eq(p.station, '阳泉北');
});

check('Line：终到停在终点', () => {
  const p = Line.computePosition(tinyPack, 1501);
  eq(p.state, 'terminal');
});

check('Line：未发车隐藏', () => {
  eq(Line.computePosition(tinyPack, 1429).state, 'pending');
});

check(`Line：真实数据 ${USABLE} 车中，无区间腿的只能是走廊内不停站车`, () => {
  const layout = Line.buildLayout(real.stations, {});
  const byTrain = {};
  real.segments.forEach(g => { (byTrain[g.train_id] = byTrain[g.train_id] || []).push(g); });
  const usable = real.trains.filter(t => t.validation.usable_for_frontend);
  const empty = usable.filter(t => Line.buildLegs(t, layout, byTrain[t.train_id] || []).legs.length === 0);
  // 走廊内停站 ≤1 的车（G379/G380 这类标杆车在石家庄通过不停）本来就没有可画的区间腿
  const CORRIDOR = new Set(['石家庄', '石家庄北', '阳泉北', '阳泉东', '太原', '太原南', '平定', '昔阳']);
  const bad = empty.filter(t => t.stops.filter(s => CORRIDOR.has(s.station)).length > 1);
  eq(bad.length, 0, '异常无腿车次 ' + bad.map(t => t.train_no).join(','));
});

// ------------------------------------------------------------ 筛选与详情
check('筛选：夹具方向 down', () => {
  eq(Interactions.applyFilters(tiny.trains, { direction: 'down' }).length, 1);
  eq(Interactions.applyFilters(tiny.trains, { direction: 'up' }).length, 0);
});

check('筛选：真实数据方向筛选自洽', () => {
  const up = Interactions.applyFilters(real.trains, { direction: 'up' }).length;
  const down = Interactions.applyFilters(real.trains, { direction: 'down' }).length;
  eq(up + down, real.trains.length);
  eq(Interactions.applyFilters(real.trains, { trainType: '高铁' }).length,
     real.trains.filter(t => t.train_type === '高铁').length);
});

check('筛选：阳泉北停站车数 = 数据中停靠阳泉北的车数', () => {
  const expected = real.trains.filter(t => t.stops.some(s => s.station === '阳泉北')).length;
  eq(Interactions.applyFilters(real.trains, { station: '阳泉北', stationMode: 'stop' }).length, expected);
  eq(Interactions.applyFilters(real.trains, { station: '阳泉北', stationMode: 'pass' }).length, 0);
});

check('筛选：不改动源数组', () => {
  const before = real.trains.length;
  Interactions.applyFilters(real.trains, { direction: 'up' });
  eq(real.trains.length, before);
});

check('车型选项来自数据', () => {
  const expect = [...new Set(real.trains.map(t => t.train_type))].sort();
  const types = Interactions.typeOptions(real.trains).map(o => o.value).sort();
  eq(types.join(','), expect.join(','));
});

check('时刻格式化：1450 → 次日 00:10', () => {
  eq(Interactions.formatAbs(1450), '次日 00:10');
  eq(Interactions.formatAbs(null), '未知');
});

const failed = results.filter(r => !r.ok);
console.log(`\n合计 ${results.length} 项，失败 ${failed.length} 项`);
process.exit(failed.length ? 1 : 0);
