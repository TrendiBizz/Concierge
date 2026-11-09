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
const PORT = 47000 + Math.floor(Math.random() * 2000);
const BASE = `http://127.0.0.1:${PORT}`;

let child;
let dataDir;
let tokenA = '';
let tokenB = '';

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

before(async () => {
  dataDir = mkdtempSync(path.join(tmpdir(), 'concierge-payments-test-'));
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
    assert.equal((await api('GET', '/api/invoices', undefined, { auth: false })).status, 401);
  });

  it('creates a tenant with a passcode, and logs in with it', async () => {
    const created = await api('POST', '/api/tenants', { name: 'Acme Co' }, { auth: false });
    assert.equal(created.status, 201);
    const login = await api('POST', '/api/login', { passcode: created.data.tenant.passcode }, { auth: false });
    assert.equal(login.status, 200);
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

describe('creating invoices', () => {
  it('requires a contact name and at least one line item', async () => {
    assert.equal((await api('POST', '/api/invoices', { items: [{ description: 'x', quantity: 1, unit_price: 1 }] })).status, 400);
    assert.equal((await api('POST', '/api/invoices', { contact_name: 'Jane', items: [] })).status, 400);
  });

  it('rejects a bad line item', async () => {
    const { status } = await api('POST', '/api/invoices', {
      contact_name: 'Jane',
      items: [{ description: 'x', quantity: 0, unit_price: 1 }],
    });
    assert.equal(status, 400);
  });

  let invoice;

  it('creates an invoice and computes totals correctly, with sequential numbering', async () => {
    const created = await api('POST', '/api/invoices', {
      contact_name: 'Jane Doe',
      contact_email: 'jane@example.com',
      tax_rate_percent: 10,
      items: [
        { description: 'Design', quantity: 2, unit_price: 100 },
        { description: 'Build', quantity: 1, unit_price: 300 },
      ],
    });
    assert.equal(created.status, 201);
    invoice = created.data.invoice;
    assert.equal(invoice.number, 'INV-0001');
    assert.equal(invoice.status, 'draft');
    assert.equal(invoice.subtotal, 500);
    assert.equal(invoice.tax, 50);
    assert.equal(invoice.total, 550);
  });

  it('numbers the next invoice sequentially, per tenant', async () => {
    const second = await api('POST', '/api/invoices', {
      contact_name: 'Second',
      items: [{ description: 'x', quantity: 1, unit_price: 10 }],
    });
    assert.equal(second.data.invoice.number, 'INV-0002');

    const firstForB = await api(
      'POST',
      '/api/invoices',
      { contact_name: 'First for B', items: [{ description: 'x', quantity: 1, unit_price: 10 }] },
      { token: tokenB },
    );
    assert.equal(firstForB.data.invoice.number, 'INV-0001'); // tenant B's own sequence
  });

  it('a tenant cannot see another tenant\'s invoice', async () => {
    const crossRead = await api('GET', `/api/invoices/${invoice.id}`, undefined, { token: tokenB });
    assert.equal(crossRead.status, 404);
    const listAsB = await api('GET', '/api/invoices', undefined, { token: tokenB });
    assert.equal(listAsB.data.invoices.length, 1); // only its own
  });

  globalThis.__invoiceId = () => invoice.id;
});

describe('editing and status transitions', () => {
  it('edits a draft invoice, replacing its line items', async () => {
    const id = globalThis.__invoiceId();
    const edited = await api('PUT', `/api/invoices/${id}`, {
      items: [{ description: 'Replaced', quantity: 1, unit_price: 999 }],
    });
    assert.equal(edited.status, 200);
    assert.equal(edited.data.invoice.subtotal, 999);
    assert.equal(edited.data.invoice.items.length, 1);
  });

  it('moves draft -> sent -> paid, rejecting invalid jumps', async () => {
    const id = globalThis.__invoiceId();
    const badJump = await api('POST', `/api/invoices/${id}/status`, { status: 'paid' });
    assert.equal(badJump.status, 422);

    const sent = await api('POST', `/api/invoices/${id}/status`, { status: 'sent' });
    assert.equal(sent.data.invoice.status, 'sent');

    const paid = await api('POST', `/api/invoices/${id}/status`, { status: 'paid' });
    assert.equal(paid.data.invoice.status, 'paid');

    const backToDraft = await api('POST', `/api/invoices/${id}/status`, { status: 'draft' });
    assert.equal(backToDraft.status, 422);
  });

  it('a non-draft invoice cannot be edited or deleted', async () => {
    const id = globalThis.__invoiceId();
    assert.equal((await api('PUT', `/api/invoices/${id}`, { notes: 'x' })).status, 409);
    assert.equal((await api('DELETE', `/api/invoices/${id}`)).status, 409);
  });

  it('void is reachable from sent, and a draft can be deleted', async () => {
    const created = await api('POST', '/api/invoices', {
      contact_name: 'Voidable',
      items: [{ description: 'x', quantity: 1, unit_price: 1 }],
    });
    const id = created.data.invoice.id;
    await api('POST', `/api/invoices/${id}/status`, { status: 'sent' });
    const voided = await api('POST', `/api/invoices/${id}/status`, { status: 'void' });
    assert.equal(voided.data.invoice.status, 'void');

    const draft = await api('POST', '/api/invoices', {
      contact_name: 'Deletable',
      items: [{ description: 'x', quantity: 1, unit_price: 1 }],
    });
    assert.equal((await api('DELETE', `/api/invoices/${draft.data.invoice.id}`)).status, 200);
    assert.equal((await api('GET', `/api/invoices/${draft.data.invoice.id}`)).status, 404);
  });
});
