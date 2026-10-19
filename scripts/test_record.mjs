import { createRequire } from 'node:module';
const require = createRequire('file:///C:/Users/Apollo/.workbuddy/binaries/node/workspace/');
const { chromium } = require('playwright-core');

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: true
  });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  const errs = [];
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  page.on('pageerror', e => errs.push('pageerror: ' + e.message));

  await page.goto('http://127.0.0.1:8000/record.html?t=600', { waitUntil: 'networkidle' });
  await page.waitForTimeout(400);
  await page.screenshot({ path: '.workbuddy/shots/record-line-day.png' });
  await page.goto('http://127.0.0.1:8000/record.html', { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  await page.mouse.move(900, 500);
  await page.waitForTimeout(300);
  await page.screenshot({ path: '.workbuddy/shots/record-marey.png' });

  const info = await page.evaluate(() => {
    const svg = document.querySelector('#viewMarey .mc-svg');
    return {
      trains: document.querySelectorAll('.mc-train').length,
      rows: document.querySelectorAll('.mc-station-label').length,
      svgHeight: svg && svg.getAttribute('height'),
      svgBox: svg && svg.getAttribute('viewBox'),
      stageH: document.getElementById('stage').clientHeight,
      hudText: document.getElementById('clock').textContent,
      seekMax: document.getElementById('seek').max
    };
  });
  console.log('marey:', JSON.stringify(info));

  await page.click('button[data-mode="both"]');
  await page.waitForTimeout(700);
  await page.mouse.move(900, 500);
  await page.waitForTimeout(200);
  await page.screenshot({ path: '.workbuddy/shots/record-both.png' });
  const both = await page.evaluate(() => ({
    mc: document.querySelectorAll('.mc-train').length,
    ld: document.querySelectorAll('.ld-train').length,
    mh: document.querySelector('#viewMarey .mc-svg')?.getAttribute('height'),
    lh: document.querySelector('#viewLine .ld-svg')?.getAttribute('height')
  }));
  console.log('both:', JSON.stringify(both));

  await page.click('button[data-mode="line"]');
  await page.waitForTimeout(700);
  await page.mouse.move(900, 500);
  await page.waitForTimeout(200);
  await page.screenshot({ path: '.workbuddy/shots/record-line.png' });

  await page.click('button[data-mode="marey"]');
  await page.waitForTimeout(500);
  await page.click('#playBtn');
  await page.waitForTimeout(1400);
  const t1 = await page.evaluate(() => window.__rec.player.getState());
  await page.waitForTimeout(900);
  const t2 = await page.evaluate(() => window.__rec.player.getState());
  console.log('play:', JSON.stringify(t1), '->', JSON.stringify(t2));

  await page.waitForTimeout(3200);
  const hidden = await page.evaluate(() => ({
    hud: document.getElementById('hud').classList.contains('is-hidden'),
    idle: document.body.classList.contains('is-idle')
  }));
  console.log('auto-hide after 3.2s idle:', JSON.stringify(hidden));
  await page.screenshot({ path: '.workbuddy/shots/record-clean.png' });

  console.log('errors:', errs.length ? errs.slice(0, 4) : 'none');
  await browser.close();
})();
