// Concierge Sites server: simple published pages and the leads their forms
// capture. JSON API + a public page renderer, zero npm dependencies.
// Requires Node 22.5+ (built-in node:sqlite).
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
const PORT = Number(process.env.PORT || 4404);
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

const db = openDb(path.join(DATA_DIR, 'sites.db'));
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

function sendHtml(res, status, html) {
  res.writeHead(status, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(html);
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

async function readForm(req) {
  const raw = await readBody(req, MAX_JSON_BYTES);
  const params = new URLSearchParams(raw.toString('utf8'));
  return Object.fromEntries(params.entries());
}

function text(value, max, field) {
  if (value === undefined || value === null) return '';
  if (typeof value !== 'string') throw new HttpError(400, `${field} must be text.`);
  if (value.length > max) throw new HttpError(400, `${field} is too long (max ${max}).`);
  return value;
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

// ---------------------------------------------------------------- blocks

const BLOCK_TYPES = ['heading', 'paragraph', 'image', 'button', 'form'];
const FORM_FIELDS = ['name', 'email', 'phone'];

function cleanBlock(b, i) {
  if (!BLOCK_TYPES.includes(b.type)) throw new HttpError(400, `blocks[${i}].type must be one of: ${BLOCK_TYPES.join(', ')}.`);
  const c = b.content || {};
  switch (b.type) {
    case 'heading':
      return { type: 'heading', content: { text: text(c.text, 200, `blocks[${i}].content.text`), level: [1, 2, 3].includes(Number(c.level)) ? Number(c.level) : 1 } };
    case 'paragraph':
      return { type: 'paragraph', content: { text: text(c.text, 2000, `blocks[${i}].content.text`) } };
    case 'image':
      return { type: 'image', content: { url: text(c.url, 1000, `blocks[${i}].content.url`), alt: text(c.alt, 200, `blocks[${i}].content.alt`) } };
    case 'button':
      return { type: 'button', content: { text: text(c.text, 100, `blocks[${i}].content.text`), link: text(c.link, 1000, `blocks[${i}].content.link`) } };
    case 'form': {
      const fields = Array.isArray(c.fields) ? c.fields.filter((f) => FORM_FIELDS.includes(f)) : ['name', 'email'];
      return {
        type: 'form',
        content: { fields: fields.length ? fields : ['name', 'email'], submit_label: text(c.submit_label, 60, `blocks[${i}].content.submit_label`) || 'Submit' },
      };
    }
    default:
      throw new HttpError(400, 'Unreachable.');
  }
}

function requirePage(tenantId, id) {
  const page = store.getPage(tenantId, id);
  if (!page) throw new HttpError(404, 'Page not found.');
  return page;
}

function pageWithBlocks(tenantId, page) {
  return { ...page, blocks: store.listBlocks(tenantId, page.id) };
}

// ---------------------------------------------------------------- public render

function renderBlock(tenantId, slug, b) {
  switch (b.type) {
    case 'heading':
      return `<h${b.content.level}>${escapeHtml(b.content.text)}</h${b.content.level}>`;
    case 'paragraph':
      return `<p>${escapeHtml(b.content.text)}</p>`;
    case 'image':
      return `<img src="${escapeHtml(b.content.url)}" alt="${escapeHtml(b.content.alt)}" style="max-width:100%">`;
    case 'button':
      return `<p><a class="btn" href="${escapeHtml(b.content.link)}">${escapeHtml(b.content.text)}</a></p>`;
    case 'form': {
      const inputs = b.content.fields
        .map((f) => `<input name="${f}" placeholder="${escapeHtml(f[0].toUpperCase() + f.slice(1))}" ${f === 'email' ? 'type="email"' : 'type="text"'}>`)
        .join('');
      return `<form method="POST" action="/site/${escapeHtml(tenantId)}/${escapeHtml(slug)}/submit">${inputs}<button type="submit">${escapeHtml(b.content.submit_label)}</button></form>`;
    }
    default:
      return '';
  }
}

function renderPage(tenantId, page, blocks) {
  const body = blocks.map((b) => renderBlock(tenantId, page.slug, b)).join('\n');
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(page.title || page.slug)}</title>
<style>body{font-family:-apple-system,sans-serif;max-width:720px;margin:40px auto;padding:0 16px;line-height:1.5}
form{display:flex;flex-direction:column;gap:8px;max-width:360px}
input,button,.btn{padding:10px 14px;border-radius:6px;border:1px solid #ccc;font:inherit;text-decoration:none;display:inline-block;color:inherit}
button,.btn{background:#2563eb;color:#fff;border-color:#2563eb;cursor:pointer;text-align:center}</style>
</head><body>
${body}
</body></html>`;
}

// ---------------------------------------------------------------- routes

const routes = [];
function route(method, pattern, handler, { auth = true } = {}) {
  routes.push({ method, regex: new RegExp(`^${pattern}$`), handler, auth });
}

route('GET', '/api/health', async ({ res }) => sendJson(res, 200, { ok: true, name: 'Concierge Sites', version: VERSION }), {
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

// ---------------------------------------------------------------- pages

route('GET', '/api/pages', async ({ tenantId, res }) => sendJson(res, 200, { pages: store.listPages(tenantId) }));

route('POST', '/api/pages', async ({ tenantId, req, res }) => {
  const body = await readJson(req);
  const slug = text(body.slug || '', 60, 'slug').trim().toLowerCase();
  if (!/^[a-z0-9-]+$/.test(slug)) throw new HttpError(400, 'slug must be lowercase letters, numbers and hyphens only.');
  if (store.getPageBySlug(tenantId, slug)) throw new HttpError(409, `A page with slug "${slug}" already exists.`);
  const page = store.insertPage(tenantId, { slug, title: text(body.title || '', 200, 'title').trim() || slug });
  sendJson(res, 201, { page: pageWithBlocks(tenantId, page) });
});

route('GET', '/api/pages/(\\d+)', async ({ tenantId, params, res }) =>
  sendJson(res, 200, { page: pageWithBlocks(tenantId, requirePage(tenantId, Number(params[0]))) }),
);

route('PUT', '/api/pages/(\\d+)', async ({ tenantId, req, params, res }) => {
  const existing = requirePage(tenantId, Number(params[0]));
  const body = await readJson(req);
  if ('title' in body) store.savePageMeta(tenantId, existing.id, { title: text(body.title, 200, 'title').trim() || existing.title });
  if ('blocks' in body) {
    if (!Array.isArray(body.blocks)) throw new HttpError(400, 'blocks must be a list.');
    store.replaceBlocks(tenantId, existing.id, body.blocks.map(cleanBlock));
  }
  sendJson(res, 200, { page: pageWithBlocks(tenantId, store.getPage(tenantId, existing.id)) });
});

route('POST', '/api/pages/(\\d+)/status', async ({ tenantId, req, params, res }) => {
  const existing = requirePage(tenantId, Number(params[0]));
  const body = await readJson(req);
  const status = text(body.status, 20, 'status');
  if (!['draft', 'published'].includes(status)) throw new HttpError(400, 'status must be draft or published.');
  sendJson(res, 200, { page: store.setPageStatus(tenantId, existing.id, status) });
});

route('DELETE', '/api/pages/(\\d+)', async ({ tenantId, params, res }) => {
  if (!store.deletePage(tenantId, Number(params[0]))) throw new HttpError(404, 'Page not found.');
  sendJson(res, 200, { ok: true });
});

// ---------------------------------------------------------------- leads

route('GET', '/api/leads', async ({ tenantId, url, res }) => {
  const pageId = url.searchParams.get('page_id');
  const leads = pageId ? store.listLeadsForPage(tenantId, Number(pageId)) : store.listLeads(tenantId);
  sendJson(res, 200, { leads });
});

// ---------------------------------------------------------------- static files (dashboard)

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

    // Public page render: /site/<tenantId>/<slug>
    const siteMatch = /^\/site\/([a-z0-9-]+)\/([a-z0-9-]+)$/.exec(pathname);
    if (siteMatch && req.method === 'GET') {
      const [, tenantId, slug] = siteMatch;
      const page = store.getPageBySlug(tenantId, slug);
      if (!page || page.status !== 'published') throw new HttpError(404, 'Page not found.');
      sendHtml(res, 200, renderPage(tenantId, page, store.listBlocks(tenantId, page.id)));
      return;
    }

    // Public lead-capture submit: /site/<tenantId>/<slug>/submit
    const submitMatch = /^\/site\/([a-z0-9-]+)\/([a-z0-9-]+)\/submit$/.exec(pathname);
    if (submitMatch && req.method === 'POST') {
      const [, tenantId, slug] = submitMatch;
      const page = store.getPageBySlug(tenantId, slug);
      if (!page || page.status !== 'published') throw new HttpError(404, 'Page not found.');
      const data = await readForm(req);
      store.insertLead(tenantId, page.id, data);
      sendHtml(res, 200, '<!doctype html><html><body><p>Thanks -- we got it.</p></body></html>');
      return;
    }

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
  console.log(`Concierge Sites ${VERSION} listening on http://${HOST}:${PORT}`);
  console.log(`Data folder: ${DATA_DIR}`);
  console.log('Create a new customer with: POST /api/tenants { "name": "..." }');
});

export { server };
