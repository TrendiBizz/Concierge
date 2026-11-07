// SocialSync server: JSON API, media storage and the web dashboard.
// Zero npm dependencies. Requires Node 22.5+ (built-in node:sqlite).
//
// Multi-tenant: one SocialSync serves every Concierge customer, standalone --
// no GHL dependency of any kind. A tenant is a row in `tenants` with its own
// id and passcode; POST /api/tenants creates one. Every tenant, including
// Pukeko Construction (tenant 'pukeko', the original single-tenant build),
// signs in the same way: enter the passcode at the same login screen.

import http from 'node:http';
import { createHmac, randomBytes, timingSafeEqual } from 'node:crypto';
import {
  createReadStream,
  existsSync,
  mkdirSync,
  readFileSync,
  statSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs';
import { writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { makeStore, openDb } from './db.js';
import { PLATFORM_IDS, RulesStore, checkPost } from './guardrails.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const DATA_DIR = path.resolve(process.env.DATA_DIR || path.join(ROOT, 'data'));
const MEDIA_DIR = path.join(DATA_DIR, 'media');
const WEB_DIR = path.join(ROOT, 'web');
const PORT = Number(process.env.PORT || 4377);
const HOST = process.env.HOST || '127.0.0.1';
const MAX_JSON_BYTES = 1024 * 1024;
const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
const VERSION = '2.0.0';
const PUKEKO_TENANT = 'pukeko';
const DUE_CHECK_MS = 60_000;

mkdirSync(MEDIA_DIR, { recursive: true });

// ---------------------------------------------------------------- config / auth

const PASSCODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';

function generatePasscode() {
  const bytes = randomBytes(8);
  return Array.from(bytes, (b) => PASSCODE_ALPHABET[b % PASSCODE_ALPHABET.length]).join('');
}

// Only the HMAC secret lives here now; each tenant's passcode lives in the
// `tenants` table instead of one shared config file.
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

// One signed session token per tenant, carrying its own tenant id:
// "<tenantId>.<hmac>". Anyone holding it can act as that tenant -- the token
// itself is the credential. tenantId is always a plain slug (see
// `slugify` below), so splitting on the first '.' is unambiguous.
function tenantToken(tenantId) {
  const mac = createHmac('sha256', config.secret).update(`socialsync-tenant:${tenantId}`).digest('hex');
  return `${tenantId}.${mac}`;
}

function readCookie(req, name) {
  const header = req.headers.cookie || '';
  for (const part of header.split(';')) {
    const [key, ...rest] = part.trim().split('=');
    if (key === name) return decodeURIComponent(rest.join('='));
  }
  return '';
}

// Resolves which tenant (if any) this request is authenticated as.
function authedTenant(req, url) {
  const bearer = /^Bearer\s+(.+)$/i.exec(req.headers.authorization || '');
  const token = (bearer && bearer[1]) || readCookie(req, 'ss_token') || url.searchParams.get('token') || '';
  const dot = token.indexOf('.');
  if (dot <= 0) return null;
  const tenantId = token.slice(0, dot);
  if (!safeEqual(token, tenantToken(tenantId))) return null;
  return tenantId;
}

// Plain HttpOnly cookie, for a normal browser tab logged in directly at this
// server. The web app also keeps the token in memory and sends it as a
// Bearer header, which is what it actually relies on (see web/app.js).
function tenantCookies(tenantId) {
  return { 'Set-Cookie': `ss_token=${tenantToken(tenantId)}; HttpOnly; SameSite=Lax; Path=/; Max-Age=31536000` };
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

const db = openDb(path.join(DATA_DIR, 'socialsync.db'));
const store = makeStore(db);

// Base rules: platform mechanics (character limits, media requirements) are
// shared by every tenant -- they come from the platform, not the business.
// `facts` / `forbidden_phrases` / `warnings` in this file are Pukeko's own
// seed only, migrated once below; every other tenant starts with none.
const baseRulesStore = new RulesStore(path.join(__dirname, 'rules.json'), process.env.TRUTH_JSON || '');

// Pukeko predates the tenants table (and predates tenants having a passcode
// column at all); give it both, with its historical passcode
// (SOCIALSYNC_PASSCODE, or a fresh one the first time this runs).
{
  const existing = store.getTenant(PUKEKO_TENANT);
  if (!existing) {
    const passcode = process.env.SOCIALSYNC_PASSCODE || generatePasscode();
    store.insertTenant(PUKEKO_TENANT, 'Pukeko Construction', passcode);
    if (!process.env.SOCIALSYNC_PASSCODE) {
      console.log(`First run: Pukeko's passcode is ${passcode} (change it with SOCIALSYNC_PASSCODE).`);
    }
  } else if (process.env.SOCIALSYNC_PASSCODE) {
    store.setTenantPasscode(PUKEKO_TENANT, process.env.SOCIALSYNC_PASSCODE);
  } else if (!existing.passcode) {
    const passcode = generatePasscode();
    store.setTenantPasscode(PUKEKO_TENANT, passcode);
    console.log(`Pukeko had no passcode on file; generated one: ${passcode} (change it with SOCIALSYNC_PASSCODE).`);
  }
}
store.seedOnce('tenant_rules_pukeko_v1', () => {
  const base = baseRulesStore.get();
  store.saveTenantRules(PUKEKO_TENANT, {
    facts: base.facts || [],
    forbidden_phrases: base.forbidden_phrases || [],
    warnings: base.warnings || [],
  });
});

function rulesFor(tenantId) {
  const base = baseRulesStore.get();
  const tenant = store.getTenantRules(tenantId);
  return {
    platforms: base.platforms || {},
    facts: tenant.facts,
    forbidden_phrases: tenant.forbidden_phrases,
    warnings: tenant.warnings,
  };
}

// ---------------------------------------------------------------- helpers

class HttpError extends Error {
  constructor(status, message, extra = {}) {
    super(message);
    this.status = status;
    this.extra = extra;
  }
}

function sendJson(res, status, body, headers = {}) {
  const payload = JSON.stringify(body);
  const out = {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(payload),
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    ...headers,
  };
  res.writeHead(status, out);
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
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
      throw new Error('not an object');
    }
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

function cleanPlatforms(value) {
  if (!Array.isArray(value)) throw new HttpError(400, 'platforms must be a list.');
  const out = [];
  for (const id of value) {
    if (!PLATFORM_IDS.includes(id)) throw new HttpError(400, `Unknown platform "${id}".`);
    if (!out.includes(id)) out.push(id);
  }
  return out;
}

function cleanMediaIds(tenantId, value) {
  if (!Array.isArray(value)) throw new HttpError(400, 'media_ids must be a list.');
  if (value.length > 10) throw new HttpError(400, 'At most 10 media items per post.');
  const out = [];
  for (const raw of value) {
    const id = Number(raw);
    if (!Number.isInteger(id) || id <= 0 || !store.getMedia(tenantId, id)) {
      throw new HttpError(400, `Media item ${raw} does not exist.`);
    }
    if (!out.includes(id)) out.push(id);
  }
  return out;
}

// Applies the editable fields from `input` on top of `base`.
function applyPostInput(tenantId, base, input) {
  const post = { ...base };
  if ('content' in input) post.content = text(input.content, 10000, 'content');
  if ('link' in input) post.link = text(input.link, 2048, 'link');
  if ('hashtags' in input) post.hashtags = text(input.hashtags, 1000, 'hashtags');
  if ('platforms' in input) post.platforms = cleanPlatforms(input.platforms);
  if ('media_ids' in input) post.media_ids = cleanMediaIds(tenantId, input.media_ids);
  return post;
}

function checkOf(tenantId, post) {
  return checkPost(post, rulesFor(tenantId));
}

// Everything that must be true before a post may sit in the schedule.
function scheduleProblems(post, check) {
  const problems = [];
  if (post.platforms.length === 0) problems.push('Choose at least one platform.');
  if (!post.content.trim()) problems.push('Write some text for the post.');
  for (const err of check.errors) problems.push(err.message);
  return problems;
}

function parseFutureDate(value) {
  const ms = typeof value === 'string' ? Date.parse(value) : NaN;
  if (!Number.isFinite(ms)) throw new HttpError(400, 'scheduled_at must be a valid date and time.');
  if (ms <= Date.now()) throw new HttpError(400, 'Pick a time in the future.');
  return new Date(ms).toISOString();
}

function requirePost(tenantId, id) {
  const post = store.getPost(tenantId, id);
  if (!post) throw new HttpError(404, 'Post not found.');
  return post;
}

function requireEditable(post) {
  if (post.status === 'posted') {
    throw new HttpError(409, 'This post is already marked as posted. Duplicate it to reuse it.');
  }
}

function postResponse(tenantId, post) {
  return { post, check: checkOf(tenantId, post) };
}

const MEDIA_TYPES = {
  'image/jpeg': 'jpg',
  'image/png': 'png',
  'image/gif': 'gif',
  'image/webp': 'webp',
  'image/heic': 'heic',
  'video/mp4': 'mp4',
  'video/quicktime': 'mov',
};

// ---------------------------------------------------------------- routes

const routes = [];
function route(method, pattern, handler, { auth = true } = {}) {
  routes.push({ method, regex: new RegExp(`^${pattern}$`), handler, auth });
}

route(
  'GET',
  '/api/health',
  async ({ res }) => sendJson(res, 200, { ok: true, name: 'SocialSync', version: VERSION }),
  { auth: false },
);

function slugify(name) {
  return (
    String(name || '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 40) || 'customer'
  );
}

// Creates a new Concierge customer: a fresh tenant with its own passcode.
// Standalone -- no GHL, no third party. The passcode is returned once, in
// the response body; store.insertTenant never exposes it again after this.
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
    sendJson(res, 200, { tenant, token: tenantToken(tenant.id) }, tenantCookies(tenant.id));
  },
  { auth: false },
);

route('POST', '/api/logout', async ({ res }) =>
  sendJson(res, 200, { ok: true }, { 'Set-Cookie': 'ss_token=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0' }),
);

route('GET', '/api/rules', async ({ tenantId, res }) => {
  const rules = rulesFor(tenantId);
  sendJson(res, 200, { platforms: rules.platforms, platform_order: PLATFORM_IDS });
});

route('POST', '/api/check', async ({ tenantId, req, res }) => {
  const input = await readJson(req);
  const post = applyPostInput(
    tenantId,
    { content: '', link: '', hashtags: '', platforms: [], media_ids: [] },
    input,
  );
  sendJson(res, 200, { check: checkOf(tenantId, post) });
});

route('GET', '/api/posts', async ({ tenantId, url, res }) => {
  const status = url.searchParams.get('status');
  let posts = store.listPosts(tenantId);
  if (status) posts = posts.filter((p) => p.status === status);
  sendJson(res, 200, { posts });
});

route('POST', '/api/posts', async ({ tenantId, req, res }) => {
  const input = await readJson(req);
  const post = applyPostInput(
    tenantId,
    { content: '', link: '', hashtags: '', platforms: [], media_ids: [] },
    input,
  );
  const saved = store.insertPost(tenantId, { ...post, status: 'draft' });
  sendJson(res, 201, postResponse(tenantId, saved));
});

route('GET', '/api/posts/(\\d+)', async ({ tenantId, params, res }) => {
  sendJson(res, 200, postResponse(tenantId, requirePost(tenantId, Number(params[0]))));
});

route('PUT', '/api/posts/(\\d+)', async ({ tenantId, req, params, res }) => {
  const existing = requirePost(tenantId, Number(params[0]));
  requireEditable(existing);
  const next = applyPostInput(tenantId, existing, await readJson(req));
  if (existing.status === 'scheduled') {
    const check = checkOf(tenantId, next);
    const problems = scheduleProblems(next, check);
    if (problems.length) {
      throw new HttpError(422, 'A scheduled post must stay valid. Fix it or unschedule first.', {
        problems,
        check,
      });
    }
  }
  sendJson(res, 200, postResponse(tenantId, store.savePost(tenantId, next)));
});

route('DELETE', '/api/posts/(\\d+)', async ({ tenantId, params, res }) => {
  requirePost(tenantId, Number(params[0]));
  store.deletePost(tenantId, Number(params[0]));
  sendJson(res, 200, { ok: true });
});

route('POST', '/api/posts/(\\d+)/schedule', async ({ tenantId, req, params, res }) => {
  const post = requirePost(tenantId, Number(params[0]));
  requireEditable(post);
  const body = await readJson(req);
  const scheduledAt = parseFutureDate(body.scheduled_at);
  const check = checkOf(tenantId, post);
  const problems = scheduleProblems(post, check);
  if (problems.length) {
    throw new HttpError(422, 'This post cannot be scheduled yet.', { problems, check });
  }
  const saved = store.savePost(tenantId, { ...post, status: 'scheduled', scheduled_at: scheduledAt });
  sendJson(res, 200, postResponse(tenantId, saved));
});

route('POST', '/api/posts/(\\d+)/unschedule', async ({ tenantId, params, res }) => {
  const post = requirePost(tenantId, Number(params[0]));
  requireEditable(post);
  const saved = store.savePost(tenantId, { ...post, status: 'draft', scheduled_at: null });
  sendJson(res, 200, postResponse(tenantId, saved));
});

route('POST', '/api/posts/(\\d+)/mark-posted', async ({ tenantId, params, res }) => {
  const post = requirePost(tenantId, Number(params[0]));
  requireEditable(post);
  const saved = store.savePost(tenantId, { ...post, status: 'posted', posted_at: new Date().toISOString() });
  sendJson(res, 200, postResponse(tenantId, saved));
});

route('POST', '/api/posts/(\\d+)/duplicate', async ({ tenantId, params, res }) => {
  const post = requirePost(tenantId, Number(params[0]));
  const copy = store.insertPost(tenantId, {
    content: post.content,
    link: post.link,
    hashtags: post.hashtags,
    platforms: post.platforms,
    media_ids: post.media_ids.filter((id) => store.getMedia(tenantId, id)),
    status: 'draft',
  });
  sendJson(res, 201, postResponse(tenantId, copy));
});

route('GET', '/api/media', async ({ tenantId, res }) => sendJson(res, 200, { media: store.listMedia(tenantId) }));

route('POST', '/api/media', async ({ tenantId, req, url, res }) => {
  const mime = String(req.headers['content-type'] || '').split(';')[0].trim().toLowerCase();
  const ext = MEDIA_TYPES[mime];
  if (!ext) {
    throw new HttpError(415, 'Only JPEG, PNG, GIF, WebP, HEIC, MP4 and MOV files are supported.');
  }
  const body = await readBody(req, MAX_UPLOAD_BYTES);
  if (body.length === 0) throw new HttpError(400, 'The file is empty.');
  const filename = text(url.searchParams.get('filename') || `upload.${ext}`, 200, 'filename')
    .replace(/[\\/\0]/g, '_');
  const id = store.insertMedia(tenantId, {
    filename,
    mime,
    size: body.length,
    caption: text(url.searchParams.get('caption') || '', 500, 'caption'),
    project: text(url.searchParams.get('project') || '', 200, 'project'),
  });
  const file = path.join(MEDIA_DIR, `${tenantId.replace(/[^a-zA-Z0-9_-]/g, '_')}-${id}.${ext}`);
  await writeFile(file, body);
  store.setMediaPath(tenantId, id, file);
  sendJson(res, 201, { media: store.getMedia(tenantId, id) });
});

route('PATCH', '/api/media/(\\d+)', async ({ tenantId, req, params, res }) => {
  const id = Number(params[0]);
  const existing = store.getMedia(tenantId, id);
  if (!existing) throw new HttpError(404, 'Photo not found.');
  const body = await readJson(req);
  const caption = 'caption' in body ? text(body.caption, 500, 'caption') : existing.caption;
  const project = 'project' in body ? text(body.project, 200, 'project') : existing.project;
  sendJson(res, 200, { media: store.saveMedia(tenantId, id, { caption, project }) });
});

route('DELETE', '/api/media/(\\d+)', async ({ tenantId, params, res }) => {
  const id = Number(params[0]);
  if (!store.getMedia(tenantId, id)) throw new HttpError(404, 'Photo not found.');
  const using = store.postsUsingMedia(tenantId, id);
  if (using.length) {
    throw new HttpError(409, `This photo is used by ${using.length} unposted post(s). Remove it from them first.`, {
      post_ids: using.map((p) => p.id),
    });
  }
  const file = store.getMediaPath(tenantId, id);
  store.deleteMedia(tenantId, id);
  if (file && existsSync(file)) unlinkSync(file);
  sendJson(res, 200, { ok: true });
});

// ---------------------------------------------------------------- social pages

// Pages and accounts a tenant uses. These are links the team can open from
// one place; the four platforms in PLATFORM_IDS are also the ones a post can
// be written for.
const CHANNEL_PLATFORMS = [
  'facebook',
  'instagram',
  'linkedin',
  'twitter',
  'youtube',
  'tiktok',
  'google',
  'website',
  'other',
];

// Found on https://pukekoconstruction.co.nz/ (footer links). Seeded once for
// the Pukeko tenant only, then editable. New tenants start with none.
const PUKEKO_DEFAULT_CHANNELS = [
  {
    platform: 'facebook',
    name: 'Pukeko Construction',
    url: 'https://www.facebook.com/pukekoconstruction',
    notes: 'Linked from the website. Check this is the right page.',
  },
  {
    platform: 'instagram',
    name: 'pukekoconstruction',
    url: 'https://www.instagram.com/pukekoconstruction/',
    notes: 'Linked from the website.',
  },
  {
    platform: 'website',
    name: 'pukekoconstruction.co.nz',
    url: 'https://pukekoconstruction.co.nz/',
    notes: '',
  },
];

store.seedOnce('default_channels_v1', () => {
  for (const channel of PUKEKO_DEFAULT_CHANNELS) store.insertChannel(PUKEKO_TENANT, channel);
});

function cleanChannel(base, input) {
  const channel = { ...base };
  if ('platform' in input) {
    if (!CHANNEL_PLATFORMS.includes(input.platform)) {
      throw new HttpError(400, `Platform must be one of: ${CHANNEL_PLATFORMS.join(', ')}.`);
    }
    channel.platform = input.platform;
  }
  if ('name' in input) channel.name = text(input.name, 100, 'name').trim();
  if ('url' in input) channel.url = text(input.url, 2048, 'url').trim();
  if ('notes' in input) channel.notes = text(input.notes, 500, 'notes');
  if (!channel.platform) throw new HttpError(400, 'Choose a platform.');
  if (!channel.name) throw new HttpError(400, 'Give the page a name.');
  let parsed;
  try {
    parsed = new URL(channel.url);
  } catch {
    throw new HttpError(400, 'The page address must be a full link, like https://www.facebook.com/yourpage');
  }
  if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
    throw new HttpError(400, 'The page address must start with https://');
  }
  channel.url = parsed.toString();
  return channel;
}

route('GET', '/api/channels', async ({ tenantId, res }) =>
  sendJson(res, 200, { channels: store.listChannels(tenantId), platforms: CHANNEL_PLATFORMS }),
);

route('POST', '/api/channels', async ({ tenantId, req, res }) => {
  const channel = cleanChannel({ platform: '', name: '', url: '', notes: '' }, await readJson(req));
  sendJson(res, 201, { channel: store.insertChannel(tenantId, channel) });
});

route('PUT', '/api/channels/(\\d+)', async ({ tenantId, req, params, res }) => {
  const existing = store.getChannel(tenantId, Number(params[0]));
  if (!existing) throw new HttpError(404, 'Page not found.');
  const channel = cleanChannel(existing, await readJson(req));
  sendJson(res, 200, { channel: store.saveChannel(tenantId, channel) });
});

route('DELETE', '/api/channels/(\\d+)', async ({ tenantId, params, res }) => {
  if (!store.deleteChannel(tenantId, Number(params[0]))) throw new HttpError(404, 'Page not found.');
  sendJson(res, 200, { ok: true });
});

// ---------------------------------------------------------------- files

function serveFile(req, res, file, mime, { cache = 'private, max-age=3600' } = {}) {
  const size = statSync(file).size;
  const headers = {
    'Content-Type': mime,
    'Accept-Ranges': 'bytes',
    'Cache-Control': cache,
    'X-Content-Type-Options': 'nosniff',
  };
  const range = req.headers.range;
  if (range) {
    const match = /^bytes=(\d*)-(\d*)$/.exec(range);
    let start = 0;
    let end = size - 1;
    if (match && (match[1] !== '' || match[2] !== '')) {
      if (match[1] === '') {
        start = Math.max(0, size - Number(match[2]));
      } else {
        start = Number(match[1]);
        if (match[2] !== '') end = Math.min(Number(match[2]), size - 1);
      }
    }
    if (!match || start >= size || end < start) {
      res.writeHead(416, { 'Content-Range': `bytes */${size}` });
      res.end();
      return;
    }
    res.writeHead(206, {
      ...headers,
      'Content-Range': `bytes ${start}-${end}/${size}`,
      'Content-Length': end - start + 1,
    });
    createReadStream(file, { start, end }).pipe(res);
    return;
  }
  res.writeHead(200, { ...headers, 'Content-Length': size });
  createReadStream(file).pipe(res);
}

const STATIC_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
};

function serveStatic(req, res, pathname) {
  let rel;
  try {
    rel = decodeURIComponent(pathname);
  } catch {
    throw new HttpError(400, 'Bad path.');
  }
  if (rel === '/' || rel === '' || rel === '/app') rel = '/index.html';
  const file = path.normalize(path.join(WEB_DIR, rel));
  if (!file.startsWith(WEB_DIR + path.sep) || !existsSync(file) || !statSync(file).isFile()) {
    throw new HttpError(404, 'Not found.');
  }
  const mime = STATIC_TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream';
  serveFile(req, res, file, mime, { cache: 'no-cache' });
}

// ---------------------------------------------------------------- server

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://localhost');
    const pathname = url.pathname;

    const mediaMatch = /^\/media\/(\d+)$/.exec(pathname);
    if (mediaMatch && (req.method === 'GET' || req.method === 'HEAD')) {
      const tenantId = authedTenant(req, url);
      if (!tenantId) throw new HttpError(401, 'Sign in required.');
      const id = Number(mediaMatch[1]);
      const meta = store.getMedia(tenantId, id);
      const file = store.getMediaPath(tenantId, id);
      if (!meta || !file || !existsSync(file)) throw new HttpError(404, 'Not found.');
      serveFile(req, res, file, meta.mime);
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

// Automation layer (no OAuth, no direct publishing -- see README "Next
// steps"). Every minute, flag posts that just became due across every
// tenant. This is logged server-side for now; the dashboard already surfaces
// "Due now" with a one-click copy-and-open per platform while it's open
// (web/app.js). Turning this into a push notification that reaches a closed
// browser is the next increment, not built yet.
const notifiedDue = new Set();
setInterval(() => {
  for (const post of store.duePostsAcrossTenants()) {
    const key = `${post.tenant_id}:${post.id}`;
    if (notifiedDue.has(key)) continue;
    notifiedDue.add(key);
    console.log(`[due] tenant ${post.tenant_id}: post ${post.id} is due now (${post.platforms.join(', ')})`);
  }
}, DUE_CHECK_MS);

server.listen(PORT, HOST, () => {
  console.log(`SocialSync ${VERSION} listening on http://${HOST}:${PORT}`);
  console.log(`Data folder: ${DATA_DIR}`);
  console.log(`Tenants: ${store.listTenants().map((t) => t.id).join(', ')}`);
  console.log('Create a new customer with: POST /api/tenants { "name": "..." }');
  if (HOST === '127.0.0.1') {
    console.log('Only this computer can connect. Set HOST=0.0.0.0 to allow phones on your network.');
  }
});

export { server };
