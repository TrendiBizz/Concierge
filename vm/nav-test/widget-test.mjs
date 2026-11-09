// Browser test of the Concierge chat widget on a site page.
//   node widget-test.mjs <pageUrl> <apiBase> <publicKey>
//   e.g. node widget-test.mjs http://localhost:8090/index.html http://127.0.0.1:8000 pk_xxx
// The script tag is added to the page at run time, exactly as the one-line install snippet would do.
// It sends one real chat message, so it needs the API and its language model running; the wait is up to 120s.
// Exit code 0 = passed, 1 = failed.
import puppeteer from 'puppeteer-core';

const [pageUrl, api, key] = process.argv.slice(2);
if (!pageUrl || !api || !key) {
  console.error('Usage: node widget-test.mjs <pageUrl> <apiBase> <publicKey>');
  process.exit(2);
}
const CHROME = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const MESSAGE = process.env.WIDGET_MESSAGE || 'What does Concierge do?';

const results = [];
const check = (name, ok, detail = '') => { results.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name} ${ok ? '' : detail}`); };

const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] });
try {
  const p = await browser.newPage();
  await p.setViewport({ width: 1280, height: 800 });
  const errors = [];
  p.on('pageerror', (e) => errors.push(String(e)));
  p.on('console', (m) => { if (m.type() === 'error' && !/favicon/.test(m.text())) errors.push(m.text()); });
  await p.goto(pageUrl, { waitUntil: 'load' });

  await p.evaluate((src, k) => {
    const s = document.createElement('script');
    s.src = src; s.defer = true; s.setAttribute('data-key', k);
    document.body.appendChild(s);
  }, `${api.replace(/\/+$/, '')}/widget.js`, key);

  const root = await p.waitForSelector('#cc-root', { timeout: 15000 }).catch(() => null);
  check('widget mounts on the page', root);
  if (!root) throw new Error('widget did not mount');

  const sh = (sel) => p.evaluateHandle((s) => document.querySelector('#cc-root').shadowRoot.querySelector(s), sel);
  const text = (sel) => p.evaluate((s) => { const e = document.querySelector('#cc-root').shadowRoot.querySelector(s); return e ? e.innerText : ''; }, sel);
  const count = (sel) => p.evaluate((s) => document.querySelector('#cc-root').shadowRoot.querySelectorAll(s).length, sel);

  const launcher = await sh('.launcher');
  check('launcher button is shown', launcher.asElement());
  await launcher.asElement().click();
  await p.waitForFunction(() => {
    const e = document.querySelector('#cc-root').shadowRoot.querySelector('.panel');
    return e && getComputedStyle(e).display !== 'none';
  }, { timeout: 5000 }).catch(() => {});
  check('click opens the chat panel', await p.evaluate(() => {
    const e = document.querySelector('#cc-root').shadowRoot.querySelector('.panel');
    return e && getComputedStyle(e).display !== 'none';
  }));
  check('greeting message is shown', (await count('.b.assistant')) >= 1, `bubbles=${await count('.b.assistant')}`);

  const before = await count('.b.assistant');
  const input = await sh('input');
  await input.asElement().type(MESSAGE);
  await (await sh('.btn[aria-label="Send"]')).asElement().click();
  check('user message appears', (await count('.b.user')) >= 1);

  const t0 = Date.now();
  // The widget shows a "…" bubble while it waits; a real reply replaces it. Wait for a last bubble that is not "…".
  const got = await p.waitForFunction((n) => {
    const b = document.querySelector('#cc-root').shadowRoot.querySelectorAll('.b.assistant');
    return b.length > n && b[b.length - 1].innerText.trim() !== '…';
  }, { timeout: 120000 }, before).then(() => true).catch(() => false);
  const reply = await p.evaluate(() => { const b = document.querySelector('#cc-root').shadowRoot.querySelectorAll('.b.assistant'); return b[b.length - 1].innerText; });
  check(`assistant replies (${Math.round((Date.now() - t0) / 1000)}s)`, got, 'no reply within 120s');
  check('reply is a real answer, not the error message', got && !/trouble right now|couldn't reach the server/i.test(reply), reply);
  console.log(`      reply: ${reply.slice(0, 200).replace(/\s+/g, ' ')}`);
  check('no JavaScript errors on the page', errors.length === 0, errors.join(' | '));
} catch (e) {
  check('test ran to the end', false, String(e));
} finally {
  await browser.close();
}
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed.`);
process.exit(failed.length ? 1 : 0);
