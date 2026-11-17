# Accepted tamper-watch changes (revert notes)

The authoritative one-line approvals are in `ACCEPT-LOG.txt`. This file records
**what changed and how to undo it**, so a revert is possible without guessing.
Baselines are snapshots, not deploys: reverting here only changes what the watch
expects. Change the live system separately.

## 2026-11-17 — mail DNS accepted (Jo confirmed)

Accepted sections: `dns`, `public_dns`, plus the config drift below.

| Record | Old baseline | Now | Revert |
|---|---|---|---|
| MX `trendibizz.com` | `mx1-hosting.jellyfish.systems` prio 5, `mx2` 10, `mx3` 20 | `route1.mx.cloudflare.net` 59, `route2` 48, `route3` 81 | Dashboard DNS: restore the three Jellyfish MX records at 5/10/20. **Only if abandoning Cloudflare Email Routing — inbound mail will follow the MX.** |
| TXT `_dmarc` | `v=DMARC1; p=none; rua=mailto:rua@dmarc.brevo.com` | `v=DMARC1; p=quarantine; rua=mailto:rua@dmarc.brevo.com` | Set `p=none` in the DMARC TXT. |
| TXT `cf2024-1._domainkey` | absent | Cloudflare Email Routing DKIM key | Delete the record (Email Routing stops signing/forwarding correctly). |
| TXT SPF | `v=spf1 +a +mx +ip4:63.250.38.99 +ip4:67.223.118.42 include:spf.web-hosting.com ~all` | same + `include:_spf.mx.cloudflare.net` | Remove the Cloudflare include. |

Evidence that this was planned: `QA/verification/INBOUND_EMAIL_SECURITY_2026-11-11.md`
(Cloudflare Email Routing is the inbound path) and
`QA/verification/EMAIL_ASSESSMENT_2026-11-12.md` (DMARC quarantine was an operator
decision). Jo confirmed 2026-11-17.

## 2026-11-17 — config drift accepted after review

| Section | Old baseline | Now | Revert |
|---|---|---|---|
| `zone_settings` | `min_tls_version: 1.0` | `1.2` | SSL/TLS → Edge Certificates → Minimum TLS 1.0. Not recommended. The unreadable `universal_ssl_enabled` value is preserved from the old baseline. |
| `rulesets` | Rate limit `api-robots`: 5 requests/10 s, expression `starts_with(http.request.uri.path, "/api/")` | 60/10 s, and exempts `/api/v1/translate`, `/api/v1/widget-`, `/api/v1/chat`, `/api/v1/voice` | Dashboard WAF custom rules: restore 5/10 s and the old expression. **Do not** — 5/10 s broke the chat widget (`QA/verification/CLOUDFLARE_THROTTLE_2026-11-13.md`). |
| `rulesets` | no such rule | `Block AI training crawlers`: block GPTBot/CCBot/Bytespider/ClaudeBot/Google-Extended/Applebot-Extended/Amazonbot/FacebookBot, except `/robots.txt` | Delete the custom rule in WAF. |
| `rulesets` | `http_request_dynamic_redirect` rules: www→apex, `not ssl`→https, `/tools/security-check`→`/security-check` | rules unreadable (token 403); the old baseline entries are **kept** | Nothing to revert yet; when the scope is added, the watch will compare them. Live probes still pass all three redirects. |
| `worker_scripts` | Worker `trendi-force-https` (2026-10-28) | list is empty | Upload `deploy_known_good/_worker.js` from the old `trendi-site` checkout and restore the script. The zone routes still name it, so they are inert until then. Removed as part of the Concierge cutover (APIs moved to the VPS); `/api/robots` is now 404. |
| `notifications` | 7 policies | 9 — two `billing_budget_alert` policies at USD 10, one of them "Default budget alert (auto-created)" | Cloudflare Notifications: delete the two billing alerts. They do not affect site security. |
| `page_shield` | disabled | enabled | Security → Page Shield → disable. Enabling is the safer state. |

`deployments` was already OK: six historic Pages deploys are in
`deployments_ledger.csv`; the current canonical deployment `6bcc4248` is accepted
and matches the live project. Pages is legacy — the site is served from the VPS by
`deploy-site.sh`, and `live_integrity` (live vs this repo's `website/`) is the real
content check.
