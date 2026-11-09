// Browser smoke test for the web dashboard. Drives headless Chrome over the
// DevTools protocol using only Node built-ins (Node 22+ has a global WebSocket).
//
// Usage (from the SocialSync folder):  node tools/ui-smoke.mjs
// Screenshots are written to /tmp/socialsync-shots/

import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const serverFile = path.resolve(here, '..', 'server', 'server.js');
const SHOTS = '/tmp/socialsync-shots';
const CHROME =
  process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 43000 + Math.floor(Math.random() * 1000);
const DEBUG_PORT = 44000 + Math.floor(Math.random() * 1000);
const BASE = `http://127.0.0.1:${PORT}`;
const PASSCODE = 'UISMOKE1';
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
);

if (!existsSync(CHROME)) {
  console.error(`Chrome not found at ${CHROME}. Set CHROME_PATH.`);
  process.exit(2);
}
mkdirSync(SHOTS, { recursive: true });

const dataDir = mkdtempSync(path.join(tmpdir(), 'socialsync-ui-'));
const profileDir = mkdtempSync(path.join(tmpdir(), 'socialsync-chrome-'));
const children = [];
const problems = [];
let step = 0;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function cleanup() {
  for (const child of children) child.kill();
  // Chrome keeps writing to its profile for a moment after it is told to quit.
  await sleep(1000);
  const options = { recursive: true, force: true, maxRetries: 10, retryDelay: 300 };
  try {
    rmSync(dataDir, options);
    rmSync(profileDir, options);
  } catch {
    // Temp folders only: leaving them behind is harmless.
  }
}

async function waitHttp(url, tries = 80) {
  for (let i = 0; i < tries; i += 1) {
    try {
      const res = await fetch(url);
      if (res.ok) return res;
    } catch {
      // not up yet
    }
    await sleep(150);
  }
  throw new Error(`Timed out waiting for ${url}`);
}

function check(name, ok, detail = '') {
  step += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${step}. ${name}${ok || !detail ? '' : ` -> ${detail}`}`);
  if (!ok) problems.push(name);
}

async function main() {
  children.push(
    spawn(process.execPath, [serverFile], {
      env: { ...process.env, PORT: String(PORT), DATA_DIR: dataDir, SOCIALSYNC_PASSCODE: PASSCODE },
      stdio: 'ignore',
    }),
  );
  await waitHttp(`${BASE}/api/health`);

  // Seed a photo through the API so the library has something to pick.
  const login = await (
    await fetch(`${BASE}/api/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ passcode: PASSCODE }),
    })
  ).json();
  await fetch(`${BASE}/api/media?filename=ponsonby.png&project=Ponsonby&caption=After`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${login.token}`, 'Content-Type': 'image/png' },
    body: PNG,
  });

  children.push(
    spawn(
      CHROME,
      [
        '--headless=new',
        '--no-sandbox',
        '--disable-gpu',
        '--no-first-run',
        '--no-default-browser-check',
        `--remote-debugging-port=${DEBUG_PORT}`,
        `--user-data-dir=${profileDir}`,
        'about:blank',
      ],
      { stdio: 'ignore' },
    ),
  );
  await waitHttp(`http://127.0.0.1:${DEBUG_PORT}/json/version`);
  const targets = await (await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/list`)).json();
  const page = targets.find((t) => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = reject;
  });

  let nextId = 0;
  const pending = new Map();
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(msg.error.message));
      else resolve(msg.result);
    } else if (msg.method === 'Runtime.exceptionThrown') {
      const d = msg.params.exceptionDetails;
      problems.push(`Uncaught: ${(d.exception && d.exception.description) || d.text}`);
    } else if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
      problems.push(`console.error: ${msg.params.args.map((a) => a.value ?? a.description).join(' ')}`);
    }
  };
  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      nextId += 1;
      pending.set(nextId, { resolve, reject });
      ws.send(JSON.stringify({ id: nextId, method, params }));
    });

  const evaluate = async (expression) => {
    const res = await send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (res.exceptionDetails) {
      throw new Error(res.exceptionDetails.exception?.description || res.exceptionDetails.text);
    }
    return res.result.value;
  };
  const waitFor = async (expression, label, timeout = 6000) => {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      if (await evaluate(`Boolean(${expression})`).catch(() => false)) return true;
      await sleep(100);
    }
    console.log(`  (timed out waiting for ${label})`);
    return false;
  };
  const shot = async (name) => {
    const { data } = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(path.join(SHOTS, `${name}.png`), Buffer.from(data, 'base64'));
  };
  const clickText = (selector, text) =>
    evaluate(`(() => {
      const el = [...document.querySelectorAll(${JSON.stringify(selector)})]
        .find((e) => e.textContent.trim() === ${JSON.stringify(text)});
      if (!el) return false;
      el.click();
      return true;
    })()`);
  const setField = (selector, value) =>
    evaluate(`(() => {
      const el = document.querySelector(${JSON.stringify(selector)});
      el.value = ${JSON.stringify(value)};
      el.dispatchEvent(new Event('input', { bubbles: true }));
      return true;
    })()`);

  await send('Runtime.enable');
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', {
    width: 1200,
    height: 950,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await send('Page.navigate', { url: BASE });

  // ---- login
  check('login screen appears', await waitFor(`document.querySelector('#passcode')`, 'login'));
  await shot('01-login');
  await evaluate(`window.confirm = () => true`);
  await setField('#passcode', 'wrong');
  await clickText('button', 'Sign in');
  check(
    'wrong passcode shows an error',
    await waitFor(`document.querySelector('.login p.small').textContent.includes('Wrong')`, 'error'),
  );
  await setField('#passcode', PASSCODE);
  await clickText('button', 'Sign in');
  check('signed in, dashboard shows', await waitFor(`document.querySelector('nav.nav')`, 'nav'));

  // ---- compose with guardrail problems
  await clickText('.pill-body', 'Facebook');
  await clickText('.pill-body', 'Instagram');
  await setField(
    '#content',
    'Preferred Nu-Wall installer with 25 years of experience. Call us today!',
  );
  check(
    'blocked claim and Instagram media rule show',
    await waitFor(
      `document.querySelectorAll('.notice.err').length >= 2 && document.querySelectorAll('.notice.warn').length >= 2`,
      'notices',
    ),
  );
  check(
    'previews render for both platforms',
    (await evaluate(`document.querySelectorAll('.preview').length`)) === 2,
  );
  await shot('02-compose-blocked');

  // ---- fix the post, add a photo, schedule
  await setField(
    '#content',
    'Before and after: a full recladding in Ponsonby, by a team with more than 10 years on the tools.',
  );
  await clickText('button', 'Choose from library');
  check('photo library modal opens', await waitFor(`document.querySelector('.photo.pick')`, 'library'));
  await evaluate(`document.querySelector('.photo.pick').click()`);
  await clickText('button', 'Use selected');
  check('photo attached', await waitFor(`document.querySelectorAll('.thumbs .thumb').length >= 1`, 'thumb'));
  check(
    'now passes checks (no blocking errors)',
    await waitFor(`document.querySelectorAll('.notice.err').length === 0`, 'clear errors'),
  );
  await shot('03-compose-ready');

  const tomorrow = new Date(Date.now() + 36 * 3600_000);
  const pad = (n) => String(n).padStart(2, '0');
  const local = `${tomorrow.getFullYear()}-${pad(tomorrow.getMonth() + 1)}-${pad(tomorrow.getDate())}T09:00`;
  await setField('#when', local);
  await clickText('button', 'Schedule');
  check('lands on the calendar after scheduling', await waitFor(`document.querySelector('.cal')`, 'calendar'));
  check('a chip is on the calendar', await waitFor(`document.querySelectorAll('.chip').length === 1`, 'chip'));
  await shot('04-calendar');

  // ---- posts list
  await clickText('nav button', 'Posts');
  check(
    'posts list shows the scheduled post',
    await waitFor(`document.querySelectorAll('article.post-card').length === 1`, 'card'),
  );
  check(
    'status badge says Scheduled',
    (await evaluate(`document.querySelector('article .badge').textContent`)) === 'Scheduled',
  );
  await shot('05-posts');
  check(
    'header shows the Pukeko logo',
    await evaluate(`(() => { const i = document.querySelector('.topbar .logo'); return Boolean(i && i.complete && i.naturalWidth > 0); })()`),
  );
  check(
    'Post now offers Facebook and Instagram',
    await evaluate(`(() => {
      const labels = [...document.querySelectorAll('article .postnow button')].map((b) => b.textContent.trim());
      return labels.includes('Post to Facebook') && labels.includes('Post to Instagram');
    })()`),
  );
  check(
    'Post to Facebook is enabled (page was seeded from the website)',
    await evaluate(`(() => {
      const b = [...document.querySelectorAll('article .postnow button')].find((x) => x.textContent.trim() === 'Post to Facebook');
      return Boolean(b) && !b.disabled;
    })()`),
  );
  await clickText('article button', 'Mark as posted');
  check(
    'mark as posted works',
    await waitFor(`document.querySelector('article .badge')?.textContent === 'Posted'`, 'posted badge'),
  );

  // ---- photos
  await clickText('nav button', 'Photos');
  check('photo library lists the upload', await waitFor(`document.querySelectorAll('.photo').length === 1`, 'photo'));
  await shot('06-photos');

  // ---- social pages
  await clickText('nav button', 'Pages');
  check('pages list has the three seeded pages', await waitFor(`document.querySelectorAll('.channel').length === 3`, 'channels'));
  check(
    'no-LinkedIn notice is shown',
    await evaluate(`document.body.textContent.includes('No LinkedIn page yet')`),
  );
  await setField('#ch-name', 'Pukeko Construction');
  await evaluate(`(() => { const s = document.querySelector('#ch-platform'); s.value = 'linkedin'; return true; })()`);
  await setField('#ch-url', 'https://www.linkedin.com/company/pukeko-construction');
  await clickText('button', 'Add page');
  check('LinkedIn page can be added', await waitFor(`document.querySelectorAll('.channel').length === 4`, 'new channel'));
  check(
    'no-LinkedIn notice disappears',
    await evaluate(`!document.body.textContent.includes('No LinkedIn page yet')`),
  );
  await shot('06b-pages');

  // ---- mobile layout
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  await clickText('nav button', 'Compose');
  await waitFor(`document.querySelector('#content')`, 'compose mobile');
  await shot('07-mobile-compose');
  check(
    'no sideways scrolling on a phone-sized screen',
    (await evaluate(`document.documentElement.scrollWidth > window.innerWidth + 1`)) === false,
  );
  await clickText('nav button', 'Calendar');
  await waitFor(`document.querySelector('.cal')`, 'calendar mobile');
  await shot('08-mobile-calendar');
  check(
    'calendar fits a phone-sized screen',
    (await evaluate(`document.documentElement.scrollWidth > window.innerWidth + 1`)) === false,
  );

  ws.close();
}

try {
  await main();
} catch (err) {
  problems.push(`Test run crashed: ${err.stack || err.message}`);
}
await cleanup();

if (problems.length) {
  console.log('\nProblems:');
  for (const p of problems) console.log(` - ${p}`);
  process.exit(1);
}
console.log(`\nAll browser checks passed. Screenshots: ${SHOTS}`);
