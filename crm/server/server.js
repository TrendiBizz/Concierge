// Concierge CRM server: contacts + a simple sales pipeline. JSON API, zero
// npm dependencies. Requires Node 22.5+ (built-in node:sqlite).
//
// Standalone: no GHL, no third party. Same tenant/auth shape as Concierge's
// other modules (see /Users/jo/Pukeko/SocialSync/server/server.js) so they
// integrate later without reconciling two different auth models.

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
const PORT = Number(process.env.PORT || 4401);
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

// "<tenantId>.<hmac>" -- see SocialSync's server.js for why this shape.
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

const db = openDb(path.join(DATA_DIR, 'crm.db'));
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

function cleanTags(value) {
  if (value === undefined) return undefined;
  if (!Array.isArray(value)) throw new HttpError(400, 'tags must be a list.');
  return value.map((t) => String(t).trim()).filter(Boolean).slice(0, 20);
}

function applyContactInput(base, input) {
  const contact = { ...base };
  if ('name' in input) contact.name = text(input.name, 200, 'name').trim();
  if ('email' in input) contact.email = text(input.email, 200, 'email').trim();
  if ('phone' in input) contact.phone = text(input.phone, 50, 'phone').trim();
  if ('notes' in input) contact.notes = text(input.notes, 5000, 'notes');
  if ('tags' in input) contact.tags = cleanTags(input.tags) ?? contact.tags;
  return contact;
}

function requireContact(tenantId, id) {
  const contact = store.getContact(tenantId, id);
  if (!contact) throw new HttpError(404, 'Contact not found.');
  return contact;
}

function requireOpportunity(tenantId, id) {
  const opp = store.getOpportunity(tenantId, id);
  if (!opp) throw new HttpError(404, 'Opportunity not found.');
  return opp;
}

// ---------------------------------------------------------------- routes

const routes = [];
function route(method, pattern, handler, { auth = true } = {}) {
  routes.push({ method, regex: new RegExp(`^${pattern}$`), handler, auth });
}

route('GET', '/api/health', async ({ res }) => sendJson(res, 200, { ok: true, name: 'Concierge CRM', version: VERSION }), {
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
    store.seedDefaultStages(tenant.id);
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

// ---------------------------------------------------------------- stages

route('GET', '/api/stages', async ({ tenantId, res }) => sendJson(res, 200, { stages: store.listStages(tenantId) }));

route('PUT', '/api/stages', async ({ tenantId, req, res }) => {
  const body = await readJson(req);
  if (!Array.isArray(body.names) || body.names.length === 0) {
    throw new HttpError(400, 'names must be a non-empty list of stage names.');
  }
  const names = body.names.map((n) => text(n, 60, 'stage name').trim()).filter(Boolean);
  if (names.length === 0) throw new HttpError(400, 'At least one stage name is required.');
  sendJson(res, 200, { stages: store.saveStages(tenantId, names) });
});

// ---------------------------------------------------------------- contacts

route('GET', '/api/contacts', async ({ tenantId, url, res }) => {
  const q = (url.searchParams.get('q') || '').toLowerCase().trim();
  let contacts = store.listContacts(tenantId);
  if (q) {
    contacts = contacts.filter(
      (c) => c.name.toLowerCase().includes(q) || c.email.toLowerCase().includes(q),
    );
  }
  sendJson(res, 200, { contacts });
});

route('POST', '/api/contacts', async ({ tenantId, req, res }) => {
  const input = await readJson(req);
  const contact = applyContactInput({ name: '', email: '', phone: '', notes: '', tags: [] }, input);
  if (!contact.name) throw new HttpError(400, 'name is required.');
  sendJson(res, 201, { contact: store.insertContact(tenantId, contact) });
});

route('GET', '/api/contacts/(\\d+)', async ({ tenantId, params, res }) =>
  sendJson(res, 200, { contact: requireContact(tenantId, Number(params[0])) }),
);

route('PUT', '/api/contacts/(\\d+)', async ({ tenantId, req, params, res }) => {
  const existing = requireContact(tenantId, Number(params[0]));
  const next = applyContactInput(existing, await readJson(req));
  if (!next.name) throw new HttpError(400, 'name is required.');
  sendJson(res, 200, { contact: store.saveContact(tenantId, next) });
});

route('DELETE', '/api/contacts/(\\d+)', async ({ tenantId, params, res }) => {
  requireContact(tenantId, Number(params[0]));
  store.deleteContact(tenantId, Number(params[0]));
  sendJson(res, 200, { ok: true });
});

// ---------------------------------------------------------------- opportunities

function applyOppInput(tenantId, base, input) {
  const opp = { ...base };
  if ('contact_id' in input) {
    const id = Number(input.contact_id);
    if (!Number.isInteger(id) || !store.getContact(tenantId, id)) {
      throw new HttpError(400, `Contact ${input.contact_id} does not exist.`);
    }
    opp.contact_id = id;
  }
  if ('title' in input) opp.title = text(input.title, 200, 'title').trim();
  if ('value' in input) {
    const v = Number(input.value);
    if (!Number.isFinite(v) || v < 0) throw new HttpError(400, 'value must be a non-negative number.');
    opp.value = v;
  }
  if ('stage' in input) opp.stage = text(input.stage, 60, 'stage').trim();
  if ('notes' in input) opp.notes = text(input.notes, 5000, 'notes');
  return opp;
}

route('GET', '/api/opportunities', async ({ tenantId, url, res }) => {
  const stage = url.searchParams.get('stage');
  let opps = store.listOpportunities(tenantId);
  if (stage) opps = opps.filter((o) => o.stage === stage);
  sendJson(res, 200, { opportunities: opps });
});

route('POST', '/api/opportunities', async ({ tenantId, req, res }) => {
  const input = await readJson(req);
  const base = { contact_id: 0, title: '', value: 0, stage: '', notes: '' };
  const opp = applyOppInput(tenantId, base, input);
  if (!opp.contact_id) throw new HttpError(400, 'contact_id is required.');
  if (!opp.title) throw new HttpError(400, 'title is required.');
  if (!opp.stage) {
    const stages = store.listStages(tenantId);
    opp.stage = stages[0] ? stages[0].name : '';
  }
  sendJson(res, 201, { opportunity: store.insertOpportunity(tenantId, opp) });
});

route('GET', '/api/opportunities/(\\d+)', async ({ tenantId, params, res }) =>
  sendJson(res, 200, { opportunity: requireOpportunity(tenantId, Number(params[0])) }),
);

route('PUT', '/api/opportunities/(\\d+)', async ({ tenantId, req, params, res }) => {
  const existing = requireOpportunity(tenantId, Number(params[0]));
  const next = applyOppInput(tenantId, existing, await readJson(req));
  sendJson(res, 200, { opportunity: store.saveOpportunity(tenantId, next) });
});

// Dedicated endpoint for the board's "move to stage" action -- same as PUT
// with only `stage` set, but a clearer intent from the dashboard's side.
route('POST', '/api/opportunities/(\\d+)/move', async ({ tenantId, req, params, res }) => {
  const existing = requireOpportunity(tenantId, Number(params[0]));
  const body = await readJson(req);
  const stage = text(body.stage, 60, 'stage').trim();
  if (!stage) throw new HttpError(400, 'stage is required.');
  sendJson(res, 200, { opportunity: store.saveOpportunity(tenantId, { ...existing, stage }) });
});

route('DELETE', '/api/opportunities/(\\d+)', async ({ tenantId, params, res }) => {
  requireOpportunity(tenantId, Number(params[0]));
  store.deleteOpportunity(tenantId, Number(params[0]));
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
  console.log(`Concierge CRM ${VERSION} listening on http://${HOST}:${PORT}`);
  console.log(`Data folder: ${DATA_DIR}`);
  console.log('Create a new customer with: POST /api/tenants { "name": "..." }');
});

export { server };
