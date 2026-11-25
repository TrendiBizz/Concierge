# CTA loop: "Scope a security review" (2026-11-25)

**Cause:** /contact "Scope a security review" -> /penetration-testing, whose "Scope a security review" button went back to /contact. No security enquiry form or API kind existed (`site_enquiries.kind` allowed only seo, concierge). The pricing/contact "SEO enquiry" button (#start-form) was correct.

**Fix:** new `security` enquiry kind (schema CHECK, API model, operator-email label); `#scope-form` on /penetration-testing posting to /api/enquiry; contact button now `/penetration-testing#scope-form-title`; quote mailto replaced by the form. New /penetration-testing-checklist (OWASP WSTG, PTES, NIST SP 800-115 based).

**Proof:** `scripts/seo/link_audit.py` (new): 54 pages, no dead links, missing anchors or button loops; mutation-checked by restoring the old loop (it reported `LOOP? contact.html -> penetration-testing.html -> contact.html`). `test_security_review_kind_is_accepted` added. Suite 1926 passed/42 skipped; seo-gate PASS.

## Addendum: CREST section and deploy gate
- /penetration-testing-checklist section 9 adds CREST CDPT v5.2 (2023) and *A Guide to Penetration Testing* (2022), read from the primary PDFs. CREST publishes no test checklist (CDPT: "does not define a methodology"); the checklist stays on OWASP WSTG. Site states Trendi does NOT claim CREST accreditation; the section is a yardstick for judging any provider.
- `scripts/seo/link_audit.py` now runs in `scripts/vps/deploy-site.sh` right after `site_seo.py check`; nonzero exit blocks the deploy. Proof: runs clean on 54 pages (`no problems`), mutation-checked earlier by restoring the old loop.
