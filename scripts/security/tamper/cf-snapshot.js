// cf-snapshot.js: READ-ONLY Cloudflare state snapshot for daily-watch.sh.
// Every call below is method:'GET'. Nothing here creates, updates or deletes.
// Run via the Cloudflare MCP:  user-Cloudflare execute, code="$file:<this file>",
// truncate:false, write_to_file:true  -> pass the written file to
// daily-watch.sh --cf-snapshot <file>.  Output contains no secret values
// (env var NAMES and types only; Worker source is reduced to a sha256).
async () => {
  const AID = '56c407fbb54833210ff95715e68bd2a6';
  const ZID = 'a4423f40b6515494e2c071d4beb44b7a';
  const PROJECT = 'trendi';
  const WORKER = 'trendi-force-https';
  const errors = [];
  const get = async (key, path, query) => {
    try {
      const r = await cloudflare.request({ method: 'GET', path, query });
      return r;
    } catch (e) { errors.push(key + ': ' + String(e.message).split('\n')[0].slice(0, 160)); return undefined; }
  };
  const sha256 = async (bytes) => {
    const h = await crypto.subtle.digest('SHA-256', bytes);
    return [...new Uint8Array(h)].map(b => b.toString(16).padStart(2, '0')).join('');
  };
  const sortBy = (arr, f) => arr.slice().sort((a, b) => (f(a) < f(b) ? -1 : f(a) > f(b) ? 1 : 0));
  const snap = { tool: 'cf-snapshot.js', version: 1, generated_at: new Date().toISOString(), sections: {} };
  const S = snap.sections;

  // DNS records (content only; ids/timestamps dropped)
  const dns = await get('dns', `/zones/${ZID}/dns_records`, { per_page: 500 });
  if (dns) S.dns = sortBy(dns.result.map(r => ({ type: r.type, name: r.name, content: r.content, proxied: r.proxied, ttl: r.ttl, priority: r.priority ?? null, data: r.data ?? null })), r => r.type + r.name + r.content);

  // DNSSEC
  const ds = await get('dnssec', `/zones/${ZID}/dnssec`);
  if (ds) S.dnssec = { status: ds.result.status, ds: ds.result.ds || null, algorithm: ds.result.algorithm || null, key_tag: ds.result.key_tag || null };

  // Zone (nameservers, plan, status)
  const z = await get('zone', `/zones/${ZID}`);
  if (z) S.zone = { name: z.result.name, status: z.result.status, paused: z.result.paused, plan: z.result.plan?.name, name_servers: z.result.name_servers, type: z.result.type };

  // Main zone settings
  const want = ['ssl', 'min_tls_version', 'tls_1_3', 'always_use_https', 'automatic_https_rewrites', 'security_header', 'opportunistic_encryption', 'security_level', 'browser_check', 'email_obfuscation', 'server_side_exclude', 'hotlink_protection', 'universal_ssl', 'ip_geolocation', 'development_mode', 'browser_cache_ttl', 'cache_level', '0rtt', 'http3', 'websockets', 'always_online', 'rocket_loader', 'mirage', 'polish', 'minify'];
  const st = await get('settings', `/zones/${ZID}/settings`);
  if (st) S.zone_settings = Object.fromEntries(sortBy(st.result.filter(s => want.includes(s.id)), s => s.id).map(s => [s.id, s.value]));
  const us = await get('universal_ssl', `/zones/${ZID}/ssl/universal/settings`);
  if (us && S.zone_settings) S.zone_settings.universal_ssl_enabled = us.result.enabled;

  // Rulesets: managed = identity only; zone/custom = full rules
  const rs = await get('rulesets', `/zones/${ZID}/rulesets`);
  if (rs) {
    const out = [];
    for (const r of sortBy(rs.result, x => x.phase + x.name)) {
      const entry = { name: r.name, phase: r.phase, kind: r.kind };
      if (r.kind !== 'managed') {
        const d = await get('ruleset:' + r.phase, `/zones/${ZID}/rulesets/${r.id}`);
        if (d) entry.rules = (d.result.rules || []).map(x => ({ id: x.id, description: x.description || '', expression: x.expression, action: x.action, enabled: x.enabled, action_parameters: x.action_parameters ?? null, ratelimit: x.ratelimit ?? null }));
        else entry.rules_unreadable = true;
      }
      out.push(entry);
    }
    S.rulesets = out;
  }

  // Workers: account script list, our Worker's source hash, zone routes
  const ws = await get('workers', `/accounts/${AID}/workers/scripts`);
  if (ws) S.worker_scripts = sortBy(ws.result.map(s => ({ id: s.id, modified_on: s.modified_on })), s => s.id);
  const wc = await get('worker_content', `/accounts/${AID}/workers/scripts/${WORKER}/content/v2`);
  if (wc !== undefined) {
    let text = typeof wc === 'string' ? wc : (wc instanceof Uint8Array ? new TextDecoder().decode(wc) : JSON.stringify(wc));
    // Multipart with a random boundary: hash part names + bodies, not the boundary
    const m = text.match(/^--([^\r\n]+)\r?\n/);
    let canon = text;
    if (m) {
      const parts = text.split('--' + m[1]).map(p => p.replace(/^\r?\n/, '')).filter(p => p && !p.startsWith('--'));
      canon = parts.map(p => { const i = p.search(/\r?\n\r?\n/); const hdr = i >= 0 ? p.slice(0, i) : ''; const body = i >= 0 ? p.slice(i).replace(/^\r?\n\r?\n/, '').replace(/\r?\n$/, '') : p; const name = (hdr.match(/name="([^"]+)"/) || [])[1] || ''; return name + '\n' + body; }).join('\n--part--\n');
    }
    S.worker = { name: WORKER, source_sha256: await sha256(new TextEncoder().encode(canon)), source_bytes: canon.length };
  }
  const wr = await get('worker_routes', `/zones/${ZID}/workers/routes`);
  if (wr) S.worker_routes = sortBy(wr.result.map(r => ({ pattern: r.pattern, script: r.script ?? null })), r => r.pattern);

  // Account members, user 2FA, account 2FA enforcement
  const mem = await get('members', `/accounts/${AID}/members`, { per_page: 50 });
  if (mem) S.members = sortBy(mem.result.map(x => ({ email: x.user?.email, status: x.status, two_factor: x.user?.two_factor_authentication_enabled ?? null, roles: (x.roles || []).map(r => r.name).sort() })), m => m.email || '');
  const acct = await get('account', `/accounts/${AID}`);
  if (acct) S.account = { name: acct.result.name, enforce_twofactor: acct.result.settings?.enforce_twofactor ?? null };
  const u = await get('user', `/user`);
  if (u) S.account.user_two_factor = u.result.two_factor_authentication_enabled;

  // Notifications
  const np = await get('notifications', `/accounts/${AID}/alerting/v3/policies`);
  if (np) S.notifications = sortBy(np.result.map(p => ({ name: p.name, alert_type: p.alert_type, enabled: p.enabled, filters: p.filters ?? null, mechanisms: Object.fromEntries(Object.entries(p.mechanisms || {}).map(([k, v]) => [k, (v || []).map(x => x.id).sort()])) })), p => p.name);

  // Client-side security (Page Shield)
  const ps = await get('page_shield', `/zones/${ZID}/page_shield`);
  if (ps) S.page_shield = { enabled: ps.result.enabled };

  // Pages project config (env var NAMES + types only)
  const pr = await get('pages_project', `/accounts/${AID}/pages/projects/${PROJECT}`);
  if (pr) {
    const r = pr.result, dc = r.deployment_configs || {};
    const cfg = (c) => c ? { compatibility_date: c.compatibility_date ?? null, compatibility_flags: c.compatibility_flags ?? [], env_vars: Object.fromEntries(Object.entries(c.env_vars || {}).sort().map(([k, v]) => [k, v?.type ?? null])), bindings: Object.keys(c).filter(k => /namespaces|buckets|databases|services|bindings|queue|vectorize|ai|hyperdrive|analytics/i.test(k) && c[k] && Object.keys(c[k]).length).sort(), fail_open: c.fail_open ?? null, usage_model: c.usage_model ?? null } : null;
    S.pages_project = { name: r.name, production_branch: r.production_branch, source: r.source ?? null, build_config: r.build_config ?? null, domains: (r.domains || []).slice().sort(), production: cfg(dc.production), preview: cfg(dc.preview) };
    snap.canonical_deployment = r.canonical_deployment?.id ?? null;
  }
  const pd = await get('pages_domains', `/accounts/${AID}/pages/projects/${PROJECT}/domains`);
  if (pd && S.pages_project) S.pages_project.custom_domains = sortBy(pd.result.map(d => ({ name: d.name, status: d.status })), d => d.name);

  // Deployments: newest 50 only (2 pages x 25, newest first). Capped so the MCP execute output does not
  // truncate the list and insert a '--- TRUNCATED ---' string (76+ deploys on 2026-11-03). Not a baseline
  // section: checked against changes.csv.
  const MAX_DEPLOYS = 50, DEP_PAGE = 25;
  const deps = [];
  for (let page = 1; page <= MAX_DEPLOYS / DEP_PAGE; page++) {
    const d = await get('deployments_p' + page, `/accounts/${AID}/pages/projects/${PROJECT}/deployments`, { per_page: DEP_PAGE, page });
    if (!d) break;
    for (const x of d.result) deps.push({ id: x.id, environment: x.environment, created_on: x.created_on, trigger: x.deployment_trigger?.type ?? null, message: (x.deployment_trigger?.metadata?.commit_message || '').slice(0, 80), status: x.latest_stage?.status ?? null });
    if (d.result.length < DEP_PAGE) break;
  }
  // Omit the key entirely when the Pages API was not readable, so the watch
  // says "could not check" instead of passing an empty list as all-clear.
  if (deps.length) snap.deployments = deps.slice(0, MAX_DEPLOYS);
  else errors.push('deployments: no deployments returned (Pages token scope?)');
  snap.errors = errors;
  return snap;
}
