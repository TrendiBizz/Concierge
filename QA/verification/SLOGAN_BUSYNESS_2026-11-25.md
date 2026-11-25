# Slogan change 2026-11-25
Cause: Jo asked hero slogan -> "More business. Less busyness." (same two-line layout, italic purple second word).
Fix: website/index.html h1 `<em>busywork.</em>` -> `<em>busyness.</em>`; site-i18n.json key "busywork." -> "busyness." (all languages; existing translations kept, native-speaker review pending).
Proof: seo-gate PASS, site_seo check OK 54 pages, suite 1926 passed/42 skipped, grep busywork in website/ = 0.
