// End-to-end tests: starts the real server on a random port with a temp data folder,
// plus a tiny real HTTP receiver to prove the webhook action makes a genuine call.
// Run with: npm test   (from the server folder)

import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import http from 'node:http';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { after, before, describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';

const serverFile = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'server.js');
const PORT = 51000 + Math.floor(Math.random() * 2000);
const BASE = `http://127.0.0.1:${PORT}`;

let child;
let dataDir;
let tokenA = '';
let tokenB = '';

// Tiny real receiver for the webhook action to POST to.
let receiver;
let receiverPort;
let received = [];
before((_, done) => {
  receiver = http.createServer((req, res) => {
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => {
      received.push(JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}'));
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end('{"ok":true}');
    });
  });
  receiver.listen(0, '127.0.0.1', () => {
    receiverPort = receiver.address().port;
    done();
  });
});
after(() => receiver.close());

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
  dataDir = mkdtempSync(path.join(tmpdir(), 'concierge-workflows-test-'));
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
    assert.equal((await api('GET', '/api/workflows', undefined, { auth: false })).status, 401);
  });

  it('creates a tenant with a passcode, and logs in with it', async () => {
    const created = await api('POST', '/api/tenants', { name: 'Acme Co' }, { auth: false });
    assert.equal(created.status, 201);
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

describe('creating workflows', () => {
  it('requires a name, event_type, and valid actions', async () => {
    assert.equal((await api('POST', '/api/workflows', { event_type: 'lead.created' })).status, 400);
    assert.equal((await api('POST', '/api/workflows', { name: 'x', event_type: 'lead.created', actions: [{ type: 'nope' }] })).status, 400);
    assert.equal((await api('POST', '/api/workflows', { name: 'x', event_type: 'lead.created', actions: [{ type: 'webhook', url: 'not a url' }] })).status, 400);
  });

  it('creates a workflow with a log action and a webhook action', async () => {
    const created = await api('POST', '/api/workflows', {
      name: 'Welcome new lead',
      event_type: 'lead.created',
      actions: [
        { type: 'log', message: 'New lead: {{name}} ({{email}})' },
        { type: 'webhook', url: `http://127.0.0.1:${receiverPort}/hook` },
      ],
    });
    assert.equal(created.status, 201);
    assert.equal(created.data.workflow.actions.length, 2);
    globalThis.__wfId = () => created.data.workflow.id;
  });
});

describe('firing events', () => {
  it('a matching event runs the workflow, hits the real webhook, and records a run', async () => {
    received = [];
    const fired = await api('POST', '/api/events', { type: 'lead.created', data: { name: 'Jane', email: 'jane@example.com' } });
    assert.equal(fired.status, 200);
    assert.equal(fired.data.matched, 1);
    assert.equal(fired.data.runs[0].ok, true);
    assert.equal(fired.data.runs[0].results[0].detail, 'New lead: Jane (jane@example.com)');
    assert.equal(fired.data.runs[0].results[1].detail, 'HTTP 200');

    assert.equal(received.length, 1);
    assert.equal(received[0].event, 'lead.created');
    assert.equal(received[0].data.name, 'Jane');

    const runs = await api('GET', '/api/runs');
    assert.equal(runs.data.runs.length, 1);
  });

  it('a non-matching event type fires nothing', async () => {
    const fired = await api('POST', '/api/events', { type: 'invoice.paid', data: {} });
    assert.equal(fired.data.matched, 0);
  });

  it('a disabled workflow does not fire', async () => {
    const id = globalThis.__wfId();
    await api('PUT', `/api/workflows/${id}`, { enabled: false });
    const fired = await api('POST', '/api/events', { type: 'lead.created', data: {} });
    assert.equal(fired.data.matched, 0);
    await api('PUT', `/api/workflows/${id}`, { enabled: true }); // restore for later tests
  });

  it('events fired as tenant B never run tenant A\'s workflows', async () => {
    const fired = await api('POST', '/api/events', { type: 'lead.created', data: {} }, { token: tokenB });
    assert.equal(fired.data.matched, 0);
  });

  it('a failing webhook (nothing listening on that port) is recorded as not-ok, run still completes', async () => {
    const created = await api('POST', '/api/workflows', {
      name: 'Broken hook',
      event_type: 'broken.event',
      actions: [{ type: 'webhook', url: 'http://127.0.0.1:1' }],
    });
    const fired = await api('POST', '/api/events', { type: 'broken.event', data: {} });
    assert.equal(fired.data.matched, 1);
    assert.equal(fired.data.runs[0].ok, false);
    assert.equal(fired.data.runs[0].results[0].ok, false);
    void created;
  });
});

describe('delete', () => {
  it('deletes a workflow', async () => {
    const id = globalThis.__wfId();
    assert.equal((await api('DELETE', `/api/workflows/${id}`)).status, 200);
    assert.equal((await api('GET', `/api/workflows/${id}`)).status, 404);
  });
});
