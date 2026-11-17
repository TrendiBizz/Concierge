// cf-run-snapshot.js: Mac runner for cf-snapshot.js (unchanged). GET-only.
// Token comes from env CF_READONLY_TOKEN (set by run-snapshot.sh from the Keychain). Never printed or written.
// Usage: node cf-run-snapshot.js <out.json>
const fs = require('fs');
const path = require('path');
const token = process.env.CF_READONLY_TOKEN;
if (!token) { console.error('CF_READONLY_TOKEN not set'); process.exit(2); }
const out = process.argv[2];
if (!out) { console.error('usage: node cf-run-snapshot.js <out.json>'); process.exit(2); }
const cloudflare = {
  request: async ({ method, path: p, query }) => {
    if (String(method).toUpperCase() !== 'GET') throw new Error('refused non-GET');
    const qs = query ? '?' + new URLSearchParams(Object.entries(query).map(([k, v]) => [k, String(v)])).toString() : '';
    const r = await fetch('https://api.cloudflare.com/client/v4' + p + qs, { method: 'GET', headers: { Authorization: 'Bearer ' + token } });
    const ct = r.headers.get('content-type') || '';
    const body = ct.includes('json') ? await r.json() : await r.text();
    if (!r.ok || (body && body.success === false)) {
      const msg = body && body.errors && body.errors[0] ? body.errors[0].message : 'HTTP ' + r.status;
      throw new Error('HTTP ' + r.status + ' ' + msg);
    }
    return body;
  },
};
(async () => {
  const src = fs.readFileSync(path.join(__dirname, 'cf-snapshot.js'), 'utf8');
  const fn = new Function('cloudflare', 'crypto', 'return (' + src.replace(/^\s*\/\/.*$/gm, '').trim().replace(/;\s*$/, '') + ');')(cloudflare, globalThis.crypto);
  const snap = await fn();
  fs.writeFileSync(out, JSON.stringify(snap), { mode: 0o600 });
  console.log('snapshot written:', out, 'sections:', Object.keys(snap.sections).length, 'errors:', snap.errors.length);
  if (snap.errors.length) console.log(snap.errors.join('\n'));
})().catch(e => { console.error('fail:', String(e.message).slice(0, 200)); process.exit(2); });
