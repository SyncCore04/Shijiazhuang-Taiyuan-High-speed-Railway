import { createRequire } from 'node:module';
const require = createRequire('file:///C:/Users/Apollo/.workbuddy/binaries/node/workspace/');
const { chromium } = require('playwright-core');

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true
  });
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  page.on('pageerror', e => console.log('pageerror:', e.message));
  await page.goto('http://127.0.0.1:8000/record.html?view=line', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);

  const report = await page.evaluate(() => {
    const rec = window.__rec;
    const layout = rec.diagram().getLayout();
    const LD = window.LineDiagram;
    const byTrain = {};
    rec.data.segments.forEach(g => { (byTrain[g.train_id] = byTrain[g.train_id] || []).push(g); });
    const out = {};
    for (const no of ['K585', 'K587', 'K892', 'K546', 'G627', 'G601']) {
      const t = rec.data.trains.find(x => x.train_no === no);
      if (!t) { out[no] = 'not-in-data'; continue; }
      const pack = LD.buildLegs(t, layout, byTrain[t.train_id] || []);
      let flips = 0, detourLegs = 0, movingLegs = 0, lastY = null, lastDir = 0;
      for (let t0 = pack.firstStart; t0 <= pack.lastEnd; t0 += 2) {
        const p = LD.computePosition(pack, t0);
        if (p.state === 'detour') detourLegs++;
        if (p.state === 'moving' && p.y != null) {
          movingLegs++;
          const dir = Math.sign(p.y - (lastY ?? p.y));
          if (lastY !== null && dir && lastDir && dir !== lastDir) flips++;
          if (dir) lastDir = dir;
          lastY = p.y;
        }
      }
      out[no] = { legs: pack.legs.length, movingLegs, detourLegs, flips };
    }
    return out;
  });
  console.log(JSON.stringify(report, null, 1));
  await browser.close();
})();
