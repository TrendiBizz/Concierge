# Working agreement — Trendi Concierge

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
| The API | `api/app/` | Deploy with `rsync api/app/` + `scripts/vps/redeploy-api.sh`. |
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
cd api && TEST_DATABASE_URL=postgresql://postgres:pw@127.0.0.1:55433/postgres python3 -m pytest -q
```

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
