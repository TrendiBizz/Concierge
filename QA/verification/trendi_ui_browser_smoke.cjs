// Browser smoke for website/ui/trendi-ui.js under the site's CSP (style-src 'self'). Local only: no network.
// Run: PLAYWRIGHT=/Users/jo/work-staging/argo-video/node_modules/playwright node QA/verification/trendi_ui_browser_smoke.cjs <out-dir>
// Pass = printed JSON has errors [], sheetClosedByDrag true, cmdk.first "Concierge pricing…", approve "Edit first".
const {chromium} = require(process.env.PLAYWRIGHT || 'playwright');
const path = require('path'), http = require('http'), fs = require('fs');
const SITE = path.resolve(__dirname, '../../website');
const OUT = process.argv[2] || require('os').tmpdir();
const page_html = `<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/ui/trendi-ui.css"></head>
<body><main><p>Lost per year: <strong id="n"></strong></p><div id="ai"></div><nav id="nav"><a href="/pricing">Pricing</a><a href="/about">About</a></nav></main>
<script src="/ui/trendi-ui.js"></script></body></html>`;
const srv = http.createServer((q, r) => {
  if (q.url === '/demo') { r.writeHead(200, {'content-type':'text/html','content-security-policy':"default-src 'self'; style-src 'self'; script-src 'self'"}); return r.end(page_html); }
  const f = path.join(SITE, q.url.split('?')[0]);
  if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) { r.writeHead(404); return r.end(); }
  const t = f.endsWith('.css') ? 'text/css' : f.endsWith('.js') ? 'text/javascript' : f.endsWith('.json') ? 'application/json' : 'application/octet-stream';
  r.writeHead(200, {'content-type': t}); fs.createReadStream(f).pipe(r);
}).listen(0, async () => {
  const base = 'http://127.0.0.1:' + srv.address().port;
  const b = await chromium.launch(); const p = await b.newPage({viewport:{width:390,height:800}});
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type()==='error') errs.push(m.text()); });
  await p.goto(base + '/demo'); const out = {};
  await p.evaluate(() => { TrendiUI.ticker(document.getElementById('n'), 12040, {format:{style:'currency',currency:'NZD'}}); });
  await p.waitForTimeout(1200);
  await p.evaluate(() => TrendiUI.ticker(document.getElementById('n'), 18990, {format:{style:'currency',currency:'NZD'}}));
  await p.waitForTimeout(1200);
  out.ticker = await p.getAttribute('#n', 'aria-label');
  out.tickerVisible = await p.evaluate(() => [...document.querySelectorAll('#n .tui-reel')].map(r => Math.round(-new DOMMatrix(getComputedStyle(r).transform).m42 / (r.offsetHeight/10))).join(''));
  await p.evaluate(() => { TrendiUI.toast('Link copied', {type:'success'}); TrendiUI.toast('Second'); TrendiUI.toast('Third'); TrendiUI.toast('Fourth'); });
  out.toasts = await p.evaluate(() => ({n: document.querySelectorAll('.tui-toast').length, hidden: document.querySelectorAll('.tui-toast.tui-hidden').length, live: document.querySelector('.tui-toast-region').getAttribute('aria-live')}));
  await p.screenshot({path: path.join(OUT, 'toasts.png')});
  const ai = p.evaluate(() => { const s = TrendiUI.aiStatus(document.getElementById('ai')); s.thinking(['Fetch robots.txt','Read sitemap','Score pages']); s.step(0,'done'); return s.stream('Your site is readable by AI crawlers. Two pages block GPTBot.').then(() => document.getElementById('ai').textContent); });
  out.aiText = await ai;
  const choice = p.evaluate(() => TrendiUI.aiStatus(document.getElementById('ai')).approve({question:'Send this quote?', step:'1 / 2', options:['Send now','Edit first']}));
  await p.click('text=Edit first'); await p.click('.tui-ai-continue'); out.approve = await choice;
  await p.evaluate(() => TrendiUI.commandMenu({indexUrl: '/ui/search-index.json'}));
  await p.keyboard.press('Control+k'); await p.waitForTimeout(300);
  await p.keyboard.type('pric'); await p.waitForTimeout(150);
  out.cmdk = await p.evaluate(() => ({open: document.querySelector('.tui-cmdk').open, first: document.querySelector('.tui-cmdk-item[aria-selected=true] .tui-cmdk-label')?.textContent, focus: document.activeElement.className}));
  await p.screenshot({path: path.join(OUT, 'cmdk.png')});
  await p.keyboard.press('Escape'); out.cmdkClosed = await p.evaluate(() => !document.querySelector('.tui-cmdk').open);
  await p.evaluate(() => { window.__s = TrendiUI.sheet(document.getElementById('nav').cloneNode(true), {label:'Menu'}); });
  await p.waitForTimeout(600); await p.screenshot({path: path.join(OUT, 'sheet.png')});
  const box = await p.locator('.tui-sheet-handle').boundingBox();
  await p.mouse.move(box.x + 20, box.y + 2); await p.mouse.down(); await p.mouse.move(box.x + 20, box.y + 60, {steps: 6}); await p.mouse.up();
  await p.waitForTimeout(700); out.sheetClosedByDrag = await p.evaluate(() => !document.querySelector('.tui-sheet'));
  out.errors = errs; console.log(JSON.stringify(out, null, 1)); await b.close(); srv.close();
});
