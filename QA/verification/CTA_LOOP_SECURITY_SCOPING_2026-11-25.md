# CTA loop: "Scope a security review" (2026-11-25)

**Cause:** /contact "Scope a security review" -> /penetration-testing, whose "Scope a security review" button went back to /contact. No security enquiry form or API kind existed (`site_enquiries.kind` allowed only seo, concierge). The pricing/contact "SEO enquiry" button (#start-form) was correct.

**Fix:** new `security` enquiry kind (schema CHECK, API model, operator-email label); `#scope-form` on /penetration-testing posting to /api/enquiry; contact button now `/penetration-testing#scope-form-title`; quote mailto replaced by the form. New /penetration-testing-checklist (OWASP WSTG, PTES, NIST SP 800-115 based).

**Proof:** `scripts/seo/link_audit.py` (new): 54 pages, no dead links, missing anchors or button loops; mutation-checked by restoring the old loop (it reported `LOOP? contact.html -> penetration-testing.html -> contact.html`). `test_security_review_kind_is_accepted` added. Suite 1926 passed/42 skipped; seo-gate PASS.
