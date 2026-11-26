# 2026-11-27 — real chat test conversation, figures restored

Cause: figure was removed from index.html and concierge.html because the old screenshot quoted stale USD 250 (agent prompt fix in fe355f7, shipped to box 70452d9).
Test: headless Chrome drove the live widget on https://trendibizz.com/concierge (opened launcher, typed "How much does Concierge cost?", waited for reply). No SMS, calls or payments.
Reply (real, unedited): "USD $199 a month, 3-month minimum, then month to month — all setup, your own number, voice answering, SMS/email confirmations, voicemail, CRM, integrations and social posting included. Prices are in USD, with 15% GST included for NZ customers." Pricing card: "USD $199/month. 3-month minimum."
Fix: new brand/screenshots/concierge-test-conversation.webp (760x1800, panel enlarged to 900px tall only so the whole exchange fits); figure + caption "captured 27 November 2026. Test data only." restored in index.html and in concierge.html #test-conversation.
Proof: site_seo check OK, seo-gate PASS 22/0.
