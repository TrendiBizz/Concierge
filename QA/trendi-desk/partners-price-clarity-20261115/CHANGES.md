# partners-price-clarity-20261115 (Trendi Desk) — STAGED, NOT DEPLOYED
Brief: seo/briefs/partners-referral-price-clarity-20261115.md (4 exact swaps). Base: live on-disk bytes (Range: bytes=0-) 2026-11-15 16:15 NZDT.
Rebuild: python3 build.py (refuses if any before-text count differs). Verify: sha256sum -c LIVE-BASE.sha256; sha256sum -c STAGED.sha256
Files to copy: site/partners.html -> partners.html; site/terms.html -> terms.html. dateModified NOT touched (no other edits).
Local gate on full mirror (40 URLs) + edits: PASS=20 FAIL=0 WARN=1.
