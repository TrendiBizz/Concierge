# Customer onboarding and separation verification

Verified locally on Mac.hub, 2026-11-09 NZDT. Source-only changes; no production deployment, publishing, provider reauthorization, existing-account unlinking or service restarts.

## Customer journey

The operator can create a separate business and generate its owner's private invitation from the admin UI. Failed invitation creation can be retried without creating a second workspace. Share the resulting link privately; no invitation email is automatically sent. The link expires after 24 hours and is single-use. Its secret is in the URL fragment, which the owner client consumes and removes before requests.

The customer sets and confirms a password, then signs into the correct workspace automatically. A setup checklist leads to editable business details, private knowledge and configured social providers. Text and Markdown files up to 100 KB can be reviewed locally before upload. Saving the same document title replaces that customer's version. Saving a website does not crawl it, approve an origin or activate channels. Unsupported social providers are hidden; provider help explains account requirements before connecting. Owner/editor/viewer permissions remain enforced server-side.

## Failures reproduced and fixed

- Business name/site edits were unavailable; now explicit validated owner fields.
- No owner knowledge upload route; now bounded list/save/delete routes derived from the authenticated tenant, with no caller-supplied tenant selection.
- Failed embeddings deleted previously saved knowledge; embeddings now complete before transactional replacement. Concurrent replacements/deletions use a tenant/document advisory lock.
- A customer could create a draft referencing another customer's social account; the Rust store now rejects every unowned account before inserting the draft.
- Sign-out left private draft fields in the page, and old session responses could paint a subsequent session; reset and session-generation guards now reject these results, including pending local file reads.
- Invitation redemption required customers to manually re-enter workspace details; successful redemption now provides the correct workspace and the client signs in immediately.
- Simultaneous same-name workspace creation caused a unique-constraint failure; atomic insert/conflict retry produces separate workspaces.
- Long business names generated slugs rejected by the social bridge; newly generated base slugs are bounded to 80 characters, leaving room for collision suffixes. Existing slugs unchanged.

## Verification

- 8 full customer-journey tests: real disposable pgvector PostgreSQL and real Rust HTTP service, two owners and a viewer, independent data/RAG retrieval, scoped deletion/replacement, failed embedding preservation, invitation replay rejection, simultaneous creation, long names, upload validation, provider OAuth-state separation, cross-customer account/draft rejection. Embedding calls alone use deterministic synthetic vectors; provider account fixtures use synthetic credentials and no external token exchange.
- 18 existing onboarding/social owner tests passed.
- 52 existing Python unit tests passed.
- 56 Rust tests passed; locked Clippy with warnings denied passed.
- 9 Node tests passed: invitation flow, sign-out cleanup, stale HTTP/file rejection, local file review, operator retry and existing widget controls. These execute actual inline scripts in a small in-memory DOM, not a real browser.
- Python syntax compilation and git whitespace checks passed.
- CI extended to run the new PostgreSQL/Rust journey and client scripts; remote CI execution is not certified by these local results.

Disposable PostgreSQL runs only at 127.0.0.1:55432 with test credentials. Rust fixture uses a random private loopback port and temporary SQLite database. Neither fixture uses live customer credentials or port 4390. Publishing and outbox are disabled. The owned QA PostgreSQL container is removed after verification.

## Remaining release gates

No production rollout is authorized. No real-browser visual/accessibility verification was performed: browser origin approval was previously refused; no alternate automation was used to bypass it. Existing staging grants are not proof of platform approval for arbitrary customer accounts. TikTok remains sandbox; Meta customer eligibility/app review must be verified; LinkedIn currently proves member-profile access, not company-Page management. A controlled real customer consent test and browser QA remain necessary before advertising fully verified customer onboarding. No password, token, real account ID or invitation secret is stored in this evidence.
