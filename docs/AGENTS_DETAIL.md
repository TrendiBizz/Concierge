# Working agreement — Trendi Concierge

Every session reads `docs/AGENT_WORKING_ORDER.md` first.

**This repository is the only place work lives.** One repository, one commit history, one deploy
path. If a change is not committed here, it does not exist, and it will be lost or silently
diverged by the next agent who touches the system.

Read this before writing anything. It is enforced by tooling, not by memory.

## The rule that keeps getting broken

On 2026-11-15 three separate drifts were found in one session:

1. The website was being published from `/Users/jo/work-staging/trendibizz-live/site`, a loose
   directory that was **not a git repository**. Three agents edited it. Seventeen files — including
   three pages and the whole CSS/JS layer — reached production without ever being committed.
2. The box carried a newer `healthcheck.py` than the repo: someone fixed a live defect on the
   server, and the fix never came back.
3. The repo carried API code the box had never run, including a real defect: a Microsoft
   account-verification email was being treated as a customer enquiry and forwarded as an owner SMS
   containing the security code.

None of this was visible from a green health check. "It works" and "it is what we committed" are
different questions.

## Where things live

| What | Path | Rules |
|---|---|---|
| The website source | `website/` | **The only site source.** Deploy with `scripts/vps/deploy-site.sh`. |
| The API | `api/app/` and `api/static/` | Deploy with `scripts/vps/deploy-api.sh` (copies both, rebuilds, restarts, verifies). |
| Host tooling | `scripts/vps/` | Deployed with `scripts/vps/sync-tooling.sh`; used by cron and systemd on the box. |
| QA records | `QA/verification/` | One dated file per piece of work: cause, fix, proof. |

Deployed locations on the box (`152.42.239.240`, release `20261108-vps`):

```
/opt/trendi/releases/20261108-vps/product/api/app/       <- the API
/opt/trendi/releases/20261108-vps/product/scripts/vps/   <- host tooling
/opt/trendi/releases/20261108-vps/website/site/          <- the served website
```

## Non-negotiables

0. **The site has a technical SEO contract, and the deploy enforces it.** Before anything is
   published, `scripts/vps/deploy-site.sh` runs `python3 scripts/seo/site_seo.py check`. It fails on
   a missing or wrong canonical, an accidental `noindex` (including a `googlebot`-only one, which
   Google obeys over `robots`), a page with no `dateModified`, a
   description over 160 characters, a broken internal link, a `robots.txt` that has stopped blocking
   training crawlers, an IndexNow key that does not match its key file, and a sitemap that disagrees
   with the pages. If it fails, fix the site; do not bypass it. The sitemap is generated, not
   hand-edited:

   ```bash
   python3 scripts/seo/site_seo.py check          # the same gate the deploy uses
   python3 scripts/seo/site_seo.py sitemap --write  # rebuild website/sitemap.xml from the pages
   ```

   After a deploy the script also pings IndexNow for the pages that changed, so Bing (and Bing-fed
   AI search) re-crawls them in hours rather than weeks. Never hand-write sitemap entries: the check
   compares it against the pages and will fail.

1. **Never edit the box and walk away.** If you fix something directly on the server, bring it back
   into this repo in the same session, with a test. `scripts/vps/verify-deploy.sh` exists to catch
   the case where you forget; the health check (`deploy:manifest`, `site:pages`) reports it too.
2. **Never publish from a directory that is not this repo.** The site deploy script refuses a dirty
   tree and stamps `.deploy-manifest.json` on the box, so any later hand edit is reported as drift.
3. **Commit before you deploy.** A deploy that cannot be traced to a commit is not a deploy.
4. **Run `scripts/vps/verify-deploy.sh` before saying "it is deployed".** Exit 0 means the repo and
   every deployed file agree. It compares by checksum, so it does not rely on anyone's memory.
5. **Every defect gets fixed, tested and documented in the same session** — cause, fix and proof in
   that date's `QA/verification/` record. Mutation-check the test once: break the fix, watch the test
   go red, restore it. A test that cannot fail is decoration.
6. **Never verify a mail fix by replaying to production.** Never send real SMS or place real calls to
   prove something works.

## Branches and pushes

`main` is the deployed branch. Push only after the full suite passes:

```bash
cd api && PYTHONPATH="$(cd .. && pwd)/QA/verification/shims" \
  TEST_DATABASE_URL=postgresql://postgres:pw@127.0.0.1:55433/postgres \
  /Users/jo/work-staging/venv-concierge/bin/python -m pytest -q
```

The interpreter, the shims path and `Pillow` are all load-bearing: the plain `python3 -m pytest -q`
this file used to give collects 101 errors without them (`QA/verification/TEST_ENV_2026-11-16.md`).

The repo is shared with other agents and an automatic checkpoint bot, so always `git pull --rebase`
before pushing, and re-run `verify-deploy.sh` afterwards in case someone else deployed in between.

## The one-command check

```bash
KEY=./Concierge ./scripts/vps/verify-deploy.sh    # repo vs box, by checksum
KEY=./Concierge ./scripts/vps/deploy-site.sh      # publish the website (refuses anything uncommitted)
KEY=./Concierge ./scripts/vps/sync-tooling.sh     # publish host tooling, then verify
```

`sync-tooling.sh` exists because a change to `scripts/vps` (including the health check) used to leave
`verify-deploy.sh` reporting `scripts/vps: DRIFT` with no supported way to clear it — the fix was a
hand-run rsync. Publish tooling changes with that script, never by hand.

If `verify-deploy.sh` reports drift, do not explain it away. Either deploy the repo state, or bring
the box state back into the repo with a commit. There is no third option.

## Agent shell environment

If every git command fails with `error: missing config key GIT_CONFIG_KEY_0`, the harness is at
fault, not this repo: its subprocess environment scrub stripped `GIT_CONFIG_KEY_n` but still
forwarded `GIT_CONFIG_COUNT` and `GIT_CONFIG_VALUE_n`, so git reads a half-written command-line
config. Fixed on 2026-11-16 in `@deepseek-ai/dsh-subprocess` (the whole `GIT_CONFIG_*` family is no
longer inherited) — see `QA/verification/HARNESS_GIT_ENV_2026-11-16.md`. Because a running harness
process keeps the old code until it restarts, prefix git with `env -u GIT_CONFIG_COUNT` in the
meantime. This never means "git is broken in this repo" and it is never a reason to skip
`verify-deploy.sh`.

## UI libraries (Jo, 2026-11-27)
Standing rule for every UI task: `~/.claude/rules_ondemand/ui-libraries.md` (five rules + library list) and
Emil Kowalski's `pick-ui-library` skill (`~/.claude/skills/pick-ui-library`, MIT). Summary: foundations
(shadcn/Base UI/Radix) restyled to Trendi purple + Plus Jakarta Sans, never default looks; Sonner toasts, Vaul
mobile drawers, cmdk Cmd-K, NumberFlow animated numbers, never hand-built; at most one standout animation per
page; free tiers only (Magic UI / Aceternity "Pro" are paid, skip).
- `website/` is static HTML: no React libs. Port the idea instead (Jo: "use the ideas and modify them for
  ourselves"): `website/ui/trendi-ui.js` + `.css` hold vanilla toast (Sonner), bottom sheet (Vaul), Cmd-K
  (cmdk, index from `scripts/seo/build_search_index.py`; rerun it after sitemap changes), number ticker
  (NumberFlow) and AI thinking/stream/approval states (Beautiful UI). Credits + licences in the file header;
  tests `api/tests/test_site_trendi_ui.py`, browser smoke `QA/verification/trendi_ui_browser_smoke.cjs`.
  One standout per page; wiring a page to it is a visible change that needs Jo's yes.
- Studio (`web/portal`, React 19 + Vite, deployed by `scripts/vps/deploy-studio.sh`) runs the Astryx design
  system (`web/portal/AGENTS.md`). Toasts go through `src/Notify.tsx` (Astryx Toast); Cmd-K is `src/CmdK.tsx`
  (Astryx Dialog + own filtering). Swapping in Sonner / cmdk / Vaul / NumberFlow, or adding shadcn + Tailwind
  beside Astryx, is a visual change that needs Jo's yes first.
