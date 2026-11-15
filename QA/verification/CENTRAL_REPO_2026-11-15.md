# One central repository, enforced — 2026-11-15

Asked, after three drifts surfaced in a single session: "we need a central repository ALL agents are
forced to write to so we don't have this happening."

## What was actually going wrong

The repository already existed and already tracked the website. The problem was that **the site was
also being published from a directory that was not in it**:

```
/Users/jo/work-staging/trendibizz-live/site     <- not a git repository
/Users/jo/work-staging/concierge-integration/website/   <- tracked, but older
```

Comparing the two on 2026-11-15: 36 pages identical, **16 files different, and every difference was
newer on the loose copy and live**. Production had three pages whose edits had never been committed
(`ai-visibility.html` schema rewrite, `security.html` expansion, `sample-report.html`
"worldwide" → "New Zealand"), plus the entire current CSS/JS layer (`refresh.css`, `concierge.js`,
`layout.css`, `refresh.js`, `concierge-social.css`, `concierge-start.js`), `favicon.ico`,
`indexnow-key.json`, two IndexNow verification files, `brand/` assets and `.well-known/`.

Nothing reported it, because nothing compared the repository to the loose directory, and a green
health check only says the site answers — not that it answers from committed code.

## What is enforced now

Nothing here relies on an agent remembering. Each layer fails loudly.

| Layer | Mechanism | What it stops |
|---|---|---|
| One source | `website/` in the repo is the site; the old path is now a **symlink into the repo** | editing a directory that git cannot see |
| Publish guard | `scripts/vps/deploy-site.sh` refuses a dirty tree **or untracked files** (`exit 1`) | shipping work that cannot be traced to a commit |
| Deploy stamp | the same script writes `.deploy-manifest.json` on the box: commit SHA, timestamp, sha256 per file (105 files) | not knowing what production actually is |
| Drift detector | health check `deploy:manifest` compares the deployed tree to the manifest | a fix made on the box and left there |
| Parity check | `scripts/vps/verify-deploy.sh` compares `api/app`, `scripts/vps`, `website/site` by checksum | any of the three copies diverging |
| Written rule | `AGENTS.md` at the repo root; `~/.dsh/AGENTS.md` points every session at it | the next agent not knowing |

## Proof, run live

**A hand edit on the box is caught.** Appended a comment to the deployed `index.html`:

```
counts {'ok': 43, 'warn': 1, 'fail': 1}
FAIL deploy:manifest -> 1 file(s) changed on the box: index.html
```

Re-deploying restored it and the check returned to `ok` (44 ok / 1 warn / 0 fail).

**Uncommitted work cannot be published.** Appended a comment to `website/about.html`:

```
REFUSING: /Users/jo/work-staging/concierge-integration/website has uncommitted changes.
Commit them first — production must be reproducible.
deploy-site.sh with a dirty tree exits: 1
```

**The deploy stamps and verifies.** `deploy-site.sh` from a clean tree at `fd065ea`:

```
manifest written: 105 files
verify-deploy: api/app 107 files match, scripts/vps 37 match, website/site 58 match
OK: repo and box agree
```

## Tests

`api/tests/test_deploy_manifest.py` (8): clean tree passes; changed, missing and added files are each
reported by name; an empty manifest is a problem rather than a pass; the check is wired into the
report; the deploy script refuses a dirty tree and untracked files; the deploy source defaults to the
tracked `website/` directory.

Mutation-checked, each turned red:

| Mutation | Test that failed |
|---|---|
| Remove the "added outside the repo" rule | added-file test |
| Remove the "changed on the box" rule | edited-file test |
| Replace the dirty-tree guard with `if false` | deploy-script test |

Full suite: **1,358 passed**.

## Migration steps taken

1. `rsync` from the live tree into `website/` — recovering 16 files of production-only work.
2. `/Users/jo/work-staging/trendibizz-live/site` → `site.legacy-20261115` (kept as evidence), then
   `site` → symlink to `../concierge-integration/website`.
3. `scripts/vps/deploy-site.sh` written and run; manifest stamped.
4. `AGENTS.md` written at the repo root; the workspace-level `~/.dsh/AGENTS.md` gained a
   "Central repository — binding for every agent" section pointing at it.
5. `verify-deploy.sh` extended to include `deploy-site.sh` and re-run after the deploy.

## What is still outside the repo, deliberately

- `/opt/trendi/shared/api.env` — secrets. Never commit them; the box is the source of truth and the
  deploy scripts read it there.
- `site.legacy-20261115` — kept until the next deploy is proven, then it can go.

## Open items

1. The historical drift cannot be attributed file by file — three agents and an autosave bot wrote to
   the loose directory, so the record here is "what differed", not "who changed it". The guard is
   forward-looking.
2. `website/` now holds `brand/*.png` and `favicon.ico` (binary assets, ~1 MB). Acceptable; note that
   the repo is no longer text-only.
