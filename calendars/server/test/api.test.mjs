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
const PORT = 45000 + Math.floor(Math.random() * 2000);
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

// Tomorrow at local midnight, as "YYYY-MM-DD" -- always in the future, so
// slot/booking tests never depend on what time the suite happens to run.
function tomorrowDateStr() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
function tomorrowWeekday() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.getDay();
}

before(async () => {
  dataDir = mkdtempSync(path.join(tmpdir(), 'concierge-calendars-test-'));
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
    assert.equal((await api('GET', '/api/windows', undefined, { auth: false })).status, 401);
  });

  it('creates a tenant with a passcode, and logs in with it', async () => {
    const created = await api('POST', '/api/tenants', { name: 'Acme Co' }, { auth: false });
    assert.equal(created.status, 201);
    assert.ok(created.data.tenant.passcode);
    const login = await api('POST', '/api/login', { passcode: created.data.tenant.passcode }, { auth: false });
    assert.equal(login.status, 200);
    tokenA = login.data.token;

    const bad = await api('POST', '/api/login', { passcode: 'nope' }, { auth: false });
    assert.equal(bad.status, 401);
  });

  it('a second tenant is fully isolated from the first', async () => {
    const created = await api('POST', '/api/tenants', { name: 'Bravo Ltd' }, { auth: false });
    const login = await api('POST', '/api/login', { passcode: created.data.tenant.passcode }, { auth: false });
    tokenB = login.data.token;
    assert.notEqual(tokenB, tokenA);
  });
});

describe('availability windows', () => {
  it('rejects a bad window and accepts a good one', async () => {
    assert.equal((await api('POST', '/api/windows', { weekday: 9, start: '09:00', end: '17:00' })).status, 400);
    assert.equal((await api('POST', '/api/windows', { weekday: 1, start: '17:00', end: '09:00' })).status, 400);

    const weekday = tomorrowWeekday();
    const created = await api('POST', '/api/windows', { weekday, start: '00:00', end: '23:30', slot_minutes: 30 });
    assert.equal(created.status, 201);

    const list = await api('GET', '/api/windows');
    assert.equal(list.data.windows.length, 1);
  });

  it('tenant B has no windows of its own', async () => {
    const list = await api('GET', '/api/windows', undefined, { token: tokenB });
    assert.equal(list.data.windows.length, 0);
  });
});

describe('slots and booking', () => {
  const date = tomorrowDateStr();
  let firstSlot;

  it('returns open slots for tomorrow, covering the whole day window', async () => {
    const { status, data } = await api('GET', `/api/slots?date=${date}`);
    assert.equal(status, 200);
    assert.ok(data.slots.length > 40); // ~48 half-hour slots in a near-full day
    firstSlot = data.slots[0];
  });

  it('tenant B sees no slots on the same date (no windows of its own)', async () => {
    const { data } = await api('GET', `/api/slots?date=${date}`, undefined, { token: tokenB });
    assert.equal(data.slots.length, 0);
  });

  it('rejects a booking outside any window', async () => {
    const outside = new Date(Date.parse(firstSlot.start_at));
    outside.setDate(outside.getDate() + 10); // a day with no window configured
    const { status } = await api('POST', '/api/appointments', {
      contact_name: 'Jane Doe',
      start_at: outside.toISOString(),
      duration_minutes: 30,
    });
    assert.equal(status, 422);
  });

  let apptId;

  it('books a real slot', async () => {
    const { status, data } = await api('POST', '/api/appointments', {
      contact_name: 'Jane Doe',
      contact_email: 'jane@example.com',
      start_at: firstSlot.start_at,
      duration_minutes: firstSlot.duration_minutes,
    });
    assert.equal(status, 201);
    assert.equal(data.appointment.status, 'booked');
    apptId = data.appointment.id;
  });

  it('that slot no longer shows as open, and double-booking it is rejected', async () => {
    const { data } = await api('GET', `/api/slots?date=${date}`);
    assert.ok(!data.slots.some((s) => s.start_at === firstSlot.start_at));

    const { status } = await api('POST', '/api/appointments', {
      contact_name: 'Collision Test',
      start_at: firstSlot.start_at,
      duration_minutes: firstSlot.duration_minutes,
    });
    assert.equal(status, 409);
  });

  it('tenant B cannot see or modify tenant A\'s appointment', async () => {
    assert.equal((await api('GET', `/api/appointments/${apptId}`, undefined, { token: tokenB })).status, 404);
    assert.equal(
      (await api('POST', `/api/appointments/${apptId}/status`, { status: 'cancelled' }, { token: tokenB })).status,
      404,
    );
  });

  it('cancelling frees the slot again', async () => {
    const cancelled = await api('POST', `/api/appointments/${apptId}/status`, { status: 'cancelled' });
    assert.equal(cancelled.data.appointment.status, 'cancelled');

    const { data } = await api('GET', `/api/slots?date=${date}`);
    assert.ok(data.slots.some((s) => s.start_at === firstSlot.start_at));
  });

  it('deletes an appointment', async () => {
    const created = await api('POST', '/api/appointments', {
      contact_name: 'To Delete',
      start_at: firstSlot.start_at,
      duration_minutes: firstSlot.duration_minutes,
    });
    const id = created.data.appointment.id;
    assert.equal((await api('DELETE', `/api/appointments/${id}`)).status, 200);
    assert.equal((await api('GET', `/api/appointments/${id}`)).status, 404);
  });
});
