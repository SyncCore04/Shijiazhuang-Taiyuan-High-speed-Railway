/**
 * scripts/test_e2e.mjs — 端到端验收（阶段8）
 *
 * 覆盖：播放器时序/边界/键盘、两视图同步、筛选语义、选中联动、空状态。
 * 依赖：playwright-core（不随项目分发）+ 本机 Chromium 内核浏览器。
 *
 * 运行：
 *   python -m http.server 8000          # 项目根目录
 *   node scripts/test_e2e.mjs           # 可用 BASE_URL / BROWSER_PATH / PLAYWRIGHT_CORE 覆盖
 *
 * 退出码：0 全通过；1 有失败；2 环境不可用。
 */

import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:8000';
const BROWSER_PATH = process.env.BROWSER_PATH ||
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const PLAYWRIGHT_CORE = process.env.PLAYWRIGHT_CORE ||
  'C:/Users/Apollo/.workbuddy/binaries/node/workspace/';

let chromium;
try {
  const require = createRequire('file:///' + PLAYWRIGHT_CORE.replace(/\\/g, '/').replace(/\/?$/, '/'));
  ({ chromium } = require('playwright-core'));
} catch (e) {
  console.error('[FATAL] 找不到 playwright-core：' + e.message);
  process.exit(2);
}

const results = [];
function check(name, ok, detail = '') {
  results.push({ name, ok: !!ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'} | ${name}${detail ? ' | ' + detail : ''}`);
}
const near = (a, b, tol) => Math.abs(a - b) <= tol;

const browser = await chromium.launch({ executablePath: BROWSER_PATH, headless: true });
const page = await browser.newPage({ viewport: { width: 1500, height: 1100 } });
const pageErrors = [];
page.on('pageerror', e => pageErrors.push(e.message));
page.on('console', m => { if (m.type() === 'error') pageErrors.push(m.text()); });

await page.goto(`${BASE_URL}/index.html`, { waitUntil: 'networkidle' });
await page.waitForSelector('.mc-train', { state: 'attached' });
await page.waitForSelector('.ld-train', { state: 'attached' });

const state = () => page.evaluate(() => window.__app.player.getState());
const clock = () => page.locator('#clock').textContent();
const sleep = ms => page.waitForTimeout(ms);

// 期望车数从数据文件动态取，避免每次换数据版本都要改测试
const DATASET = JSON.parse(readFileSync(
  path.join(rootDir, 'data/processed/shita_timetable_2026-10-20_data-v2.json'), 'utf8'));
const USABLE = DATASET.trains.filter(t => t.validation.usable_for_frontend).length;

// ---------------------------------------------------------------- 数据/装配
// 线路图只会为「走廊内停站 ≥2」的车建腿；G379/G380 这类标杆车在石家庄通过不停，故可少 1~2 个
const mareyCount = await page.locator('.mc-train').count();
const lineCount = await page.locator('.ld-train').count();
check(`两视图渲染车数（线路图可少无腿标杆车）`,
  mareyCount === USABLE && lineCount <= mareyCount && mareyCount - lineCount <= 2,
  `${mareyCount}/${lineCount}`);
check('初始暂停且时间 10:00', (await state()).playing === false && (await clock()) === '10:00');

// ---------------------------------------------------------------- 新拓扑：分站与联络线
const axisLabels = await page.evaluate(() => Array.from(document.querySelectorAll('.mc-station-label')).map(n => n.textContent));
check('运行图纵轴 ≥7 行且两城双站分开', axisLabels.length >= 7 && axisLabels.includes('太原') && axisLabels.includes('太原南') &&
  axisLabels.includes('石家庄') && axisLabels.includes('石家庄北'), axisLabels.join(' / '));

const linkInfo = await page.evaluate(() => {
  const el = document.querySelector('.ld-link--connecting');
  const edge = window.__app.diagram.getLayout().edges.find(e => e.kind === 'connecting');
  return el ? { dash: el.getAttribute('stroke-dasharray'), a: edge && edge.a, b: edge && edge.b } : null;
});
check('获鹿—石家庄北（石太普铁）为虚线联络线', !!linkInfo && /\d/.test(linkInfo.dash || '') &&
  linkInfo.a === '获鹿' && linkInfo.b === '石家庄北', JSON.stringify(linkInfo));

const doubleStop = await page.evaluate(() => {
  const t = window.__app.data.trains.find(x => x.train_no === 'G622');
  const names = t.stops.map(s => s.station);
  return { hasBoth: names.includes('太原') && names.includes('太原南'), order: names.slice(names.indexOf('太原南'), names.indexOf('太原') + 1) };
});
check('一城双停：G622 同时停太原南与太原', doubleStop.hasBoth, doubleStop.order.join('→'));

const orthogonal = await page.evaluate(() => {
  const paths = Array.from(document.querySelectorAll('.ld-track'));
  let bad = 0, segs = 0;
  paths.forEach(p => {
    const nums = (p.getAttribute('d').match(/-?\d+(?:\.\d+)?/g) || []).map(Number);
    for (let i = 2; i + 1 < nums.length; i += 2) {
      segs += 1;
      if (nums[i - 2] !== nums[i] && nums[i - 1] !== nums[i + 1]) bad += 1;
    }
  });
  return { paths: paths.length, segs, bad };
});
check('轨道全部横平竖直（无斜线）', orthogonal.bad === 0 && orthogonal.paths >= 10,
  JSON.stringify(orthogonal));

const onTrack = await page.evaluate(() => {
  const app = window.__app;
  app.player.seek(660);
  const active = app.diagram.getActiveTrains();
  const layout = app.diagram.getLayout();
  let worst = { off: -1, train: null };
  active.forEach(a => {
    const el = document.querySelector('.ld-train[data-train-no="' + a.trainNo + '"]');
    const m = /translate\(([-\d.]+),([-\d.]+)\)/.exec(el.getAttribute('transform') || '');
    if (!m) return;
    const px = +m[1], py = +m[2];
    let best = Infinity;
    layout.edges.forEach(e => {
      for (let i = 1; i < e.geom.length; i++) {
        const p0 = e.geom[i - 1], p1 = e.geom[i];
        const dx = p1.x - p0.x, dy = p1.y - p0.y;
        const len2 = dx * dx + dy * dy;
        let t = len2 ? ((px - p0.x) * dx + (py - p0.y) * dy) / len2 : 0;
        t = Math.max(0, Math.min(1, t));
        best = Math.min(best, Math.hypot(px - (p0.x + dx * t), py - (p0.y + dy * t)));
      }
    });
    if (best > worst.off) worst = { off: best, train: a.trainNo };
  });
  return { worst, count: active.length };
});
check('车底点严格贴在轨道上', onTrack.worst.off >= 0 && onTrack.worst.off < 0.5,
  JSON.stringify(onTrack));

// ---------------------------------------------------------------- 播放时序
await page.evaluate(() => window.__app.player.seek(600));
await page.click('#playBtn');
await sleep(1000);
let s = await state();
check('1x 播放约 2 分钟/秒', s.playing && near(s.time - 600, 2, 0.7), `Δ=${(s.time - 600).toFixed(2)}`);

await page.click('#playBtn');
await sleep(450);
const paused1 = await state();
await sleep(400);
const paused2 = await state();
check('暂停后时间不推进', paused1.playing === false && paused1.time === paused2.time,
  `${paused1.time.toFixed(2)} → ${paused2.time.toFixed(2)}`);

await page.selectOption('#speed', '5');
await page.evaluate(() => window.__app.player.seek(600));
await page.click('#playBtn');
await sleep(1000);
s = await state();
check('5x 播放约 10 分钟/秒', near(s.time - 600, 10, 2), `Δ=${(s.time - 600).toFixed(2)}`);
await page.click('#playBtn');

await page.selectOption('#speed', '0.5');
await page.evaluate(() => window.__app.player.seek(600));
await page.click('#playBtn');
await sleep(1000);
s = await state();
check('0.5x 播放约 1 分钟/秒', near(s.time - 600, 1, 0.45), `Δ=${(s.time - 600).toFixed(2)}`);
await page.click('#playBtn');

await page.selectOption('#speed', '2');
await page.evaluate(() => window.__app.player.seek(600));
await page.click('#playBtn');
await sleep(1000);
s = await state();
check('2x 播放约 4 分钟/秒', near(s.time - 600, 4, 1), `Δ=${(s.time - 600).toFixed(2)}`);
await page.click('#playBtn');

// ---------------------------------------------------------------- destroy 后不再推进
const destroyResult = await page.evaluate(async () => {
  let ticks = 0;
  const p = window.Player.createPlayer({
    min: 0, max: 1000, initial: 100, minutesPerSecond: 2,
    onTimeChange: () => { ticks += 1; }
  });
  p.play();
  await new Promise(r => setTimeout(r, 300));
  p.destroy();
  const atDestroy = ticks;
  await new Promise(r => setTimeout(r, 300));
  return { atDestroy, after: ticks, state: p.getState() };
});
check('destroy 后停止推进并清理监听',
  destroyResult.atDestroy > 0 && destroyResult.after === destroyResult.atDestroy,
  `${destroyResult.atDestroy} → ${destroyResult.after}`);

// ---------------------------------------------------------------- 多次播放/暂停只有一个循环
for (let i = 0; i < 4; i++) { await page.click('#playBtn'); await sleep(60); await page.click('#playBtn'); await sleep(60); }
await page.selectOption('#speed', '1');
await page.evaluate(() => window.__app.player.seek(600));
await page.click('#playBtn');
await sleep(1000);
s = await state();
check('反复播放/暂停不产生多个 RAF 循环', near(s.time - 600, 2, 0.8), `Δ=${(s.time - 600).toFixed(2)}`);
await page.click('#playBtn');

// ---------------------------------------------------------------- 步进/键盘
await page.evaluate(() => window.__app.player.seek(600));
await page.click('#plus1');
check('+1 分钟精确 +1', (await state()).time === 601, String((await state()).time));
await page.click('#minus1');
check('−1 分钟精确 −1', (await state()).time === 600, String((await state()).time));

await page.locator('body').click({ position: { x: 5, y: 5 } });
await page.keyboard.press('ArrowRight');
const afterRight = (await state()).time;
await page.keyboard.press('ArrowLeft');
check('← / → 逐分钟', afterRight === 601 && (await state()).time === 600, `${afterRight}`);

await page.keyboard.press('Space');
await sleep(120);
const spacePlaying = (await state()).playing;
await page.keyboard.press('Space');
await sleep(120);
check('空格播放/暂停', spacePlaying === true && (await state()).playing === false);

await page.focus('#speed');
const beforeSpace = (await state()).playing;
await page.keyboard.press('Space');
await sleep(120);
check('选择器聚焦时空格不误触', (await state()).playing === beforeSpace, `playing=${beforeSpace}`);
await page.locator('body').click({ position: { x: 5, y: 5 } });

// ---------------------------------------------------------------- 边界
await page.evaluate(() => window.__app.player.seek(window.__app.player.getState().max - 1));
await page.click('#playBtn');
await sleep(900);
s = await state();
check('到边界停止且不绕回', s.playing === false && s.time === s.max, `${s.time}=${s.max}, playing=${s.playing}`);

await page.evaluate(() => window.__app.player.seek(600));
await page.evaluate(() => { const t = document.getElementById('timeline'); t.value = t.max; t.dispatchEvent(new Event('input', { bubbles: true })); });
s = await state();
check('拖到末端即停', s.time === s.max && s.playing === false, `${s.time}`);

// ---------------------------------------------------------------- 两视图同步
await page.evaluate(() => window.__app.player.seek(600));
check('时间读数与 Marey 光标一致', (await clock()) === '10:00' &&
  (await page.locator('.mc-cursor text').textContent()) === '10:00');
const activeAt600 = await page.evaluate(() => window.__app.diagram.getActiveTrains().length);
const visibleLine = await page.evaluate(() => Array.from(document.querySelectorAll('.ld-train')).filter(n => n.style.display !== 'none').length);
check('线路图可见标记 = 活动车次', activeAt600 === visibleLine, `${visibleLine}/${activeAt600}`);

await page.evaluate(() => window.__app.player.seek(1450));
check('次日时刻显示正确（1450 = 次日 00:10）', (await clock()) === '次日 00:10', await clock());
await page.evaluate(() => window.__app.player.seek(600));

// ---------------------------------------------------------------- 筛选
async function counts() {
  return page.evaluate(() => {
    const all = window.__app.data.trains;
    const usable = all.filter(t => t.validation.usable_for_frontend);
    const ids = window.__app.visibleIds();
    return {
      all: all.length, usable: usable.length, visible: ids.length,
      up: usable.filter(t => t.direction === 'up').length,
      down: usable.filter(t => t.direction === 'down').length,
      hsr: usable.filter(t => t.train_type === '高铁').length,
      yq: usable.filter(t => t.stops.some(s => s.station === '阳泉北' && s.stop_kind !== 'pass' && s.is_stop !== false)).length
    };
  });
}
const c0 = await counts();

await page.click('#dirSeg button:nth-child(2)');
let visible = await page.evaluate(() => window.__app.visibleIds().length);
let mareyVisible = await page.evaluate(() => Array.from(document.querySelectorAll('.mc-train')).filter(n => n.style.display !== 'none').length);
check('方向=上行：两视图一致', visible === c0.up && mareyVisible === c0.up, `${visible}/${mareyVisible}/${c0.up}`);

await page.click('#dirSeg button:nth-child(1)');
await page.selectOption('#typeSel', '高铁');
visible = await page.evaluate(() => window.__app.visibleIds().length);
check('车型=高铁筛选', visible === c0.hsr, `${visible}/${c0.hsr}`);

await page.selectOption('#typeSel', 'all');
await page.selectOption('#stationSel', '阳泉北');
visible = await page.evaluate(() => window.__app.visibleIds().length);
check('车站=阳泉北（停站）', visible === c0.yq, `${visible}/${c0.yq}`);

await page.selectOption('#stationMode', 'pass');
visible = await page.evaluate(() => window.__app.visibleIds().length);
const banner = await page.locator('#emptyBanner').isVisible();
check('通过模式为空状态（本批无通过站）', visible === 0 && banner, `visible=${visible}, banner=${banner}`);

await page.click('#resetFilters');
visible = await page.evaluate(() => window.__app.visibleIds().length);
check('重置筛选恢复全部', visible === c0.usable, `${visible}/${c0.usable}`);

// ---------------------------------------------------------------- 筛选不影响时间/播放
await page.evaluate(() => window.__app.player.seek(600));
await page.click('#playBtn');
await sleep(300);
const beforeFilter = await state();
await page.click('#dirSeg button:nth-child(3)');
await sleep(300);
const afterFilter = await state();
check('筛选不重置时间、不暂停', afterFilter.playing === true && afterFilter.time > beforeFilter.time,
  `${beforeFilter.time.toFixed(1)} → ${afterFilter.time.toFixed(1)}, playing=${afterFilter.playing}`);
await page.click('#playBtn');
await page.click('#dirSeg button:nth-child(1)');

// ---------------------------------------------------------------- 选中联动
// 折线可能互相覆盖：沿路径找一个“该车在最上层”的点再点。
// 选 S951（阳大支线、2 站）做点击样本，主线车次在 86 线密集区很难独占命中。
const sampleTrain = await page.evaluate(() => {
  const g = document.querySelector('.mc-train[data-train-no="S951"] .mc-series-hit');
  if (!g || g.closest('.mc-train').style.display === 'none') return null;
  const len = g.getTotalLength();
  const ctm = g.getScreenCTM();
  for (let i = 1; i < 20; i++) {
    const p = g.getPointAtLength(len * i / 20);
    const x = p.x * ctm.a + p.y * ctm.c + ctm.e;
    const y = p.x * ctm.b + p.y * ctm.d + ctm.f;
    const top = document.elementFromPoint(x, y);
    const owner = top && top.closest ? top.closest('.mc-train') : null;
    if (owner && owner.getAttribute('data-train-no') === 'S951') return { no: 'S951', x, y };
  }
  return null;
});
if (!sampleTrain) {
  check('点击 Marey 车次 → 详情', false, '找不到 S951 的独占点击点');
  check('选中同步到线路图', false, '跳过');
} else {
  await page.mouse.click(sampleTrain.x, sampleTrain.y);
  await sleep(200);
  const detailText = await page.evaluate(() => document.getElementById('detail').innerText.replace(/\n/g, ' '));
  check('点击 Marey 车次 → 详情', detailText.includes('S951') && detailText.includes('阳泉东'), detailText.slice(0, 60));
  const ringOpacity = await page.evaluate(() => document.querySelector('.ld-train[data-train-no="S951"] .ld-selected-ring').getAttribute('opacity'));
  check('选中同步到线路图', ringOpacity === '1', String(ringOpacity));
}

// 选中车次被筛掉：S951 是下行，切到“上行”应清空并提示
await page.click('#dirSeg button:nth-child(2)');
await sleep(150);
const afterFilterDetail = await page.evaluate(() => document.getElementById('detail').innerText);
const cleared = await page.evaluate(() => window.__app.getSelected() === null);
check('选中车次被筛掉时清空并提示',
  cleared && afterFilterDetail.includes('不在当前筛选结果'), `cleared=${cleared}`);
await page.click('#resetFilters');

// 线路图点击：G606 在 10:00 停在石家庄
const marker = await page.evaluate(() => {
  const el = document.querySelector('.ld-train[data-train-no="G606"] .ld-marker');
  if (!el || el.closest('.ld-train').style.display === 'none') return null;
  const r = el.getBoundingClientRect();
  return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
});
if (marker) {
  await page.mouse.click(marker.x, marker.y);
  await sleep(200);
  const t2 = await page.evaluate(() => document.getElementById('detail').innerText.replace(/\n/g, ' '));
  check('点击线路图标记 → 同一份详情', t2.includes('G606'), t2.slice(0, 40));
  const mareySel = await page.evaluate(() => document.querySelector('.mc-train[data-train-no="G606"]').classList.contains('mc-train--selected'));
  check('线路图选中同步回 Marey', mareySel);
} else {
  check('点击线路图标记 → 同一份详情', false, 'G606 在当前时刻不可见');
  check('线路图选中同步回 Marey', false, '跳过');
}

// ---------------------------------------------------------------- 空数据防护
const emptyOk = await page.evaluate(() => {
  const app = window.__app;
  app.marey.setVisibleTrains([]);
  app.diagram.setVisibleTrains([]);
  return document.querySelectorAll('.mc-train[style*="display: none"]').length > 0;
});
check('空筛选不报错', emptyOk);
await page.click('#resetFilters');

// ---------------------------------------------------------------- 拖动
await page.evaluate(() => window.__app.player.seek(600));
await page.click('#playBtn');
await sleep(200);
const sliderBox = await page.locator('#timeline').boundingBox();
await page.mouse.move(sliderBox.x + sliderBox.width * 0.4, sliderBox.y + sliderBox.height / 2);
await page.mouse.down();
await page.mouse.move(sliderBox.x + sliderBox.width * 0.6, sliderBox.y + sliderBox.height / 2, { steps: 6 });
const dragState = await state();
const dragClock = await clock();
await page.mouse.up();
await sleep(150);
const afterDragState = await state();
check('拖动时暂停且时间跟随', dragState.playing === false && dragClock !== '10:00', `${dragClock}, playing=${dragState.playing}`);
check('松手后恢复播放', afterDragState.playing === true, `playing=${afterDragState.playing}`);
await page.click('#playBtn');

// ---------------------------------------------------------------- 异常路径（独立页面）
const filePage = await browser.newPage({ viewport: { width: 1200, height: 800 } });
await filePage.goto(pathToFileURL(path.join(rootDir, 'index.html')).href);
await filePage.waitForTimeout(400);
const fileFatal = await filePage.locator('.fatal').innerText().catch(() => '');
const fileHint = fileFatal.includes('file://') || fileFatal.includes('fetch') || fileFatal.includes('HTTP');
check('file:// 打开给出明确提示', fileHint, fileFatal.slice(0, 50).replace(/\n/g, ' '));
await filePage.close();

const badJsonPage = await browser.newPage({ viewport: { width: 1200, height: 800 } });
await badJsonPage.route('**/shita_timetable_*.json', route => route.fulfill({
  status: 200, contentType: 'application/json', body: '{"meta": {'
}));
await badJsonPage.goto(`${BASE_URL}/index.html`, { waitUntil: 'domcontentloaded' });
await badJsonPage.waitForTimeout(500);
const badJsonFatal = await badJsonPage.locator('.fatal').innerText().catch(() => '');
check('非法 JSON 显示错误而非白屏', badJsonFatal.length > 0, badJsonFatal.slice(0, 40).replace(/\n/g, ' '));
await badJsonPage.close();

const versionPage = await browser.newPage({ viewport: { width: 1200, height: 800 } });
await versionPage.route('**/shita_timetable_*.json', async route => {
  const resp = await route.fetch();
  const body = (await resp.text()).replace(/"schema_version":\s*"2\.\d+\.\d+"/, '"schema_version": "3.0.0"');
  await route.fulfill({ status: 200, contentType: 'application/json', body });
});
await versionPage.goto(`${BASE_URL}/index.html`, { waitUntil: 'domcontentloaded' });
await versionPage.waitForTimeout(500);
const versionFatal = await versionPage.locator('.fatal').innerText().catch(() => '');
check('契约主版本不匹配时拒绝渲染', versionFatal.includes('版本不匹配'), versionFatal.slice(0, 40).replace(/\n/g, ' '));
await versionPage.close();

// 窄屏
await page.setViewportSize({ width: 900, height: 1000 });
await sleep(350);
const cols = await page.evaluate(() => getComputedStyle(document.querySelector('.app-grid')).gridTemplateColumns.split(' ').length);
check('窄屏（900px）切为单列', cols === 1, `columns=${cols}`);

check('页面无 console/page 错误', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

await page.screenshot({ path: path.resolve('.workbuddy/shots/e2e-final.png'), fullPage: true });
await browser.close();

const failed = results.filter(r => !r.ok);
console.log(`\n合计 ${results.length} 项，失败 ${failed.length} 项`);
process.exit(failed.length ? 1 : 0);
