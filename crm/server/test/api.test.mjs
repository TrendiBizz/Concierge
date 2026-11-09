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
const PORT = 43000 + Math.floor(Math.random() * 2000);
const BASE = `http://127.0.0.1:${PORT}`;

let child;
let dataDir;
let tokenA = '';
let tokenB = '';
let tenantA = '';

async function api(method, route, body, { token = tokenA, headers = {}, auth = true } = {}) {
  const init = { method, headers: { ...headers } };
  if (auth && token) init.headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  const res = await fetch(`${BASE}${route}`, init);
  const data = await res.json().catch(() => ({}));
  return { status: res.status, data };
}

before(async () => {
  dataDir = mkdtempSync(path.join(tmpdir(), 'concierge-crm-test-'));
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
    assert.equal((await api('GET', '/api/contacts', undefined, { auth: false })).status, 401);
  });

  it('creates a tenant with a passcode, and logs in with it', async () => {
    const created = await api('POST', '/api/tenants', { name: 'Acme Co' }, { auth: false });
    assert.equal(created.status, 201);
    assert.ok(created.data.tenant.passcode);
    tenantA = created.data.tenant.id;

    const bad = await api('POST', '/api/login', { passcode: 'nope' }, { auth: false });
    assert.equal(bad.status, 401);

    const login = await api('POST', '/api/login', { passcode: created.data.tenant.passcode }, { auth: false });
    assert.equal(login.status, 200);
    assert.equal(login.data.tenant.id, tenantA);
    tokenA = login.data.token;
  });

  it('a second tenant gets its own isolated token', async () => {
    const created = await api('POST', '/api/tenants', { name: 'Bravo Ltd' }, { auth: false });
    const login = await api(
      'POST',
      '/api/login',
      { passcode: created.data.tenant.passcode },
      { auth: false },
    );
    tokenB = login.data.token;
    assert.notEqual(tokenB, tokenA);
  });
});

describe('pipeline stages', () => {
  it('a new tenant gets the default stages', async () => {
    const { status, data } = await api('GET', '/api/stages');
    assert.equal(status, 200);
    assert.deepEqual(data.stages.map((s) => s.name), ['New', 'Contacted', 'Qualified', 'Won', 'Lost']);
  });

  it('a tenant can redefine its stages', async () => {
    const { status, data } = await api('PUT', '/api/stages', { names: ['Lead', 'Quoted', 'Signed'] });
    assert.equal(status, 200);
    assert.deepEqual(data.stages.map((s) => s.name), ['Lead', 'Quoted', 'Signed']);
  });
});

describe('contacts', () => {
  let contactId;

  it('creates, lists and searches contacts', async () => {
    const created = await api('POST', '/api/contacts', { name: 'Jane Doe', email: 'jane@example.com', tags: ['vip'] });
    assert.equal(created.status, 201);
    contactId = created.data.contact.id;

    const list = await api('GET', '/api/contacts');
    assert.equal(list.data.contacts.length, 1);

    const found = await api('GET', '/api/contacts?q=jane');
    assert.equal(found.data.contacts.length, 1);
    const missed = await api('GET', '/api/contacts?q=zzz');
    assert.equal(missed.data.contacts.length, 0);
  });

  it('requires a name', async () => {
    const { status } = await api('POST', '/api/contacts', { email: 'noname@example.com' });
    assert.equal(status, 400);
  });

  it('edits and deletes a contact', async () => {
    const edited = await api('PUT', `/api/contacts/${contactId}`, { phone: '555-1234' });
    assert.equal(edited.data.contact.phone, '555-1234');
    assert.equal(edited.data.contact.name, 'Jane Doe');

    const del = await api('DELETE', `/api/contacts/${contactId}`);
    assert.equal(del.status, 200);
    assert.equal((await api('GET', `/api/contacts/${contactId}`)).status, 404);
  });

  it('a tenant cannot see another tenant\'s contacts', async () => {
    const created = await api('POST', '/api/contacts', { name: 'Cross Tenant Check' });
    const idInA = created.data.contact.id;
    const crossRead = await api('GET', `/api/contacts/${idInA}`, undefined, { token: tokenB });
    assert.equal(crossRead.status, 404);
    const listAsB = await api('GET', '/api/contacts', undefined, { token: tokenB });
    assert.equal(listAsB.data.contacts.length, 0);
  });
});

describe('opportunities', () => {
  let contactId;
  let oppId;

  it('creates an opportunity against a contact, defaulting to the first stage', async () => {
    const contact = await api('POST', '/api/contacts', { name: 'Opportunity Contact' });
    contactId = contact.data.contact.id;

    const created = await api('POST', '/api/opportunities', { contact_id: contactId, title: 'Reclad job', value: 15000 });
    assert.equal(created.status, 201);
    assert.equal(created.data.opportunity.stage, 'Lead');
    oppId = created.data.opportunity.id;
  });

  it('rejects an opportunity for a contact that does not exist', async () => {
    const { status } = await api('POST', '/api/opportunities', { contact_id: 999999, title: 'Ghost', value: 1 });
    assert.equal(status, 400);
  });

  it('moves an opportunity to a different stage', async () => {
    const moved = await api('POST', `/api/opportunities/${oppId}/move`, { stage: 'Quoted' });
    assert.equal(moved.status, 200);
    assert.equal(moved.data.opportunity.stage, 'Quoted');

    const filtered = await api('GET', '/api/opportunities?stage=Quoted');
    assert.equal(filtered.data.opportunities.length, 1);
  });

  it('deletes an opportunity', async () => {
    assert.equal((await api('DELETE', `/api/opportunities/${oppId}`)).status, 200);
    assert.equal((await api('GET', `/api/opportunities/${oppId}`)).status, 404);
  });
});
