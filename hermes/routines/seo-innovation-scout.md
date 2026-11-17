# Routine: Innovation scout (Trendi)

- Profile: `seo-engine`
- Schedule: `0 10 8,22 * *` Pacific/Auckland
- Source: `~/OpenBot/Shared/workwatch/routines/seo-innovation-scout.md`
- Status: active
- Approval: ideas only; never acts externally

## Procedure

Fortnightly scout for new ways to get Trendi noticed.

1. Read `~/jo-brain/AGENTS.md`, `~/OpenBot/Shared/trendi-seo/ideas.csv` (create if
   missing: `date, idea, category, source_url, effort 1-5, likely_impact 1-5, score,
   status, notes`) and the "Trendi coverage & promotion plan" in
   `~/jo-brain/bots/handover/trendi-desk.md` and `~/jo-brain/trendi/social.md`, so
   ideas are not repeated.
2. Look with free sources at:
   - search/AI answer engine changes (Google AI Overviews and AI Mode, Bing Copilot,
     ChatGPT search, Perplexity, Gemini);
   - new free directories or citation sources in global English markets;
   - new or underused schema types;
   - link-earning free-tool ideas;
   - competitor moves (describe the category, do not name brands in customer copy);
   - community/Q&A placements.
3. Every idea needs a real source URL. Never invent facts or promise rankings. Score
   effort vs impact, append to `ideas.csv`, and mark stale ones.
4. Never act externally: no sign-ups, posts, listings or emails.

## Report

The top 1–3 new ideas (why it matters, effort) asking yes/no on each. If nothing is
worthwhile, write `Status: quiet` and say nothing else.

Save to `~/.workwatch/reports/hermes/seo-engine/<date>-seo-innovation-scout.md` and
update `latest.md`.
