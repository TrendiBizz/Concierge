// End-to-end tests: starts the real server on a random port with a temp data folder.
// Run with: npm test   (from the server folder)

import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { after, before, describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';

const serverFile = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'server.js');
const PORT = 49000 + Math.floor(Math.random() * 2000);
const BASE = `http://127.0.0.1:${PORT}`;

let child;
let dataDir;
let tokenA = '';
let tokenB = '';
let tenantAId = '';

async function api(method, route, body, { token = tokenA, auth = true } = {}) {
  const init = { method, headers: {} };
  if (auth && token) init.headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  const res = await fetch(`${BASE}${route}`, init);
  const data = await res.json().catch(() => ({}));
  return { status: res.status, data };
}

async function rawGet(route) {
  const res = await fetch(`${BASE}${route}`);
  return { status: res.status, text: await res.text() };
}

async function rawPostForm(route, form) {
  const res = await fetch(`${BASE}${route}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams(form).toString(),
  });
  return { status: res.status, text: await res.text() };
}

before(async () => {
  dataDir = mkdtempSync(path.join(tmpdir(), 'concierge-sites-test-'));
  child = spawn(process.execPath, [serverFile], {
    env: { ...process.env, PORT: String(PORT), DATA_DIR: dataDir },
    stdio: 'ignore',
  });
  for (let i = 0; i < 50; i += 1) {
    try {
      const res = await fetch(`${BASE}/api/health`);
      if (res.ok) return;
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error('Server did not start');
});

after(() => {
  if (child) child.kill();
  if (dataDir) rmSync(dataDir, { recursive: true, force: true });
});

describe('tenants and auth', () => {
  it('health is public, everything else needs a token', async () => {
    assert.equal((await api('GET', '/api/health', undefined, { auth: false })).status, 200);
    assert.equal((await api('GET', '/api/pages', undefined, { auth: false })).status, 401);
  });

  it('creates a tenant with a passcode, and logs in with it', async () => {
    const created = await api('POST', '/api/tenants', { name: 'Acme Co' }, { auth: false });
    assert.equal(created.status, 201);
    tenantAId = created.data.tenant.id;
    const login = await api('POST', '/api/login', { passcode: created.data.tenant.passcode }, { auth: false });
    tokenA = login.data.token;
    assert.equal((await api('POST', '/api/login', { passcode: 'nope' }, { auth: false })).status, 401);
  });

  it('a second tenant is fully isolated from the first', async () => {
    const created = await api('POST', '/api/tenants', { name: 'Bravo Ltd' }, { auth: false });
    const login = await api('POST', '/api/login', { passcode: created.data.tenant.passcode }, { auth: false });
    tokenB = login.data.token;
    assert.notEqual(tokenB, tokenA);
  });
});

describe('pages', () => {
  let pageId;

  it('creates a page, rejecting a bad slug and a duplicate', async () => {
    assert.equal((await api('POST', '/api/pages', { slug: 'Has Spaces' })).status, 400);
    const created = await api('POST', '/api/pages', { slug: 'landing', title: 'My Landing Page' });
    assert.equal(created.status, 201);
    pageId = created.data.page.id;
    assert.equal(created.data.page.status, 'draft');
    const dup = await api('POST', '/api/pages', { slug: 'landing' });
    assert.equal(dup.status, 409);
  });

  it('a draft page 404s publicly', async () => {
    const { status } = await rawGet(`/site/${tenantAId}/landing`);
    assert.equal(status, 404);
  });

  it('sets blocks on a page, rejecting a bad block type', async () => {
    const badType = await api('PUT', `/api/pages/${pageId}`, { blocks: [{ type: 'nope', content: {} }] });
    assert.equal(badType.status, 400);

    const ok = await api('PUT', `/api/pages/${pageId}`, {
      blocks: [
        { type: 'heading', content: { text: 'Welcome', level: 1 } },
        { type: 'paragraph', content: { text: 'Hello there.' } },
        { type: 'form', content: { fields: ['name', 'email'], submit_label: 'Get started' } },
      ],
    });
    assert.equal(ok.status, 200);
    assert.equal(ok.data.page.blocks.length, 3);
    assert.equal(ok.data.page.blocks[0].content.text, 'Welcome');
  });

  it('publishing makes the page render publicly', async () => {
    const published = await api('POST', `/api/pages/${pageId}/status`, { status: 'published' });
    assert.equal(published.data.page.status, 'published');

    const { status, text: html } = await rawGet(`/site/${tenantAId}/landing`);
    assert.equal(status, 200);
    assert.ok(html.includes('Welcome'));
    assert.ok(html.includes('Hello there.'));
    assert.ok(html.includes('<form'));
    assert.ok(!html.includes('<script')); // no raw script injection from content
  });

  it('a tenant cannot see or edit another tenant\'s page', async () => {
    assert.equal((await api('GET', `/api/pages/${pageId}`, undefined, { token: tokenB })).status, 404);
    assert.equal((await api('POST', `/api/pages/${pageId}/status`, { status: 'draft' }, { token: tokenB })).status, 404);
  });

  it('user-supplied text is escaped, never raw HTML, in the public render', async () => {
    await api('PUT', `/api/pages/${pageId}`, {
      blocks: [{ type: 'paragraph', content: { text: '<script>alert(1)</script>' } }],
    });
    const { text: html } = await rawGet(`/site/${tenantAId}/landing`);
    assert.ok(!html.includes('<script>alert(1)</script>'));
    assert.ok(html.includes('&lt;script&gt;'));
  });

  globalThis.__pageId = () => pageId;
});

describe('leads', () => {
  it('submitting the public form stores a lead, scoped to the right tenant and page', async () => {
    const pageId = globalThis.__pageId();
    const { status, text: html } = await rawPostForm(`/site/${tenantAId}/landing/submit`, {
      name: 'Jane Doe',
      email: 'jane@example.com',
    });
    assert.equal(status, 200);
    assert.ok(html.includes('Thanks'));

    const leads = await api('GET', '/api/leads');
    assert.equal(leads.data.leads.length, 1);
    assert.equal(leads.data.leads[0].data.email, 'jane@example.com');

    const filtered = await api('GET', `/api/leads?page_id=${pageId}`);
    assert.equal(filtered.data.leads.length, 1);

    const asB = await api('GET', '/api/leads', undefined, { token: tokenB });
    assert.equal(asB.data.leads.length, 0);
  });

  it('submitting to an unpublished/nonexistent page 404s, no lead recorded', async () => {
    const { status } = await rawPostForm(`/site/${tenantAId}/does-not-exist/submit`, { name: 'x' });
    assert.equal(status, 404);
    const leads = await api('GET', '/api/leads');
    assert.equal(leads.data.leads.length, 1); // unchanged
  });
});

describe('delete', () => {
  it('deletes a page', async () => {
    const pageId = globalThis.__pageId();
    assert.equal((await api('DELETE', `/api/pages/${pageId}`)).status, 200);
    assert.equal((await api('GET', `/api/pages/${pageId}`)).status, 404);
    const { status } = await rawGet(`/site/${tenantAId}/landing`);
    assert.equal(status, 404);
  });
});
