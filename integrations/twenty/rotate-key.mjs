// Rotate the Twenty API key used by the lead bridge.
//   node rotate-key.mjs              create + test a new key, save it to the keychain, revoke the old key(s)
//   node rotate-key.mjs --keep-old   same, but do not revoke the old key(s)
// The admin password is read from the keychain item "concierge-twenty-admin"; the new key is written to the
// keychain item "concierge-twenty-api-key". No secret is printed or written to a file.
// After it finishes, restart the bridge (./bridge/start.sh) so it picks up the new key.
import { spawnSync } from 'node:child_process';

const EMAIL = process.env.TWENTY_ADMIN_EMAIL || 'admin@trendibizz.com';
const BASE = process.env.TWENTY_URL || 'http://127.0.0.1:3010';
const ORIGIN = process.env.TWENTY_ORIGIN || 'http://localhost:3010';
const KEEP_OLD = process.argv.includes('--keep-old');

const sec = (args, input) => spawnSync('security', args, { encoding: 'utf8', input });
function keychainGet(service) {
  const r = sec(['find-generic-password', '-s', service, '-w']);
  return r.status === 0 ? r.stdout.trim() : '';
}
function keychainSet(service, account, label, secret) {
  // via stdin so the secret never shows in the process list
  const r = sec(['-i'], `add-generic-password -U -a "${account}" -s "${service}" -l "${label}" -w "${secret}"\n`);
  if (r.status !== 0) throw new Error('keychain write failed');
}
async function gql(query, variables, token) {
  const r = await fetch(BASE + '/metadata', {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...(token ? { authorization: 'Bearer ' + token } : {}) },
    body: JSON.stringify({ query, variables }),
  });
  return r.json();
}
const fail = (msg) => { console.error('FAILED: ' + msg); process.exit(1); };

const pw = keychainGet('concierge-twenty-admin');
if (!pw) fail('no admin password in keychain item concierge-twenty-admin');

let r = await gql('mutation($e:String!,$p:String!,$o:String!){ getLoginTokenFromCredentials(email:$e,password:$p,origin:$o){ loginToken{ token } } }', { e: EMAIL, p: pw, o: ORIGIN });
if (r.errors) fail('login: ' + r.errors.map((e) => e.message).join('; '));
r = await gql('mutation($t:String!,$o:String!){ getAuthTokensFromLoginToken(loginToken:$t, origin:$o){ tokens{ accessOrWorkspaceAgnosticToken{ token } } } }', { t: r.data.getLoginTokenFromCredentials.loginToken.token, o: ORIGIN });
if (r.errors) fail('token: ' + r.errors.map((e) => e.message).join('; '));
const wtok = r.data.getAuthTokensFromLoginToken.tokens.accessOrWorkspaceAgnosticToken.token;

// existing keys (to revoke after the new one is proven)
r = await gql('{ apiKeys { id name revokedAt expiresAt } }', {}, wtok);
if (r.errors) fail('listing keys: ' + r.errors.map((e) => e.message).join('; '));
const oldKeys = r.data.apiKeys.filter((k) => !k.revokedAt);
console.log(`existing active keys: ${oldKeys.length} (${oldKeys.map((k) => k.name).join(', ')})`);

r = await gql('{ getRoles { id label } }', {}, wtok);
if (r.errors || !r.data.getRoles.length) fail('roles');
const role = r.data.getRoles.find((x) => /admin/i.test(x.label)) || r.data.getRoles[0];

const stamp = new Date().toISOString().slice(0, 10);
const expiresAt = new Date(Date.now() + 365 * 86400000).toISOString();
r = await gql('mutation($i:CreateApiKeyInput!){ createApiKey(input:$i){ id expiresAt } }', { i: { name: `concierge-lead-bridge-${stamp}`, expiresAt, roleId: role.id } }, wtok);
if (r.errors) fail('createApiKey: ' + r.errors.map((e) => e.message).join('; '));
const created = r.data.createApiKey;
r = await gql('mutation($a:UUID!,$e:String!){ generateApiKeyToken(apiKeyId:$a, expiresAt:$e){ token } }', { a: created.id, e: created.expiresAt }, wtok);
if (r.errors) fail('generateApiKeyToken: ' + r.errors.map((e) => e.message).join('; '));
const newToken = r.data.generateApiKeyToken.token;

// prove the new key works before anything else changes
const probe = await fetch(BASE + '/rest/people?limit=1', { headers: { authorization: 'Bearer ' + newToken } });
if (!probe.ok) fail(`new key rejected by Twenty (HTTP ${probe.status}); nothing was changed except creating it`);
console.log('new key accepted by Twenty (HTTP ' + probe.status + ')');

keychainSet('concierge-twenty-api-key', 'concierge-lead-bridge', 'Twenty API key for the Concierge lead bridge', newToken);
if (keychainGet('concierge-twenty-api-key') !== newToken) fail('keychain did not store the new key');
console.log('saved to keychain item concierge-twenty-api-key; expires ' + created.expiresAt);

if (KEEP_OLD) {
  console.log('--keep-old: old keys left active.');
} else {
  for (const k of oldKeys) {
    const rv = await gql('mutation($i:RevokeApiKeyInput!){ revokeApiKey(input:$i){ id } }', { i: { id: k.id } }, wtok);
    console.log(rv.errors ? `could not revoke ${k.name}: ${rv.errors.map((e) => e.message).join('; ')}` : `revoked ${k.name} (${k.id})`);
  }
}
console.log('Next: restart the bridge so it uses the new key.');
