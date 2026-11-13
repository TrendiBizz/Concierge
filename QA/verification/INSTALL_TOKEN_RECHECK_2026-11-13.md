# Install token recheck

The "install token" is the `data-key` in the snippet a business pastes into its site:

```html
<script src="https://chat.trendibizz.com/widget.js" data-key="pk_..." defer></script>
```

It is the tenant's `public_key`, and it is the only credential the public widget carries, so it was
checked end to end against production.

## What was verified

| Check | Result |
|---|---|
| `GET /widget.js` | **200**, 33,464 bytes, `application/javascript` |
| Valid key → `GET /api/v1/widget-config?key=…` | **200** with name, greeting, CTA, accent, voice flags |
| Conrad's key (`pk_cfR6…`) | **200** — read-only, creates nothing |
| The key trendibizz.com actually serves (`pk_8y_ws…`) | **200** — belongs to tenant `trendi-oauth-staging`, owned by admin@trendibizz.com |
| Wrong key | **404 `Unknown key`** |
| No key | **422** |
| `install-check` on pukekoconstruction.co.nz | `found:false, script:false` — "could not find the chat script" |
| `install-check` on trendibizz.com | `found:false, script:true, key:false` — "we found the chat script but not this business's key. The snippet belongs to another business." (correct: that page carries a different tenant's key) |

## Findings

1. **Conrad's chat is not installed.** His key is valid and answers, but
   `pukekoconstruction.co.nz` does not contain `widget.js` at all. He needs the snippet added before
   the closing `</body>`; until then his window does not exist. This is the onboarding step that
   remains for him, not a fault.
2. **The production site's chat belongs to a tenant called `trendi-oauth-staging`.** It works and it
   is owned by admin@trendibizz.com, so enquiries are readable — but the slug is a leftover name on
   the live business. Cosmetic, and renaming a slug would break the site's key only if the key
   changed; recorded rather than changed.
3. **A key could never be revoked.** The archived prototype tenant still answered `widget-config`
   **200** with a live greeting. The only way to stop a retired business answering was to delete the
   business. Fixed: `POST /admin/tenants/{slug}/rotate-key` (operator only) issues a new key and the
   old one stops resolving at once.

## Proof of the revocation fix

| Before | After |
|---|---|
| `pk_archived_6wGO9X8isFPV9oHn_qqaOZ6n` → **200** | → **404** |
| — | new key `pk_Yktk2EIa5mV3w4ASKbMa7fSb` |
| Conrad's key `pk_cfR6…` | **200** (unchanged) |
| trendibizz.com key `pk_8y_ws…` | **200** (unchanged) |

Tests: `tests/test_install_key_revocation.py` (4). Full suite **1138**.
