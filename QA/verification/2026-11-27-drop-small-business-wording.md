# 2026-11-27 — drop "small business" wording (Jo)

Cause: product is for any business; site copy, titles, JSON-LD, llms.txt, page generator and owner-ask prompt said "small business".
Fix: "for small business(es)" -> "for any business"; other uses -> "business(es)". Edited website/*.html, llms.txt, scripts/seo/make_page.py (generator, so regenerated pages stay in sync), outreach kit text, api/app/owner_ask.py prompt. Removed 57 stale translated i18n entries keyed on the old English (pages fall back to English until retranslated).
Left alone: geo-daily.py search query (a tracked query, not our copy); binary media (concierge-explainer.mp4, trendi-intro.mp4, concierge-setup-request.webp) may still say it.
Proof: site_seo check OK (54 pages), seo-gate PASS 22/0, pytest 1928 passed/42 skipped, grep of website/*.html finds no "small business".
