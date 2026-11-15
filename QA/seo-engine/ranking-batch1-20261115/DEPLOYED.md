# Ranking batch 1: deployed 15 Nov 2026 (Omega Boss)

- 16:00 NZDT: apply-on-vps.sh (sha256 e7c59753...8082) applied on 152.42.239.240. 18 HTML files written; seo-gate PASS=21 FAIL=0 WARN=0; served check 18/18. Backup: /opt/trendi/backups/ranking-batch1-20261115.
- 16:01 NZDT: apply-routing-301-on-vps.sh (5ac884bf...8c81) aborted safely at "insert failed" (exit 4, website.mjs untouched): gawk on the VPS turns `\/` in `awk -v a=...` into `/`, so the anchor never matched (the local test used mawk). Failed run's backup dir renamed to routing-301-20261115-attempt1-awkfail.
- 16:03 NZDT: apply-routing-301-on-vps.v2.sh (sha256 b6ecd340...b46f; only change: ANCHOR passed via ENVIRON) applied. 30/30 probes OK; seo-gate PASS=21/0/0. Live website.mjs a23b8d78... (before 350567e9...). Backup: /opt/trendi/backups/routing-301-20261115.
- Cloudflare cache purged (purge_everything) after each script.
- Note: live website.mjs differs from this repo's scripts/vps/website.mjs outside the 301 block (before-sha 350567e9 vs repo base de9b3ed2); not reconciled here.
- Note: repo website/*.html formatting differs from the live bytes; live is the source of truth for these 18 files.
