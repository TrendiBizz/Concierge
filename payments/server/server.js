// Concierge Payments server: invoicing with manual status tracking. JSON
// API, zero npm dependencies. Requires Node 22.5+ (built-in node:sqlite).
//
// NO REAL PAYMENT PROCESSING. There is no Stripe/PayPal/gateway integration
// anywhere in this module. "Mark as paid" is a manual action the tenant
// clicks after being paid some other way -- this only tracks status. See
// README.
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
const PORT = Number(process.env.PORT || 4403);
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

const db = openDb(path.join(DATA_DIR, 'payments.db'));
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

function cleanItems(value) {
  if (!Array.isArray(value)) throw new HttpError(400, 'items must be a list.');
  if (value.length > 100) throw new HttpError(400, 'At most 100 line items per invoice.');
  return value.map((it, i) => {
    const description = text(it.description, 500, `items[${i}].description`).trim();
    const quantity = Number(it.quantity);
    const unitPrice = Number(it.unit_price);
    if (!description) throw new HttpError(400, `items[${i}].description is required.`);
    if (!Number.isFinite(quantity) || quantity <= 0) throw new HttpError(400, `items[${i}].quantity must be a positive number.`);
    if (!Number.isFinite(unitPrice) || unitPrice < 0) throw new HttpError(400, `items[${i}].unit_price must be a non-negative number.`);
    return { description, quantity, unit_price: unitPrice };
  });
}

function cleanDueDate(value) {
  if (value === undefined || value === null || value === '') return null;
  const ms = Date.parse(value);
  if (!Number.isFinite(ms)) throw new HttpError(400, 'due_date must be a valid date.');
  return new Date(ms).toISOString();
}

function cleanTaxRate(value) {
  if (value === undefined) return 0;
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0 || n > 100) throw new HttpError(400, 'tax_rate_percent must be between 0 and 100.');
  return n;
}

function requireInvoice(tenantId, id) {
  const invoice = store.getInvoice(tenantId, id);
  if (!invoice) throw new HttpError(404, 'Invoice not found.');
  return invoice;
}

// draft -> sent -> paid; void reachable from draft or sent; nothing leaves paid or void.
const TRANSITIONS = {
  draft: ['sent', 'void'],
  sent: ['paid', 'void'],
  paid: [],
  void: [],
};

// ---------------------------------------------------------------- routes

const routes = [];
function route(method, pattern, handler, { auth = true } = {}) {
  routes.push({ method, regex: new RegExp(`^${pattern}$`), handler, auth });
}

route('GET', '/api/health', async ({ res }) => sendJson(res, 200, { ok: true, name: 'Concierge Payments', version: VERSION }), {
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

// ---------------------------------------------------------------- invoices

route('GET', '/api/invoices', async ({ tenantId, url, res }) => {
  const status = url.searchParams.get('status');
  let invoices = store.listInvoices(tenantId);
  if (status) invoices = invoices.filter((i) => i.status === status);
  sendJson(res, 200, { invoices });
});

route('POST', '/api/invoices', async ({ tenantId, req, res }) => {
  const body = await readJson(req);
  const contactName = text(body.contact_name || '', 200, 'contact_name').trim();
  if (!contactName) throw new HttpError(400, 'contact_name is required.');
  const items = cleanItems(body.items || []);
  if (items.length === 0) throw new HttpError(400, 'At least one line item is required.');
  const invoice = store.insertInvoice(
    tenantId,
    {
      contact_name: contactName,
      contact_email: text(body.contact_email || '', 200, 'contact_email').trim(),
      due_date: cleanDueDate(body.due_date),
      tax_rate_percent: cleanTaxRate(body.tax_rate_percent),
      notes: text(body.notes || '', 2000, 'notes'),
    },
    items,
  );
  sendJson(res, 201, { invoice });
});

route('GET', '/api/invoices/(\\d+)', async ({ tenantId, params, res }) =>
  sendJson(res, 200, { invoice: requireInvoice(tenantId, Number(params[0])) }),
);

route('PUT', '/api/invoices/(\\d+)', async ({ tenantId, req, params, res }) => {
  const existing = requireInvoice(tenantId, Number(params[0]));
  if (existing.status !== 'draft') {
    throw new HttpError(409, 'Only a draft invoice can be edited. Void it and start a new one instead.');
  }
  const body = await readJson(req);
  const items = 'items' in body ? cleanItems(body.items) : existing.items.map(({ description, quantity, unit_price }) => ({ description, quantity, unit_price }));
  const invoice = store.saveInvoice(
    tenantId,
    existing.id,
    {
      contact_name: 'contact_name' in body ? text(body.contact_name, 200, 'contact_name').trim() || existing.contact_name : existing.contact_name,
      contact_email: 'contact_email' in body ? text(body.contact_email, 200, 'contact_email').trim() : existing.contact_email,
      due_date: 'due_date' in body ? cleanDueDate(body.due_date) : existing.due_date,
      tax_rate_percent: 'tax_rate_percent' in body ? cleanTaxRate(body.tax_rate_percent) : existing.tax_rate_percent,
      notes: 'notes' in body ? text(body.notes, 2000, 'notes') : existing.notes,
    },
    items,
  );
  sendJson(res, 200, { invoice });
});

route('POST', '/api/invoices/(\\d+)/status', async ({ tenantId, req, params, res }) => {
  const existing = requireInvoice(tenantId, Number(params[0]));
  const body = await readJson(req);
  const status = text(body.status, 20, 'status');
  const allowed = TRANSITIONS[existing.status] || [];
  if (!allowed.includes(status)) {
    throw new HttpError(422, `Cannot move an invoice from "${existing.status}" to "${status}".`, {
      allowed_from_here: allowed,
    });
  }
  sendJson(res, 200, { invoice: store.setInvoiceStatus(tenantId, existing.id, status) });
});

route('DELETE', '/api/invoices/(\\d+)', async ({ tenantId, params, res }) => {
  const existing = requireInvoice(tenantId, Number(params[0]));
  if (existing.status !== 'draft') {
    throw new HttpError(409, 'Only a draft invoice can be deleted. Void it instead to keep the record.');
  }
  store.deleteInvoice(tenantId, existing.id);
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
  console.log(`Concierge Payments ${VERSION} listening on http://${HOST}:${PORT}`);
  console.log(`Data folder: ${DATA_DIR}`);
  console.log('Create a new customer with: POST /api/tenants { "name": "..." }');
  console.log('NOTE: no real payment processing -- "paid" is a manual status only.');
});

export { server };
