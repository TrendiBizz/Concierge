# Marketing skills library (Trendi's own use)

Third-party marketing skills vendored for Trendi's own use (trendibizz.com SEO and AI visibility). They are
**reference playbooks an AI assistant reads**, not code. This directory contains markdown only: every script, hook, installer,
eval fixture and HTML template was removed on import, and nothing here runs, fetches, posts or spends.

## How to use them

No runtime or scheduler is involved. In Claude Code (or any assistant working in this repo), name the task and the
skill, for example: "Use `marketing/skills/seo-geo/SKILL.md` to audit `website/ai-seo-services.html` and write a
brief". Each skill points to its own `references/` files. Skills are deliberately **not** placed in `.claude/skills/`,
so they do not load into every session on this repo; copy or symlink one there only if you want it always on.

## Provenance (pinned; all MIT)

| Source | Commit | Skills taken |
|---|---|---|
| [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills) | `7ae95403e88a` | ai-seo, seo-audit, schema, programmatic-seo, site-architecture, content-strategy, copywriting, copy-editing, competitor-profiling, free-tools, link-building, lead-magnets, cro, product-marketing, public-relations |
| [AgriciDaniel/claude-seo](https://github.com/AgriciDaniel/claude-seo) | `468ed5b0d9e3` | seo-geo, seo-technical, seo-schema, seo-content, seo-sxo, seo-cluster, seo-content-brief, seo-local, seo-competitor-pages |
| [petergyang/no-ai-slop](https://github.com/petergyang/no-ai-slop) | `000650b15698` | no-ai-slop |

Licences are in `_licenses/`. To update a skill, re-vendor from the pinned repo, diff it, strip anything executable,
and bump the commit above. Do not run the upstream installers or point an assistant at the upstream repos directly.

## Trendi rules override every skill

Where a skill disagrees with these, these win (they match Trendi's existing SEO and copy rules):

- Free sources first. Paid tools named in a skill (DataForSEO, SE Ranking, Ahrefs, Profound, Semrush and similar)
  are not used. The only paid call is the existing DataForSEO weekly cap of $0.08. Skills that say "if the MCP tool is
  available" are skipped: report the item as `not measured`.
- Scripts that the claude-seo skills mention (`scripts/fetch_page.py`, drift baselines and the like) are not vendored.
  Use the existing `trendi-seo` toolchain (`audits/`, `monitor/`) and `scripts/seo/` instead.
- `seo-cluster` mentions an HTML cluster-map template that is not vendored. Produce the map as a markdown table.
- Competitor names and the "free" word are fine in internal briefs and reports (`competitor-profiling`, `free-tools`).
  They stay out of customer-facing copy, as Trendi's copy rules require.
- Never promise a ranking or a mention. Cite a real source URL for every factual claim. Never invent numbers.
- Drafts and briefs only. Nothing is published, sent, posted or deployed without Jo's yes; site changes go through
  the `trendi-site` gate.

## Which job uses what

| Task | Skills |
|---|---|
| Weekly and monthly SEO audits | seo-audit, seo-technical, seo-schema, schema, ai-seo, seo-geo, site-architecture |
| Site copy briefs | seo-content-brief, seo-content, seo-sxo, seo-cluster, programmatic-seo, content-strategy, copywriting, cro |
| New-page ideas, AI-visibility offer | seo-geo, ai-seo, free-tools, lead-magnets, competitor-profiling, seo-competitor-pages, seo-local |
| Authority and links (briefs only, no outreach sent) | link-building, public-relations |
| Every draft before Jo sees it | copy-editing, then no-ai-slop |
| Positioning questions | product-marketing |

## AI-search checklist

`scripts/seo/ai_checklist.py` scores the site's HTML pages against the automatable items of an AI-search readiness
checklist (answer-first structure, question headings, FAQ and schema, dates and freshness, evidence, media,
entities). Items that need judgement are listed as `manual`, never scored. It is read-only, makes no network calls and
is meant for the monthly audit: run it, compare with last month's report, and turn gaps into briefs. See the
script's docstring.

## Not imported, and why

| Source | Decision |
|---|---|
| mvanhorn/last30days-skill | Not vendored. Useful for a trend scan, but it ships an engine that reads browser cookies (`chrome_cookies.py`) and wants paid scraper keys. Run it only in an isolated container with no browser profile, never on a machine with a logged-in browser. |
| rdoser13/free-claude-skills | Overlaps what is vendored (anti-slop, seo-content-strategy, cro-audit, keyword-research). Nothing unique enough to add. |
| alirezarezvani/claude-skills | About 495 skills, mostly engineering, finance and compliance. Its marketing folder overlaps marketingskills. Not marketing-specific enough to vendor. |
| irinabuht12-oss/marketing-skills | Mostly paid-ads audits (Google, Meta, LinkedIn, Reddit); Trendi runs no paid ads. The AI-visibility items overlap `ai-seo` and `seo-geo`. |
| ericosiu/ai-marketing-skills | Depends on paid tools (Ahrefs, Instantly, Apollo) and cold outbound, which conflicts with Trendi's no-unsolicited-send rule. |
| aaron-he-zhu/aaron-marketing-skills | 120 skills built around a shared registry and memory protocol, which needs its own runtime. Too heavy for the same coverage. |
