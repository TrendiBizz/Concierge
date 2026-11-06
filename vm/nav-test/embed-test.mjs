// Test that the site itself loads the chat widget and the widget answers from the knowledge base.
//   node embed-test.mjs [siteDir] ["question"]
// The site is not deployed, so the browser is told that https://www.trendibizz.com/<page> is a file in siteDir.
// Everything else (widget.js, the chat API at chat.trendibizz.com, the language model) is the LIVE service,
// called from the allowed origin https://www.trendibizz.com. It sends one real chat message.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import puppeteer from 'puppeteer-core';

const SITE = process.argv[2] || path.join(os.homedir(), 'Downloads/concierge-build/concierge-site');
const QUESTION = process.argv[3] || 'What can the CRM do?';
const CHROME = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const TYPES = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml' };

const results = [];
const check = (name, ok, detail = '') => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name} ${ok ? '' : detail}`); };

const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] });
try {
  const p = await browser.newPage();
  await p.setViewport({ width: 1280, height: 800 });
  const errors = [];
  p.on('pageerror', (e) => errors.push(String(e)));
  await p.setRequestInterception(true);
  p.on('request', (req) => {
    const u = new URL(req.url());
    if (u.hostname === 'www.trendibizz.com') {
      const file = path.join(SITE, u.pathname === '/' ? 'index.html' : u.pathname);
      if (file.startsWith(SITE) && fs.existsSync(file) && fs.statSync(file).isFile()) {
        return req.respond({ status: 200, contentType: TYPES[path.extname(file)] || 'application/octet-stream', body: fs.readFileSync(file) });
      }
      return req.respond({ status: 404, body: 'not found' });
    }
    req.continue();
  });
  p.on('console', (m) => { if (m.type() === 'error' && !/favicon|filesafe|ERR_/.test(m.text())) errors.push(m.text()); });

  await p.goto('https://www.trendibizz.com/crm.html', { waitUntil: 'load' });
  const root = await p.waitForSelector('#cc-root', { timeout: 15000 }).catch(() => null);
  check('site loads the widget by itself (no manual script tag)', root);
  if (!root) throw new Error('widget did not appear');
  const sr = (fn, ...a) => p.evaluate(fn, ...a);
  await p.evaluateHandle(() => document.querySelector('#cc-root').shadowRoot.querySelector('.launcher').click());
  check('chat panel opens', await sr(() => getComputedStyle(document.querySelector('#cc-root').shadowRoot.querySelector('.panel')).display !== 'none'));
  const before = await sr(() => document.querySelector('#cc-root').shadowRoot.querySelectorAll('.b.assistant').length);
  const input = await p.evaluateHandle(() => document.querySelector('#cc-root').shadowRoot.querySelector('input'));
  await input.asElement().type(QUESTION);
  await p.evaluateHandle(() => document.querySelector('#cc-root').shadowRoot.querySelector('.btn[aria-label="Send"]').click());
  const t0 = Date.now();
  const got = await p.waitForFunction((n) => {
    const b = document.querySelector('#cc-root').shadowRoot.querySelectorAll('.b.assistant');
    return b.length > n && b[b.length - 1].innerText.trim() !== '…';
  }, { timeout: 120000 }, before).then(() => true).catch(() => false);
  const reply = await sr(() => { const b = document.querySelector('#cc-root').shadowRoot.querySelectorAll('.b.assistant'); return b[b.length - 1].innerText; });
  check(`assistant replies (${Math.round((Date.now() - t0) / 1000)}s)`, got);
  check('reply is not the error message', got && !/trouble right now|couldn't reach the server/i.test(reply), reply);
  console.log(`      question: ${QUESTION}\n      reply: ${reply.replace(/\s+/g, ' ').slice(0, 500)}`);
  check('no JavaScript errors', errors.length === 0, errors.join(' | '));
} catch (e) {
  check('test ran to the end', false, String(e));
} finally {
  await browser.close();
}
console.log(`\n${results.filter(Boolean).length}/${results.length} checks passed.`);
process.exit(results.every(Boolean) ? 0 : 1);
