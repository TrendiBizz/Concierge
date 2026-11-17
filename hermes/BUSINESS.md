# The business: SEO and authorized security testing in one Hermes

This is how the two Trendi revenue lines fit together and where Hermes sits. The
technical detail is in the pen-test repo: `PENETRATION_TESTING_SERVICE.md`,
`METHODOLOGY_AND_TEST_REGIMEN.md`, `TOOLING_AND_AUTOMATION.md`, `UMBRELLA.md`.

## 1. The two offers

| Line | What the customer buys | Who delivers | Recurring? |
|---|---|---|---|
| **SEO / AI visibility** | Indexed → Found → Mentioned: the site, content, GSC/Bing, AI-search presence | `seo-engine` + `trendi-desk` | Monthly/quarterly |
| **Authorized security testing** | Surface Check, Web App, API, Cloud, Code, Retest: evidence and fixes | `pen-test` + the umbrella | Annual + retest, or a retainer |

They share a buyer (an SME that needs to be found *and* trusted), a proof standard
(measured, cited, no invented numbers) and a delivery habit (report → fix → verify).
Security findings are also a legitimate reason to talk to an existing SEO client, and
the SEO site is the trust surface that sells the testing.

## 2. The security offer

| Service | Scope | Duration | Deliverable |
|---|---|---|---|
| Surface Check | One domain, public DNS/TLS/HTTP/email posture; safe active checks | 1–2 days | Prioritised external attack-surface report |
| Web App Assessment | One app/API, test accounts per role | 5–10 days | OWASP WSTG-based findings, CVSS 4.0, evidence, fixes |
| API / Integration | REST/GraphQL, auth, object-level access, webhooks | 3–7 days | API report + retest |
| Cloud / SaaS Review | Read-only IAM, storage, logging, exposure | 2–5 days | Configuration findings and hardening plan |
| Code & Supply Chain | SAST, secrets, dependencies, IaC, CI trust | 2–5 days | Code-level findings + SBOM plan |
| Retest | The exact original evidence steps + regression | 0.5–2 days | Pass/fail per finding, residual risk |

**Out of scope by default:** DoS/load, social engineering, phishing, physical, wireless,
third-party services the customer does not own, destructive changes. These need a
separate signed authorization and, for DoS, a separate environment and window.

## 3. The pipeline

```
lead → qualify → scoping call → signed authorization + contract
     → kickoff (contacts, canary, accounts, window)
     → passive recon → active recon → discovery → analysis → validation
     → report draft → QA → customer report → debrief
     → remediation → retest → closure/retainer
```

Every stage has an owner and a written artefact. The authorization is the gate: no
authorization, no active traffic. The umbrella enforces that in code; PRE and T3MP3ST
add their own scopes and approvals.

## 4. Where Hermes fits

| Profile | Business job |
|---|---|
| `trendi-master` | Owns the morning brief and the weekly business review; reads the pen-test lane, the SEO lane and the worklist |
| `seo-engine` | The SEO/AI-visibility delivery and measurement |
| `trendi-desk` | The content, social and post-brief lane; the trust surface |
| `pen-test` | The authorized-testing lane: engagement status, authorization expiry, report QA, retest, defensive content |
| `site-watch` | Site integrity and tamper alerts |
| `workwatch` | The weekly automation review |

The **umbrella** at <http://127.0.0.1:9130> is the pen-test console: engagements,
authorization, scope, PRE, T3MP3ST, Ghidra, findings, tools. The Hermes Dashboard at
<http://127.0.0.1:9120> is the agent console. They are deliberately separate: Hermes
talks and reports; the umbrella executes a gated test.

## 5. The weekly business review

Add these to the Monday `master-weekly-review`:

- Leads and quotes in the SEO and security lines; what needs a scoping call.
- Engagements in flight; days remaining; authorization expiry within 14 days.
- Drafts/reports waiting on QA; retests due; open critical/high findings.
- Delivered this week; retest pass rate; customer-reported issues.
- Utilisation: how much of the week went to delivery vs sales vs admin.
- One process change for the week, with the reason and how to undo it.

No invented numbers. A pipeline item with no date is `UNVERIFIED`, not "warm".

## 6. Guardrails that make the business safe

- **Written authorization only.** A signed document naming target, dates, tester and
  permitted actions. The template is in `PENETRATION_TESTING_SERVICE.md` §3.
- **Scope in code.** The Rust gate checks every active step; PRE and T3MP3ST have their
  own scopes. Never bypass either to "save time".
- **No report without QA.** Every confirmed finding needs reproducible evidence, CVSS,
  CWE, a specific fix and a second pair of eyes on high/critical.
- **No public disclosure** without written consent. Stop and call the emergency contact
  if a live compromise is found.
- **Data minimisation.** Encrypt, redact, retain 90 days after the final report, then
  delete. Never put customer data into a public model or a cloud scanner without
  consent.
- **Licences.** GPL/AGPL tools run as separate processes; get legal advice before
  bundling or hosting them. The AGPL secret scanner (TruffleHog) is opt-in; Gitleaks is
  the default.
- **Insurance and contract** before the first paid test; legal review of the
  authorization and the privacy terms.

## 7. Pricing and packaging (Jo sets the numbers)

The engine does not set prices. A workable shape:

- Surface Check: fixed fee, 1–2 days.
- Web App: fixed fee per app, 5–10 days, one account per role.
- API: fixed fee per API/spec, 3–7 days.
- Cloud: day rate, read-only.
- Code: fixed fee per repo up to an agreed LOC.
- Retest: 50% of the original fee within 30 days.
- Out of scope: a new authorization and a new quote. No "while we are here".

Every quote states assumptions, customer responsibilities, exclusions and validity
(30 days). Payment, cancellation and liability are in the contract.

## 8. What is ready, what is next

**Ready:** the offer, the authorization/RoE requirements, the methodology, the tool
matrix, the Rust gate, the umbrella GUI, PRE and T3MP3ST integration, Ghidra headless.

**Next:**
1. Jo sets the prices and the first authorization/contract template.
2. Run one **lab** engagement end to end (Juice Shop/DVWA) through the umbrella and
   produce a report; fix anything that breaks.
3. Run one **real** Surface Check on a customer-owned domain with a signed
   authorization; deliver, then retest.
4. Add the report-QA and retest steps to the pen-test routine.
5. Connect the Studio/website to the offer (a services page and a booking path) once
   the first case study exists.
