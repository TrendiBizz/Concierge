// Concierge lead bridge: POST /lead from the website (or any module) creates a
// person in the Twenty CRM. Zero npm dependencies. Node 22.5+.
//
// Config (environment):
//   PORT              default 4410
//   HOST              default 127.0.0.1 (use 0.0.0.0 so a VM's browser can reach it)
//   TWENTY_URL        default http://127.0.0.1:3010
//   TWENTY_API_KEY    Twenty API key; or put it in the file named by TWENTY_API_KEY_FILE
//   TWENTY_API_KEY_FILE  default ./.twenty-key (gitignored)
//   ALLOWED_ORIGINS   comma list, default * (any website may post a lead; rate limited)

import http from 'node:http';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MAX_BODY = 16 * 1024;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function clean(v, max) {
  return typeof v === 'string' ? v.trim().slice(0, max) : '';
}

export function normalizePhone(raw) {
  const s = clean(raw, 40);
  if (!s) return '';
  const digits = s.replace(/[^\d+]/g, '');
  if (digits.startsWith('+')) return /^\+\d{7,15}$/.test(digits) ? digits : '';
  if (digits.startsWith('00')) return /^00\d{7,15}$/.test(digits) ? '+' + digits.slice(2) : '';
  // Local number with a leading 0: assume New Zealand (+64) like the rest of Concierge.
  if (/^0\d{7,10}$/.test(digits)) return '+64' + digits.slice(1);
  return '';
}

export function validateLead(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return { error: 'invalid_json' };
  const lead = {
    first_name: clean(body.first_name, 80),
    last_name: clean(body.last_name, 80),
    email: clean(body.email, 200).toLowerCase(),
    phone: normalizePhone(body.phone),
    company: clean(body.company, 120),
    message: clean(body.message, 2000),
    plan: clean(body.plan, 40),
    source: clean(body.source, 60) || 'website',
  };
  if (clean(body.phone, 40) && !lead.phone) return { error: 'invalid_phone' };
  if (lead.email && !EMAIL_RE.test(lead.email)) return { error: 'invalid_email' };
  if (!lead.email && !lead.phone) return { error: 'email_or_phone_required' };
  if (!lead.first_name && !lead.last_name && !lead.email) return { error: 'name_required' };
  return { lead };
}

export function createBridge(opts = {}) {
  const twentyUrl = (opts.twentyUrl || process.env.TWENTY_URL || 'http://127.0.0.1:3010').replace(/\/+$/, '');
  const keyFile = opts.keyFile || process.env.TWENTY_API_KEY_FILE || path.join(__dirname, '.twenty-key');
  const allowed = (opts.allowedOrigins || process.env.ALLOWED_ORIGINS || '*').split(',').map((s) => s.trim()).filter(Boolean);
  const rateLimit = opts.rateLimitPerMinute || 20;
  const hits = new Map();

  function apiKey() {
    if (opts.apiKey !== undefined) return opts.apiKey;
    if (process.env.TWENTY_API_KEY) return process.env.TWENTY_API_KEY.trim();
    try { return existsSync(keyFile) ? readFileSync(keyFile, 'utf8').trim() : ''; } catch { return ''; }
  }

  function limited(ip) {
    const now = Date.now();
    const arr = (hits.get(ip) || []).filter((t) => now - t < 60000);
    arr.push(now);
    hits.set(ip, arr);
    if (hits.size > 5000) for (const [k, v] of hits) if (!v.some((t) => now - t < 60000)) hits.delete(k);
    return arr.length > rateLimit;
  }

  function corsHeaders(req) {
    const origin = req.headers.origin;
    const h = { 'access-control-allow-methods': 'POST, OPTIONS', 'access-control-allow-headers': 'content-type', 'access-control-max-age': '600', vary: 'Origin' };
    if (allowed.includes('*')) h['access-control-allow-origin'] = '*';
    else if (origin && allowed.includes(origin)) h['access-control-allow-origin'] = origin;
    return h;
  }

  function send(req, res, status, obj) {
    const body = JSON.stringify(obj);
    res.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', 'x-content-type-options': 'nosniff', ...corsHeaders(req) });
    res.end(body);
  }

  function readJson(req) {
    return new Promise((resolve, reject) => {
      let size = 0; const chunks = [];
      req.on('data', (c) => {
        size += c.length;
        if (size > MAX_BODY) { reject(Object.assign(new Error('too_large'), { status: 413 })); req.destroy(); return; }
        chunks.push(c);
      });
      req.on('end', () => {
        try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8') || 'null')); }
        catch { reject(Object.assign(new Error('invalid_json'), { status: 400 })); }
      });
      req.on('error', reject);
    });
  }

  async function twenty(method, pathname, key, body) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 8000);
    try {
      const r = await fetch(twentyUrl + pathname, {
        method,
        headers: { authorization: 'Bearer ' + key, 'content-type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: ctrl.signal,
      });
      const text = await r.text();
      let json = null;
      try { json = text ? JSON.parse(text) : null; } catch { /* not json */ }
      return { status: r.status, json };
    } finally { clearTimeout(t); }
  }

  // Twenty wraps results as { data: { people: [...] } } or { data: { createPerson: {...} } }.
  const pick = (json, ...names) => {
    const d = json && json.data;
    if (!d) return null;
    for (const n of names) if (d[n] !== undefined) return d[n];
    return null;
  };

  async function findByEmail(key, email) {
    const q = '/rest/people?limit=1&filter=' + encodeURIComponent('emails.primaryEmail[eq]:"' + email + '"');
    const r = await twenty('GET', q, key);
    if (r.status === 401 || r.status === 403) throw Object.assign(new Error('bad_key'), { code: 'bad_key' });
    if (r.status >= 400) throw new Error('lookup_failed_' + r.status);
    const people = pick(r.json, 'people') || [];
    return people.length ? people[0] : null;
  }

  async function createPerson(key, lead) {
    const person = { name: { firstName: lead.first_name, lastName: lead.last_name }, emails: { primaryEmail: lead.email } };
    if (lead.phone) {
      // New Zealand numbers are split into country and national parts; any other country's
      // number is stored whole in E.164 form (we cannot guess other calling-code lengths).
      person.phones = lead.phone.startsWith('+64')
        ? { primaryPhoneNumber: lead.phone.slice(3), primaryPhoneCountryCode: 'NZ', primaryPhoneCallingCode: '+64' }
        : { primaryPhoneNumber: lead.phone };
    }
    const r = await twenty('POST', '/rest/people', key, person);
    if (r.status === 401 || r.status === 403) throw Object.assign(new Error('bad_key'), { code: 'bad_key' });
    if (r.status >= 400) throw new Error('create_failed_' + r.status);
    const created = pick(r.json, 'createPerson', 'person');
    if (!created || !created.id) throw new Error('create_no_id');
    return created;
  }

  async function addNote(key, personId, lead) {
    const lines = ['Source: ' + lead.source];
    if (lead.plan) lines.push('Plan: ' + lead.plan);
    if (lead.company) lines.push('Company: ' + lead.company);
    if (lead.message) lines.push('', lead.message);
    try {
      const n = await twenty('POST', '/rest/notes', key, { title: 'Website enquiry', bodyV2: { markdown: lines.join('\n') } });
      const note = pick(n.json, 'createNote', 'note');
      if (n.status >= 400 || !note || !note.id) return false;
      const t = await twenty('POST', '/rest/noteTargets', key, { noteId: note.id, personId });
      return t.status < 400;
    } catch { return false; }
  }

  async function handleLead(req, res) {
    const ip = req.socket.remoteAddress || 'x';
    if (limited(ip)) return send(req, res, 429, { ok: false, error: 'rate_limited' });
    let body;
    try { body = await readJson(req); }
    catch (e) { return send(req, res, e.status || 400, { ok: false, error: e.message }); }
    if (body && typeof body === 'object' && body.website) return send(req, res, 200, { ok: true }); // honeypot
    const v = validateLead(body);
    if (v.error) return send(req, res, 400, { ok: false, error: v.error });
    const key = apiKey();
    if (!key) return send(req, res, 503, { ok: false, error: 'not_configured' });
    try {
      let person = v.lead.email ? await findByEmail(key, v.lead.email) : null;
      const duplicate = !!person;
      if (!person) person = await createPerson(key, v.lead);
      const note = await addNote(key, person.id, v.lead);
      return send(req, res, 200, { ok: true, twenty_id: person.id, duplicate, note });
    } catch (e) {
      if (e.code === 'bad_key') return send(req, res, 503, { ok: false, error: 'not_configured' });
      return send(req, res, 502, { ok: false, error: 'crm_unavailable' });
    }
  }

  const server = http.createServer((req, res) => {
    const url = (req.url || '/').split('?')[0];
    if (req.method === 'OPTIONS') { res.writeHead(204, corsHeaders(req)); return res.end(); }
    if (req.method === 'GET' && url === '/health') return send(req, res, 200, { ok: true, configured: !!apiKey() });
    if (req.method === 'POST' && url === '/lead') return handleLead(req, res).catch(() => send(req, res, 500, { ok: false, error: 'server_error' }));
    return send(req, res, 404, { ok: false, error: 'not_found' });
  });
  return { server };
}

if (import.meta.url === pathToFileURL(process.argv[1] || '').href) {
  const port = Number(process.env.PORT || 4410);
  const host = process.env.HOST || '127.0.0.1';
  const { server } = createBridge();
  server.listen(port, host, () => console.log(`Concierge lead bridge listening on http://${host}:${port}`));
}
