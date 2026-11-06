// Click-test of the Concierge site navigation in headless Chrome.
//   cd vm/nav-test && npm install && node nav-test.mjs [baseUrl]
// Default base URL: http://localhost:8080  (the site container from ../run.sh)
// Chrome: CHROME_PATH or the macOS default.
// Exit code 0 = all checks passed, 1 = at least one failed.
import puppeteer from 'puppeteer-core';

const BASE = (process.argv[2] || 'http://localhost:8080').replace(/\/+$/, '');
const CHROME = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PAGES = [
  'index', 'about', 'ad-manager', 'ai-chatbot', 'calendars', 'communities', 'contact', 'content-ai',
  'cookies', 'crm', 'ecommerce', 'email-marketing', 'mobile-app', 'payments', 'pricing', 'privacy',
  'reputation', 'security', 'sms-whatsapp', 'terms', 'voice-ai', 'voicemail', 'websites-funnels', 'workflows',
];

const results = [];
function check(page, name, ok, detail = '') {
  results.push({ page, name, ok: !!ok, detail });
  if (!ok) console.log(`  FAIL [${page}] ${name} ${detail}`);
}

const visible = (p, sel) => p.evaluate((s) => {
  const el = document.querySelector(s);
  if (!el) return false;
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
}, sel);

async function open(browser, url, viewport) {
  const p = await browser.newPage();
  await p.setViewport(viewport);
  const errors = [];
  p.on('pageerror', (e) => errors.push(String(e)));
  p.on('console', (m) => { if (m.type() === 'error' && !/favicon|ERR_|Failed to load resource/.test(m.text())) errors.push(m.text()); });
  await p.goto(url, { waitUntil: 'load' });
  return { p, errors };
}

const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] });

try {
  for (const name of PAGES) {
    const url = `${BASE}/${name}.html`;

    // ---------- desktop ----------
    {
      const { p, errors } = await open(browser, url, { width: 1280, height: 800 });
      const id = `${name} desktop`;
      check(id, 'nav present', await p.$('#nav'));
      check(id, 'hamburger hidden', !(await visible(p, '#menuToggle')));
      check(id, 'dropdown closed at start', !(await visible(p, '.mega')));

      const btn = await p.$('#nav button[aria-haspopup="true"]');
      check(id, 'Product button present', btn);
      if (btn) {
        await btn.hover();
        check(id, 'hover opens dropdown', await visible(p, '.mega'));
        // move the pointer down into the panel: it must stay open (no hover gap)
        const box = await (await p.$('.mega > div')).boundingBox();
        await p.mouse.move(box.x + box.width / 2, box.y + 20, { steps: 8 });
        check(id, 'dropdown stays open when pointer enters it', await visible(p, '.mega'));
        await p.mouse.move(640, 700, { steps: 4 });
        check(id, 'pointer away closes dropdown', !(await visible(p, '.mega')));

        await btn.focus();
        check(id, 'keyboard focus opens dropdown', await visible(p, '.mega'));
        await p.evaluate(() => document.activeElement && document.activeElement.blur());
        await p.mouse.move(640, 700);
      }

      const desk = await p.$$eval('.mega a', (as) => as.map((a) => a.getAttribute('href')));
      const mob = await p.$$eval('#mobileMenu a[href$=".html"]', (as) => as.map((a) => a.getAttribute('href')));
      check(id, 'dropdown has links', desk.length >= 10, `count=${desk.length}`);
      const missing = desk.filter((h) => !mob.includes(h));
      check(id, 'every dropdown link also in mobile menu', missing.length === 0, missing.join(','));

      const login = await p.$$eval('[data-app-link]', (as) => as.map((a) => a.href));
      check(id, 'Log in links point at CRM :3010', login.length >= 1 && login.every((h) => /:3010\/$/.test(h)), login.join(','));
      check(id, 'no JS errors', errors.length === 0, errors.join(' | '));
      await p.close();
    }

    // ---------- mobile ----------
    {
      const { p, errors } = await open(browser, url, { width: 390, height: 844, isMobile: true, hasTouch: true });
      const id = `${name} mobile`;
      check(id, 'hamburger visible', await visible(p, '#menuToggle'));
      check(id, 'desktop links hidden', !(await visible(p, '#nav .md\\:flex')));
      check(id, 'menu closed at start', !(await visible(p, '#mobileMenu')));
      await p.tap('#menuToggle');
      check(id, 'tap opens menu', await visible(p, '#mobileMenu'));
      check(id, 'aria-expanded=true when open', (await p.$eval('#menuToggle', (b) => b.getAttribute('aria-expanded'))) === 'true');
      await p.tap('#menuToggle');
      check(id, 'second tap closes menu', !(await visible(p, '#mobileMenu')));
      check(id, 'aria-expanded=false when closed', (await p.$eval('#menuToggle', (b) => b.getAttribute('aria-expanded'))) === 'false');

      // open again and follow a link
      await p.tap('#menuToggle');
      const target = name === 'pricing' ? 'about.html' : 'pricing.html';
      const link = await p.$(`#mobileMenu a[href="${target}"]`);
      check(id, `menu link ${target} present`, link);
      if (link) {
        await Promise.all([p.waitForNavigation({ waitUntil: 'load' }), link.tap()]);
        check(id, `menu link navigates to ${target}`, p.url().endsWith(`/${target}`), p.url());
      }
      check(id, 'no JS errors', errors.length === 0, errors.join(' | '));
      await p.close();
    }
  }

  // ---------- desktop: click a dropdown link and land on the page ----------
  {
    const { p } = await open(browser, `${BASE}/index.html`, { width: 1280, height: 800 });
    await (await p.$('#nav button[aria-haspopup="true"]')).hover();
    const href = await p.$eval('.mega a', (a) => a.getAttribute('href'));
    await Promise.all([p.waitForNavigation({ waitUntil: 'load' }), p.click('.mega a')]);
    check('index desktop', `clicking first dropdown link goes to ${href}`, p.url().endsWith(`/${href}`), p.url());
    await p.close();
  }
} finally {
  await browser.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed across ${PAGES.length} pages (desktop 1280px + mobile 390px).`);
if (failed.length) {
  console.log(`${failed.length} FAILED:`);
  for (const f of failed) console.log(` - [${f.page}] ${f.name} ${f.detail}`);
  process.exit(1);
}
