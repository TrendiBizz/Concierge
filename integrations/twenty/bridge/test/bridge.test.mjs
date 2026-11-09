// Tests for the lead bridge. A mock Twenty server records every request.
// NOTE: the mock encodes our ASSUMPTIONS about Twenty's REST shapes. These tests prove the
// bridge's own behaviour; test/live.sh proves the shapes against a real Twenty.
import { test, before, after, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtempSync, rmSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createBridge, validateLead, normalizePhone } from '../server.js';

const KEY = 'test-key-123';
let mock, mockUrl, calls, state;
const bridges = [];

function startMock() {
  return new Promise((resolve) => {
    mock = http.createServer((req, res) => {
      const chunks = [];
      req.on('data', (c) => chunks.push(c));
      req.on('end', () => {
        const raw = Buffer.concat(chunks).toString('utf8');
        const body = raw ? JSON.parse(raw) : null;
        const u = new URL(req.url, 'http://x');
        calls.push({ method: req.method, path: u.pathname, search: u.search, body, auth: req.headers.authorization });
        const send = (st, o) => { res.writeHead(st, { 'content-type': 'application/json' }); res.end(JSON.stringify(o)); };
        if (req.headers.authorization !== 'Bearer ' + KEY) return send(401, { error: 'unauthorized' });
        if (req.method === 'GET' && u.pathname === '/rest/people') {
          const f = decodeURIComponent(u.searchParams.get('filter') || '');
          if (state.malformedEmailLookup && f.includes('emails.primaryEmail')) return send(200, { data: { people: { unexpected: true } } });
          const hitEmail = state.existingEmail && f.includes(state.existingEmail);
          const hitPhone = state.existingPhone && f.includes('phones.primaryPhoneNumber[eq]:"' + state.existingPhone + '"');
          if (state.phoneLookupFails && f.includes('phones.primaryPhoneNumber')) return send(500, { error: 'lookup_error' });
          return send(200, { data: { people: hitEmail || hitPhone ? [{ id: 'p-existing' }] : [] } });
        }
        if (req.method === 'POST' && u.pathname === '/rest/people') return send(state.createStatus || 201, { data: { createPerson: { id: 'p-new' } } });
        if (req.method === 'POST' && u.pathname === '/rest/notes') return state.notesFail ? send(500, { error: 'x' }) : send(201, { data: { createNote: { id: 'n1' } } });
        if (req.method === 'POST' && u.pathname === '/rest/noteTargets') return send(201, { data: { createNoteTarget: { id: 't1' } } });
        return send(404, { error: 'nope' });
      });
    });
    mock.listen(0, '127.0.0.1', () => { mockUrl = 'http://127.0.0.1:' + mock.address().port; resolve(); });
  });
}

async function bridge(opts = {}) {
  const { server } = createBridge({ twentyUrl: mockUrl, apiKey: KEY, ...opts });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  bridges.push(server);
  return 'http://127.0.0.1:' + server.address().port;
}
const post = (base, body, headers = {}) => fetch(base + '/lead', { method: 'POST', headers: { 'content-type': 'application/json', ...headers }, body: typeof body === 'string' ? body : JSON.stringify(body) });

before(startMock);
after(() => { mock.close(); bridges.forEach((s) => s.close()); });
beforeEach(() => { calls = []; state = {}; });

test('normalizePhone: NZ local, international, junk', () => {
  assert.equal(normalizePhone('021 555 0101'), '+64215550101');
  assert.equal(normalizePhone('+61 4 1234 5678'), '+61412345678');
  assert.equal(normalizePhone('0064 21 555 0101'), '+64215550101');
  assert.equal(normalizePhone('abc'), '');
  assert.equal(normalizePhone('123'), '');
  assert.equal(normalizePhone(''), '');
});

test('validateLead: accepts good input and trims/lowercases', () => {
  const r = validateLead({ first_name: ' Ana ', email: 'ANA@Example.com ', message: 'hi' });
  assert.equal(r.lead.first_name, 'Ana');
  assert.equal(r.lead.email, 'ana@example.com');
  assert.equal(r.lead.source, 'website');
});

test('validateLead: rejects bad input', () => {
  assert.equal(validateLead(null).error, 'invalid_json');
  assert.equal(validateLead([]).error, 'invalid_json');
  assert.equal(validateLead({ first_name: 'A' }).error, 'email_or_phone_required');
  assert.equal(validateLead({ first_name: 'A', email: 'nope' }).error, 'invalid_email');
  assert.equal(validateLead({ first_name: 'A', phone: '12' }).error, 'invalid_phone');
  assert.equal(validateLead({ email: '' , phone: '0215550101' }).error, 'name_required');
});

test('validateLead: truncates long fields', () => {
  const r = validateLead({ first_name: 'x'.repeat(500), email: 'a@b.co', message: 'm'.repeat(9999) });
  assert.equal(r.lead.first_name.length, 80);
  assert.equal(r.lead.message.length, 2000);
});

test('new lead: creates person, adds note, sends bearer key', async () => {
  const base = await bridge();
  const r = await post(base, { first_name: 'Ana', last_name: 'Lee', email: 'ana@example.com', phone: '021 555 0101', message: 'Need a quote', plan: 'Starter' });
  const j = await r.json();
  assert.equal(r.status, 200);
  assert.deepEqual({ ok: j.ok, id: j.twenty_id, dup: j.duplicate, note: j.note }, { ok: true, id: 'p-new', dup: false, note: true });
  const create = calls.find((c) => c.method === 'POST' && c.path === '/rest/people');
  assert.equal(create.body.name.firstName, 'Ana');
  assert.equal(create.body.name.lastName, 'Lee');
  assert.equal(create.body.emails.primaryEmail, 'ana@example.com');
  assert.deepEqual(create.body.phones, { primaryPhoneNumber: '215550101', primaryPhoneCountryCode: 'NZ', primaryPhoneCallingCode: '+64' });
  const note = calls.find((c) => c.path === '/rest/notes');
  assert.match(note.body.bodyV2.markdown, /Need a quote/);
  assert.match(note.body.bodyV2.markdown, /Plan: Starter/);
  assert.equal(calls.find((c) => c.path === '/rest/noteTargets').body.targetPersonId, 'p-new');
  assert.ok(calls.every((c) => c.auth === 'Bearer ' + KEY));
});

test('non-NZ phone is stored whole, not guessed', async () => {
  const base = await bridge();
  await post(base, { first_name: 'Bo', email: 'bo@example.com', phone: '+61 412 345 678' });
  const create = calls.find((c) => c.method === 'POST' && c.path === '/rest/people');
  assert.deepEqual(create.body.phones, { primaryPhoneNumber: '+61412345678' });
});

test('duplicate email: no second person, note still added', async () => {
  state.existingEmail = 'ana@example.com';
  const base = await bridge();
  const j = await (await post(base, { first_name: 'Ana', email: 'ana@example.com', message: 'again' })).json();
  assert.equal(j.ok, true);
  assert.equal(j.duplicate, true);
  assert.equal(j.twenty_id, 'p-existing');
  assert.equal(calls.filter((c) => c.method === 'POST' && c.path === '/rest/people').length, 0);
  assert.equal(calls.find((c) => c.path === '/rest/noteTargets').body.targetPersonId, 'p-existing');
});

test('phone-only NZ lead reuses matching person rather than creating duplicate', async () => {
  state.existingPhone = '215550101';
  const base = await bridge();
  const r = await post(base, { first_name: 'Ana', phone: '021 555 0101' });
  const result = await r.json();
  assert.equal(r.status, 200);
  assert.equal(result.duplicate, true);
  assert.equal(result.twenty_id, 'p-existing');
  assert.equal(calls.filter((c) => c.path === '/rest/people' && c.method === 'POST').length, 0);
  const lookup = calls.find((c) => c.path === '/rest/people' && c.method === 'GET');
  assert.match(lookup.search, /primaryPhoneCallingCode/);
});

test('malformed email lookup fails closed before creating a person', async () => {
  state.malformedEmailLookup = true;
  const base = await bridge();
  const r = await post(base, { first_name: 'Ana', email: 'ana@example.com' });
  assert.equal(r.status, 502);
  assert.equal(calls.filter((c) => c.path === '/rest/people' && c.method === 'POST').length, 0);
});

test('phone lookup failure fails closed before create', async () => {
  state.phoneLookupFails = true;
  const base = await bridge();
  const r = await post(base, { first_name: 'Ana', phone: '021 555 0101' });
  assert.equal(r.status, 502);
  assert.equal(calls.filter((c) => c.path === '/rest/people' && c.method === 'POST').length, 0);
});

test('note failure does not fail the lead', async () => {
  state.notesFail = true;
  const base = await bridge();
  const j = await (await post(base, { first_name: 'Ana', email: 'ana@example.com', message: 'hi' })).json();
  assert.equal(j.ok, true);
  assert.equal(j.note, false);
});

test('bad input returns 400 and never reaches Twenty', async () => {
  const base = await bridge();
  for (const body of [{ first_name: 'A' }, { first_name: 'A', email: 'bad' }, '{not json', 'null']) {
    const r = await post(base, body);
    assert.equal(r.status, 400, JSON.stringify(body));
    assert.equal((await r.json()).ok, false);
  }
  assert.equal(calls.length, 0);
});

test('oversized body is rejected', async () => {
  const base = await bridge();
  let status = 0;
  try { status = (await post(base, { first_name: 'A', email: 'a@b.co', message: 'x'.repeat(40000) })).status; }
  catch { status = 413; } // connection may be cut after the limit is hit
  assert.equal(status, 413);
  assert.equal(calls.length, 0);
});

test('honeypot field: pretends success, stores nothing', async () => {
  const base = await bridge();
  const r = await post(base, { first_name: 'Bot', email: 'bot@example.com', website: 'http://spam' });
  assert.equal((await r.json()).ok, true);
  assert.equal(calls.length, 0);
});

test('rate limit: 429 after the limit', async () => {
  const base = await bridge({ rateLimitPerMinute: 3 });
  const codes = [];
  for (let i = 0; i < 5; i++) codes.push((await post(base, { first_name: 'A', email: `a${i}@example.com` })).status);
  assert.deepEqual(codes, [200, 200, 200, 429, 429]);
});

test('Twenty unreachable: 502 so the site falls back to email', async () => {
  const base = await bridge({ twentyUrl: 'http://127.0.0.1:1' });
  const r = await post(base, { first_name: 'Ana', email: 'ana@example.com' });
  assert.equal(r.status, 502);
  assert.equal((await r.json()).error, 'crm_unavailable');
});

test('no API key: 503 not_configured', async () => {
  const base = await bridge({ apiKey: '' });
  const r = await post(base, { first_name: 'Ana', email: 'ana@example.com' });
  assert.equal(r.status, 503);
  assert.equal((await r.json()).error, 'not_configured');
});

test('wrong API key: 503 not_configured (no key detail leaked)', async () => {
  const base = await bridge({ apiKey: 'wrong' });
  const r = await post(base, { first_name: 'Ana', email: 'ana@example.com' });
  const j = await r.json();
  assert.equal(r.status, 503);
  assert.equal(j.error, 'not_configured');
  assert.ok(!JSON.stringify(j).includes('wrong'));
});

test('Twenty create error: 502', async () => {
  state.createStatus = 500;
  const base = await bridge();
  const r = await post(base, { first_name: 'Ana', email: 'ana@example.com' });
  assert.equal(r.status, 502);
});

test('CORS: preflight and origin allow-list', async () => {
  const open = await bridge();
  const pre = await fetch(open + '/lead', { method: 'OPTIONS', headers: { origin: 'http://site.test' } });
  assert.equal(pre.status, 204);
  assert.equal(pre.headers.get('access-control-allow-origin'), '*');
  const locked = await bridge({ allowedOrigins: 'http://site.test' });
  const ok = await fetch(locked + '/lead', { method: 'OPTIONS', headers: { origin: 'http://site.test' } });
  const no = await fetch(locked + '/lead', { method: 'OPTIONS', headers: { origin: 'http://evil.test' } });
  assert.equal(ok.headers.get('access-control-allow-origin'), 'http://site.test');
  assert.equal(no.headers.get('access-control-allow-origin'), null);
});

test('health and 404', async () => {
  const base = await bridge();
  const h = await (await fetch(base + '/health')).json();
  assert.deepEqual(h, { ok: true, configured: true });
  assert.equal((await fetch(base + '/nope')).status, 404);
  assert.equal((await fetch(base + '/lead')).status, 404);
});

test('private Docker bridge rejects requests missing its service credential', async (t) => {
  const secret = 'test-only-private-service-token-0123456789';
  const { server } = createBridge({
    apiKey: 'never-used',
    internalSecret: secret,
    twentyUrl: 'http://127.0.0.1:1',
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise((resolve) => server.close(resolve)));
  const url = 'http://127.0.0.1:' + server.address().port + '/lead';
  const body = JSON.stringify({ email: 'person@example.test', first_name: 'Example' });
  const unauthorized = await fetch(url, { method: 'POST', body, headers: {
    'content-type': 'application/json',
  }});
  assert.equal(unauthorized.status, 401);
  const bad = await fetch(url, { method: 'POST', body, headers: {
    'content-type': 'application/json',
    authorization: 'Bearer wrong-credential',
  }});
  assert.equal(bad.status, 401);
  // Valid authentication reaches normal request validation, not a security bypass.
  const valid = await fetch(url, { method: 'POST', body: '{}', headers: {
    'content-type': 'application/json',
    authorization: 'Bearer ' + secret,
  }});
  assert.equal(valid.status, 400);
});

test('private ledger requires valid delivery id before CRM is touched', async (t) => {
  const dir = mkdtempSync(path.join(tmpdir(), 'trendi-crm-ledger-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const base = await bridge({ idempotencyDir: dir, requireDeliveryId: true });
  for (const delivery_id of [undefined, 'bad', 'a'.repeat(63)]) {
    const r = await post(base, { email: 'ana@example.com', first_name: 'Ana', delivery_id });
    assert.equal(r.status, 400);
  }
  assert.equal(calls.length, 0);
});

test('completed delivery replays receipt without second person or note', async (t) => {
  const dir = mkdtempSync(path.join(tmpdir(), 'trendi-crm-ledger-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const delivery_id = 'a'.repeat(64);
  const payload = { email: 'ana@example.com', first_name: 'Ana', delivery_id };
  const first = await bridge({ idempotencyDir: dir, requireDeliveryId: true });
  const firstResponse = await post(first, payload);
  assert.equal(firstResponse.status, 200);
  const receipt = await firstResponse.json();
  assert.equal(receipt.note, true);
  const second = await bridge({ idempotencyDir: dir, requireDeliveryId: true });
  const replay = await post(second, payload);
  assert.equal(replay.status, 200);
  assert.deepEqual(await replay.json(), receipt);
  assert.equal(calls.filter((c) => c.path === '/rest/people' && c.method === 'POST').length, 1);
  assert.equal(calls.filter((c) => c.path === '/rest/notes').length, 1);
  assert.equal(readdirSync(dir).filter((f) => f.endsWith('.done')).length, 1);
});

test('two concurrent requests for one event cannot create two notes', async (t) => {
  const dir = mkdtempSync(path.join(tmpdir(), 'trendi-crm-ledger-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const base = await bridge({ idempotencyDir: dir, requireDeliveryId: true });
  const payload = { email: 'ana@example.com', first_name: 'Ana', delivery_id: 'b'.repeat(64) };
  const pair = await Promise.all([post(base, payload), post(base, payload)]);
  assert.deepEqual(pair.map((r) => r.status).sort(), [200, 409]);
  assert.equal(calls.filter((c) => c.path === '/rest/people' && c.method === 'POST').length, 1);
  assert.equal(calls.filter((c) => c.path === '/rest/notes').length, 1);
});

test('failed note remains uncertain and never auto-duplicates', async (t) => {
  const dir = mkdtempSync(path.join(tmpdir(), 'trendi-crm-ledger-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  state.notesFail = true;
  const base = await bridge({ idempotencyDir: dir, requireDeliveryId: true });
  const payload = { email: 'ana@example.com', first_name: 'Ana', delivery_id: 'c'.repeat(64) };
  const original = await post(base, payload);
  assert.equal(original.status, 200);
  assert.equal((await original.json()).note, false);
  const replay = await post(base, payload);
  assert.equal(replay.status, 409);
  assert.equal((await replay.json()).error, 'delivery_outcome_uncertain');
  assert.equal(calls.filter((c) => c.path === '/rest/people' && c.method === 'POST').length, 1);
  assert.equal(calls.filter((c) => c.path === '/rest/notes').length, 1);
});

test('same delivery ID cannot be reused for a changed payload', async (t) => {
  const dir = mkdtempSync(path.join(tmpdir(), 'trendi-crm-ledger-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const base = await bridge({ idempotencyDir: dir, requireDeliveryId: true });
  const delivery_id = 'd'.repeat(64);
  assert.equal((await post(base, { first_name: 'Ana', email: 'ana@example.com', delivery_id })).status, 200);
  const changed = await post(base, { first_name: 'Ana', email: 'other@example.com', delivery_id });
  assert.equal(changed.status, 409);
  assert.equal(calls.filter((c) => c.path === '/rest/people' && c.method === 'POST').length, 1);
  assert.equal(calls.filter((c) => c.path === '/rest/notes').length, 1);
});
