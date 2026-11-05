// Concierge Calendars server: one availability-window booking calendar per
// tenant. JSON API, zero npm dependencies. Requires Node 22.5+ (built-in
// node:sqlite).
//
// Standalone: no GHL, no third party. Same tenant/auth shape as Concierge's
// other modules (see /Users/jo/Concierge/crm/server/server.js) so they
// integrate later without reconciling different auth models.
//
// Timezone note: every time in this module is the SERVER's own local time.
// There is no timezone conversion anywhere. Fine for one tenant/one region
// testing on one machine; a real limitation once tenants and customers are
// in different timezones -- see README "Next steps".

import http from 'node:http';
import { createHmac, randomBytes, timingSafeEqual } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { makeStore, openDb } from './db.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const DATA_DIR = path.resolve(process.env.DATA_DIR || path.join(ROOT, 'data'));
const WEB_DIR = path.join(ROOT, 'web');
const PORT = Number(process.env.PORT || 4402);
const HOST = process.env.HOST || '127.0.0.1';
const MAX_JSON_BYTES = 1024 * 1024;
const VERSION = '1.0.0';

mkdirSync(DATA_DIR, { recursive: true });

// ---------------------------------------------------------------- config / auth

const PASSCODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';

function generatePasscode() {
  const bytes = randomBytes(8);
  return Array.from(bytes, (b) => PASSCODE_ALPHABET[b % PASSCODE_ALPHABET.length]).join('');
}

function loadConfig() {
  const file = path.join(DATA_DIR, 'config.json');
  let cfg = {};
  if (existsSync(file)) {
    try {
      cfg = JSON.parse(readFileSync(file, 'utf8'));
    } catch {
      cfg = {};
    }
  }
  if (!cfg.secret) {
    cfg.secret = randomBytes(32).toString('hex');
    writeFileSync(file, JSON.stringify(cfg, null, 2), { mode: 0o600 });
  }
  return cfg;
}

const config = loadConfig();

function safeEqual(a, b) {
  const left = Buffer.from(String(a));
  const right = Buffer.from(String(b));
  return left.length === right.length && timingSafeEqual(left, right);
}

function tenantToken(tenantId) {
  const mac = createHmac('sha256', config.secret).update(`concierge-tenant:${tenantId}`).digest('hex');
  return `${tenantId}.${mac}`;
}

function authedTenant(req, url) {
  const bearer = /^Bearer\s+(.+)$/i.exec(req.headers.authorization || '');
  const token = (bearer && bearer[1]) || url.searchParams.get('token') || '';
  const dot = token.indexOf('.');
  if (dot <= 0) return null;
  const tenantId = token.slice(0, dot);
  if (!safeEqual(token, tenantToken(tenantId))) return null;
  return tenantId;
}

const loginAttempts = new Map();

function loginAllowed(ip) {
  const stamp = Date.now();
  const entry = loginAttempts.get(ip);
  if (!entry || entry.resetAt < stamp) {
    loginAttempts.set(ip, { count: 1, resetAt: stamp + 60_000 });
    return true;
  }
  entry.count += 1;
  return entry.count <= 10;
}

// ---------------------------------------------------------------- state

const db = openDb(path.join(DATA_DIR, 'calendars.db'));
const store = makeStore(db);

function slugify(name) {
  return (
    String(name || '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 40) || 'customer'
  );
}

// ---------------------------------------------------------------- helpers

class HttpError extends Error {
  constructor(status, message, extra = {}) {
    super(message);
    this.status = status;
    this.extra = extra;
  }
}

function sendJson(res, status, body) {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(payload),
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
  });
  res.end(payload);
}

function readBody(req, limit) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on('data', (chunk) => {
      size += chunk.length;
      if (size > limit) {
        reject(new HttpError(413, 'Request body is too large.'));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

async function readJson(req) {
  const raw = await readBody(req, MAX_JSON_BYTES);
  if (raw.length === 0) return {};
  try {
    const value = JSON.parse(raw.toString('utf8'));
    if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new Error('not an object');
    return value;
  } catch {
    throw new HttpError(400, 'Request body must be a JSON object.');
  }
}

function text(value, max, field) {
  if (value === undefined || value === null) return '';
  if (typeof value !== 'string') throw new HttpError(400, `${field} must be text.`);
  if (value.length > max) throw new HttpError(400, `${field} is too long (max ${max}).`);
  return value;
}

function parseHHMM(value, field) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(value || ''));
  if (!m) throw new HttpError(400, `${field} must be "HH:MM".`);
  const hh = Number(m[1]);
  const mm = Number(m[2]);
  if (hh > 23 || mm > 59) throw new HttpError(400, `${field} must be a valid time.`);
  return hh * 60 + mm;
}

// ---------------------------------------------------------------- slot math

// Midnight (local time) for a "YYYY-MM-DD" string.
function dayStart(dateStr) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(dateStr || ''));
  if (!m) throw new HttpError(400, 'date must be "YYYY-MM-DD".');
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  if (Number.isNaN(d.getTime())) throw new HttpError(400, 'date is not a real date.');
  return d;
}

// Every open slot on `dateStr`, as ISO start times, minus anything already
// booked (any non-cancelled appointment overlapping the slot is excluded).
function slotsFor(tenantId, dateStr) {
  const start = dayStart(dateStr);
  const weekday = start.getDay();
  const windows = store.listWindows(tenantId).filter((w) => w.weekday === weekday);
  if (windows.length === 0) return [];

  const dayEnd = new Date(start);
  dayEnd.setDate(dayEnd.getDate() + 1);
  const taken = store
    .listAppointmentsBetween(tenantId, start.toISOString(), dayEnd.toISOString())
    .filter((a) => a.status !== 'cancelled');

  const overlaps = (slotStartMs, slotEndMs) =>
    taken.some((a) => {
      const aStart = Date.parse(a.start_at);
      const aEnd = aStart + a.duration_minutes * 60_000;
      return slotStartMs < aEnd && aStart < slotEndMs;
    });

  const slots = [];
  for (const w of windows) {
    for (let m = w.start_minutes; m + w.slot_minutes <= w.end_minutes; m += w.slot_minutes) {
      const slotStart = new Date(start);
      slotStart.setMinutes(m);
      const slotStartMs = slotStart.getTime();
      const slotEndMs = slotStartMs + w.slot_minutes * 60_000;
      if (slotStartMs < Date.now()) continue; // no slots in the past
      if (overlaps(slotStartMs, slotEndMs)) continue;
      slots.push({ start_at: slotStart.toISOString(), duration_minutes: w.slot_minutes });
    }
  }
  slots.sort((a, b) => Date.parse(a.start_at) - Date.parse(b.start_at));
  return slots;
}

// True if [startMs, startMs+durationMs) sits fully inside one of the
// tenant's availability windows for that weekday.
function withinWindow(tenantId, startMs, durationMinutes) {
  const start = new Date(startMs);
  const weekday = start.getDay();
  const minutesOfDay = start.getHours() * 60 + start.getMinutes();
  const endMinutes = minutesOfDay + durationMinutes;
  return store
    .listWindows(tenantId)
    .some((w) => w.weekday === weekday && minutesOfDay >= w.start_minutes && endMinutes <= w.end_minutes);
}

function collides(tenantId, startMs, durationMinutes, excludeId) {
  const endMs = startMs + durationMinutes * 60_000;
  const dayStartMs = new Date(startMs).setHours(0, 0, 0, 0);
  const dayEndMs = dayStartMs + 24 * 3600_000;
  return store
    .listAppointmentsBetween(tenantId, new Date(dayStartMs).toISOString(), new Date(dayEndMs).toISOString())
    .filter((a) => a.status !== 'cancelled' && a.id !== excludeId)
    .some((a) => {
      const aStart = Date.parse(a.start_at);
      const aEnd = aStart + a.duration_minutes * 60_000;
      return startMs < aEnd && aStart < endMs;
    });
}

// ---------------------------------------------------------------- routes

const routes = [];
function route(method, pattern, handler, { auth = true } = {}) {
  routes.push({ method, regex: new RegExp(`^${pattern}$`), handler, auth });
}

route('GET', '/api/health', async ({ res }) => sendJson(res, 200, { ok: true, name: 'Concierge Calendars', version: VERSION }), {
  auth: false,
});

route(
  'POST',
  '/api/tenants',
  async ({ req, res }) => {
    const body = await readJson(req);
    const name = text(body.name || '', 200, 'name').trim();
    if (!name) throw new HttpError(400, 'name is required.');
    let id = slugify(name);
    if (store.getTenant(id)) id = `${id}-${randomBytes(2).toString('hex')}`;
    const passcode = generatePasscode();
    const tenant = store.insertTenant(id, name, passcode);
    sendJson(res, 201, { tenant: { id: tenant.id, name: tenant.name, passcode } });
  },
  { auth: false },
);

route(
  'POST',
  '/api/login',
  async ({ req, res }) => {
    const ip = req.socket.remoteAddress || 'unknown';
    if (!loginAllowed(ip)) throw new HttpError(429, 'Too many attempts. Wait a minute and try again.');
    const body = await readJson(req);
    const given = typeof body.passcode === 'string' ? body.passcode.trim() : '';
    const tenant = given ? store.getTenantByPasscode(given) : null;
    if (!tenant) throw new HttpError(401, 'Wrong passcode.');
    sendJson(res, 200, { tenant, token: tenantToken(tenant.id) });
  },
  { auth: false },
);

// ---------------------------------------------------------------- windows

route('GET', '/api/windows', async ({ tenantId, res }) => sendJson(res, 200, { windows: store.listWindows(tenantId) }));

route('POST', '/api/windows', async ({ tenantId, req, res }) => {
  const body = await readJson(req);
  const weekday = Number(body.weekday);
  if (!Number.isInteger(weekday) || weekday < 0 || weekday > 6) {
    throw new HttpError(400, 'weekday must be 0 (Sunday) through 6 (Saturday).');
  }
  const start = parseHHMM(body.start, 'start');
  const end = parseHHMM(body.end, 'end');
  if (end <= start) throw new HttpError(400, 'end must be after start.');
  const slotMinutes = Number(body.slot_minutes) || 30;
  if (slotMinutes < 5 || slotMinutes > 480) throw new HttpError(400, 'slot_minutes must be between 5 and 480.');
  const w = store.insertWindow(tenantId, { weekday, start_minutes: start, end_minutes: end, slot_minutes: slotMinutes });
  sendJson(res, 201, { window: w });
});

route('DELETE', '/api/windows/(\\d+)', async ({ tenantId, params, res }) => {
  if (!store.deleteWindow(tenantId, Number(params[0]))) throw new HttpError(404, 'Window not found.');
  sendJson(res, 200, { ok: true });
});

// ---------------------------------------------------------------- slots

route('GET', '/api/slots', async ({ tenantId, url, res }) => {
  const date = url.searchParams.get('date');
  if (!date) throw new HttpError(400, 'date query param is required ("YYYY-MM-DD").');
  sendJson(res, 200, { slots: slotsFor(tenantId, date) });
});

// ---------------------------------------------------------------- appointments

route('GET', '/api/appointments', async ({ tenantId, url, res }) => {
  const from = url.searchParams.get('from');
  const to = url.searchParams.get('to');
  const appts = from && to ? store.listAppointmentsBetween(tenantId, from, to) : store.listAppointments(tenantId);
  sendJson(res, 200, { appointments: appts });
});

route('GET', '/api/appointments/(\\d+)', async ({ tenantId, params, res }) => {
  const appt = store.getAppointment(tenantId, Number(params[0]));
  if (!appt) throw new HttpError(404, 'Appointment not found.');
  sendJson(res, 200, { appointment: appt });
});

route('POST', '/api/appointments', async ({ tenantId, req, res }) => {
  const body = await readJson(req);
  const contactName = text(body.contact_name || '', 200, 'contact_name').trim();
  if (!contactName) throw new HttpError(400, 'contact_name is required.');
  const startAt = typeof body.start_at === 'string' ? body.start_at : '';
  const startMs = Date.parse(startAt);
  if (!Number.isFinite(startMs)) throw new HttpError(400, 'start_at must be a valid ISO date-time.');
  const durationMinutes = Number(body.duration_minutes) || 30;
  if (durationMinutes < 5 || durationMinutes > 480) throw new HttpError(400, 'duration_minutes must be between 5 and 480.');

  if (!withinWindow(tenantId, startMs, durationMinutes)) {
    throw new HttpError(422, 'That time is outside any availability window.');
  }
  if (collides(tenantId, startMs, durationMinutes, -1)) {
    throw new HttpError(409, 'That time overlaps an existing appointment.');
  }

  const appt = store.insertAppointment(tenantId, {
    contact_name: contactName,
    contact_email: text(body.contact_email || '', 200, 'contact_email').trim(),
    contact_phone: text(body.contact_phone || '', 50, 'contact_phone').trim(),
    start_at: new Date(startMs).toISOString(),
    duration_minutes: durationMinutes,
    status: 'booked',
    notes: text(body.notes || '', 2000, 'notes'),
  });
  sendJson(res, 201, { appointment: appt });
});

route('POST', '/api/appointments/(\\d+)/status', async ({ tenantId, req, params, res }) => {
  const appt = store.getAppointment(tenantId, Number(params[0]));
  if (!appt) throw new HttpError(404, 'Appointment not found.');
  const body = await readJson(req);
  const status = text(body.status, 20, 'status');
  if (!['booked', 'completed', 'cancelled'].includes(status)) {
    throw new HttpError(400, 'status must be booked, completed or cancelled.');
  }
  sendJson(res, 200, { appointment: store.setAppointmentStatus(tenantId, appt.id, status) });
});

route('DELETE', '/api/appointments/(\\d+)', async ({ tenantId, params, res }) => {
  if (!store.deleteAppointment(tenantId, Number(params[0]))) throw new HttpError(404, 'Appointment not found.');
  sendJson(res, 200, { ok: true });
});

// ---------------------------------------------------------------- static files

const STATIC_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.ico': 'image/x-icon',
};

function serveStatic(req, res, pathname) {
  let rel;
  try {
    rel = decodeURIComponent(pathname);
  } catch {
    throw new HttpError(400, 'Bad path.');
  }
  if (rel === '/' || rel === '') rel = '/index.html';
  const file = path.normalize(path.join(WEB_DIR, rel));
  if (!file.startsWith(WEB_DIR + path.sep) || !existsSync(file)) throw new HttpError(404, 'Not found.');
  const mime = STATIC_TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream';
  const body = readFileSync(file);
  res.writeHead(200, { 'Content-Type': mime, 'Cache-Control': 'no-cache' });
  res.end(body);
}

// ---------------------------------------------------------------- server

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://localhost');
    const pathname = url.pathname;

    if (pathname.startsWith('/api/')) {
      for (const r of routes) {
        if (r.method !== req.method) continue;
        const match = r.regex.exec(pathname);
        if (!match) continue;
        let tenantId = null;
        if (r.auth) {
          tenantId = authedTenant(req, url);
          if (!tenantId) throw new HttpError(401, 'Sign in required.');
        }
        await r.handler({ req, res, url, params: match.slice(1), tenantId });
        return;
      }
      throw new HttpError(404, 'Unknown API route.');
    }

    if (req.method !== 'GET' && req.method !== 'HEAD') throw new HttpError(405, 'Method not allowed.');
    serveStatic(req, res, pathname);
  } catch (err) {
    if (res.headersSent) {
      res.end();
      return;
    }
    if (err instanceof HttpError) {
      sendJson(res, err.status, { error: err.message, ...err.extra });
    } else {
      console.error(err);
      sendJson(res, 500, { error: 'Something went wrong on the server.' });
    }
  }
});

server.listen(PORT, HOST, () => {
  console.log(`Concierge Calendars ${VERSION} listening on http://${HOST}:${PORT}`);
  console.log(`Data folder: ${DATA_DIR}`);
  console.log('Create a new customer with: POST /api/tenants { "name": "..." }');
});

export { server };
