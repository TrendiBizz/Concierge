// Regression tests for cf-snapshot.js (no network).
//   node tests/test_snapshot.js
// Covers the 2026-11-17 defects: a Pages 403 was written out as an empty
// deployments list (read as "all clear"), and a ruleset whose detail could not
// be read silently lost its rules (read as "rules removed").
const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '..', 'cf-snapshot.js');
const ZID = 'a4423f40b6515494e2c071d4beb44b7a';

function mockCloudflare() {
  return {
    request: async ({ method, path: p }) => {
      if (String(method).toUpperCase() !== 'GET') throw new Error('refused non-GET');
      const err403 = (m) => { const e = new Error('HTTP 403 ' + m); e.status = 403; throw e; };
      if (p.endsWith('/rulesets')) {
        return { result: [
          { id: 'r-redirect', name: 'default', phase: 'http_request_dynamic_redirect', kind: 'zone' },
          { id: 'r-custom', name: 'custom', phase: 'http_request_firewall_custom', kind: 'zone' },
          { id: 'r-managed', name: 'managed', phase: 'http_request_firewall_managed', kind: 'managed' },
        ] };
      }
      if (p.includes('/rulesets/r-redirect')) { err403('request is not authorized'); }
      if (p.includes('/rulesets/r-custom')) {
        return { result: { rules: [{ id: 'x', action: 'block', expression: 'true', enabled: true }] } };
      }
      if (p.includes('/ssl/universal/settings')) { err403('Unauthorized'); }
      if (p.endsWith('/settings')) {
        return { result: [
          { id: 'ssl', value: 'strict' },
          { id: 'min_tls_version', value: '1.2' },
        ] };
      }
      if (p.includes('/pages/')) { err403('Authentication error'); }
      if (p.endsWith('/workers/scripts')) { return { result: [] }; }
      if (p.endsWith('/user')) { err403('Unauthorized'); }
      if (p.endsWith('/zones/' + ZID)) { return { result: { name: 'trendibizz.com', status: 'active', plan: { name: 'Free' }, name_servers: [], type: 'full' } }; }
      return { result: [] };
    },
  };
}

(async () => {
  const src = fs.readFileSync(SRC, 'utf8');
  const fn = new Function('cloudflare', 'crypto', 'return (' + src.replace(/^\s*\/\/.*$/gm, '').trim().replace(/;\s*$/, '') + ');')(mockCloudflare(), globalThis.crypto);
  const snap = await fn();

  const checks = [];
  const check = (name, ok) => checks.push([name, ok]);
  check('deployments key omitted when Pages is unreadable', !('deployments' in snap));
  check('deployments error recorded', snap.errors.some(e => e.startsWith('deployments:')));
  const redirect = (snap.sections.rulesets || []).find(r => r.phase === 'http_request_dynamic_redirect');
  check('unreadable ruleset marked', !!redirect && redirect.rules_unreadable === true && !('rules' in redirect));
  const custom = (snap.sections.rulesets || []).find(r => r.phase === 'http_request_firewall_custom');
  check('readable ruleset keeps rules', !!custom && custom.rules.length === 1);
  check('universal SSL failure recorded', snap.errors.some(e => e.startsWith('universal_ssl:')));
  check('universal_ssl_enabled not invented', !('universal_ssl_enabled' in (snap.sections.zone_settings || {})));

  let failed = 0;
  for (const [name, ok] of checks) {
    console.log((ok ? 'ok   ' : 'FAIL ') + name);
    if (!ok) failed++;
  }
  console.log(`\n${checks.length - failed}/${checks.length} checks passed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error('test crashed:', e); process.exit(2); });
