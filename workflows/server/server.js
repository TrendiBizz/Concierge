// Concierge Workflows server: event-triggered automations. JSON API, zero
// npm dependencies. Requires Node 22.5+ (built-in node:sqlite and fetch).
//
// An automation has one trigger (an event_type string) and an ordered list
// of actions. Only two action types exist: "log" (records a message, with
// {{field}} substituted from the event's data) and "webhook" (a real HTTP
// POST of the event to a URL you control). There is no built-in email/SMS
// sending and no live wiring to Concierge's other modules yet -- see README.
//
// Standalone: no GHL, no third party. Same tenant/auth shape as Concierge's
// other modules (see /Users/jo/Concierge/crm/server/server.js).

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
const PORT = Number(process.env.PORT || 4405);
const HOST = process.env.HOST || '127.0.0.1';
const MAX_JSON_BYTES = 1024 * 1024;
const WEBHOOK_TIMEOUT_MS = 5000;
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

const db = openDb(path.join(DATA_DIR, 'workflows.db'));
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

// ---------------------------------------------------------------- actions

const ACTION_TYPES = ['log', 'webhook'];

function cleanAction(a, i) {
  if (!ACTION_TYPES.includes(a.type)) throw new HttpError(400, `actions[${i}].type must be one of: ${ACTION_TYPES.join(', ')}.`);
  if (a.type === 'log') {
    return { type: 'log', message: text(a.message, 500, `actions[${i}].message`) || 'Workflow ran.' };
  }
  const url = text(a.url, 1000, `actions[${i}].url`);
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') throw new Error('bad protocol');
  } catch {
    throw new HttpError(400, `actions[${i}].url must be a full http(s) URL.`);
  }
  return { type: 'webhook', url };
}

function substitute(template, data) {
  return String(template).replace(/\{\{\s*([\w.]+)\s*\}\}/g, (m, key) => (key in data ? String(data[key]) : m));
}

async function runAction(action, eventType, eventData) {
  if (action.type === 'log') {
    return { type: 'log', ok: true, detail: substitute(action.message, eventData) };
  }
  // webhook
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), WEBHOOK_TIMEOUT_MS);
  try {
    const res = await fetch(action.url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event: eventType, data: eventData }),
      signal: controller.signal,
    });
    return { type: 'webhook', ok: res.ok, detail: `HTTP ${res.status}` };
  } catch (err) {
    return { type: 'webhook', ok: false, detail: `Request failed: ${err.message}` };
  } finally {
    clearTimeout(timer);
  }
}

async function fireEvent(tenantId, eventType, eventData) {
  const workflows = store.listWorkflowsForEvent(tenantId, eventType);
  const runs = [];
  for (const wf of workflows) {
    const results = [];
    for (const action of wf.actions) {
      results.push(await runAction(action, eventType, eventData)); // eslint-disable-line no-await-in-loop
    }
    const ok = results.every((r) => r.ok);
    store.recordRun(tenantId, wf.id, eventType, eventData, results, ok);
    runs.push({ workflow_id: wf.id, workflow_name: wf.name, ok, results });
  }
  return runs;
}

function requireWorkflow(tenantId, id) {
  const wf = store.getWorkflow(tenantId, id);
  if (!wf) throw new HttpError(404, 'Workflow not found.');
  return wf;
}

// ---------------------------------------------------------------- routes

const routes = [];
function route(method, pattern, handler, { auth = true } = {}) {
  routes.push({ method, regex: new RegExp(`^${pattern}$`), handler, auth });
}

route('GET', '/api/health', async ({ res }) => sendJson(res, 200, { ok: true, name: 'Concierge Workflows', version: VERSION }), {
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

// ---------------------------------------------------------------- workflows

route('GET', '/api/workflows', async ({ tenantId, res }) => sendJson(res, 200, { workflows: store.listWorkflows(tenantId) }));

route('POST', '/api/workflows', async ({ tenantId, req, res }) => {
  const body = await readJson(req);
  const name = text(body.name || '', 200, 'name').trim();
  if (!name) throw new HttpError(400, 'name is required.');
  const eventType = text(body.event_type || '', 100, 'event_type').trim();
  if (!eventType) throw new HttpError(400, 'event_type is required.');
  const actions = Array.isArray(body.actions) ? body.actions.map(cleanAction) : [];
  const wf = store.insertWorkflow(tenantId, { name, event_type: eventType, enabled: body.enabled !== false, actions });
  sendJson(res, 201, { workflow: wf });
});

route('GET', '/api/workflows/(\\d+)', async ({ tenantId, params, res }) =>
  sendJson(res, 200, { workflow: requireWorkflow(tenantId, Number(params[0])) }),
);

route('PUT', '/api/workflows/(\\d+)', async ({ tenantId, req, params, res }) => {
  const existing = requireWorkflow(tenantId, Number(params[0]));
  const body = await readJson(req);
  const next = {
    name: 'name' in body ? text(body.name, 200, 'name').trim() || existing.name : existing.name,
    event_type: 'event_type' in body ? text(body.event_type, 100, 'event_type').trim() || existing.event_type : existing.event_type,
    enabled: 'enabled' in body ? Boolean(body.enabled) : existing.enabled,
    actions: 'actions' in body ? body.actions.map(cleanAction) : existing.actions,
  };
  sendJson(res, 200, { workflow: store.saveWorkflow(tenantId, existing.id, next) });
});

route('DELETE', '/api/workflows/(\\d+)', async ({ tenantId, params, res }) => {
  if (!store.deleteWorkflow(tenantId, Number(params[0]))) throw new HttpError(404, 'Workflow not found.');
  sendJson(res, 200, { ok: true });
});

// ---------------------------------------------------------------- events + runs

route('POST', '/api/events', async ({ tenantId, req, res }) => {
  const body = await readJson(req);
  const eventType = text(body.type || '', 100, 'type').trim();
  if (!eventType) throw new HttpError(400, 'type is required.');
  const data = body.data && typeof body.data === 'object' && !Array.isArray(body.data) ? body.data : {};
  const runs = await fireEvent(tenantId, eventType, data);
  sendJson(res, 200, { matched: runs.length, runs });
});

route('GET', '/api/runs', async ({ tenantId, url, res }) => {
  const workflowId = url.searchParams.get('workflow_id');
  const runs = workflowId ? store.listRunsForWorkflow(tenantId, Number(workflowId)) : store.listRuns(tenantId);
  sendJson(res, 200, { runs });
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
  console.log(`Concierge Workflows ${VERSION} listening on http://${HOST}:${PORT}`);
  console.log(`Data folder: ${DATA_DIR}`);
  console.log('Create a new customer with: POST /api/tenants { "name": "..." }');
});

export { server };
