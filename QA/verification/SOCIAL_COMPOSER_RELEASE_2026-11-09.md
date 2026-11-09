# Social composer release — 9 November 2026 (Auckland)

Deployment host: 152.42.239.240; release tree remains `/opt/trendi/releases/20261108-vps`.

## Implemented

Shared brief and single media upload; separately editable platform variants; tenant-owned bounded uploads; image normalization to padded square JPEG; H.264/AAC video normalization with measured output dimensions; Google Business video poster; encrypted expiring media capability URLs; revision/media/options-bound approval and scheduling. LinkedIn member/company media adapters and TikTok native video/status support are included. Legacy network history remains; Mastodon/Bluesky removed from destination choices/public offer and Mastodon publishing registration removed.

Facebook/TikTok pending receipts stay Processing until provider reconciliation. Asset loading/signing/vault errors fail the individual claimed post instead of abandoning the batch. Media tools have a 120-second deadline with forced termination after five seconds. TikTok requires server-inspected uploads, current creator settings, music consent and branded-content consent; URL-only TikTok publishing is rejected because client duration is untrusted. Publishing remains disabled; no real social posts were sent.

## Evidence

- 68 Rust tests passed, including native ffmpeg image/video/poster processing, normalized dimensions, tenant isolation and signed download tampering. The scheduler regression verifies a missing owned asset fails only that job while another approved job completes.
- 73 Python tests passed in candidate image with production secret environment excluded from unit-test settings. An earlier run inherited ADMIN_TOKEN and caused two configuration-dependent failures; clean test configuration passed all tests.
- Python compilation; extracted inline owner JavaScript syntax; git diff whitespace checks passed.
- Isolated social SQLite copy: four accounts preserved; image and video uploads, compose, edited drafts, submission, approval and scheduling passed. Candidate publishing disabled.
- Isolated PostgreSQL copy/API on 8002: owner session authentication, four accounts, compose bridge and disabled publishing passed. Candidate outbox and CRM bridge disabled.
- Fresh encrypted backup and isolated restore passed: 23 Concierge and 121 CRM tables, SQLite integrity, social media directory, uploads and settings. No production volume replacement or database migration/reset.
- Public owner portal, website and CRM health respond 200. Invalid public media capability responds 404 without requiring owner login.
- Live website retains “Your office, handled.”, USD 400/month and USD 4,080/year; Mastodon and Bluesky removed. Actual checkout billing has not been verified in this session.
- Browser login confirmed four preserved connected accounts. A browser cosmetic filter hid the old social-text/social-link IDs; renaming these fields restored visibility.

## External gates / unverified activation

- LinkedIn: developer portal directly confirmed Share on LinkedIn and OpenID Connect provisioned. Community Management request is blocked: LinkedIn requires it to be the ONLY product on an app. A separate Community Management app, company verification, grants and customer consent are required for company Pages. Existing member app/account retained.
- TikTok: Content Posting API approval, video.publish consent, app audit/visibility restrictions and approved real-video delivery remain unverified. Login Kit linking is not publishing approval.
- Google Business Profile: OAuth branding/client and Business Profile entitlement/approval remain unfinished/unverified. Temporary kiwi18@gmail.com support address must still be replaced with eligible support@trendibizz.com and verified on consent branding.
- Meta: customer-wide app review/permission approval and real Instagram/Facebook publishing remain unverified. Existing Facebook and Instagram account records preserved.
- Real provider publishing requires explicit approved content/destination and provider activation. Do not replay old/uncertain jobs when enabling it.

Phone/SMS provider activation and mailbox forwarding are separate pending work. No live provider success is claimed by this release.

## Live browser acceptance

Jo supplied the owner login form. Verified four connected accounts, visible composer fields after cosmetic-filter fix, Facebook and LinkedIn destination selection, live AI adaptations with distinct text, editable Facebook preview, and saving two explicit “do not publish” verification drafts. These two drafts remain unapproved and unscheduled; customer connections unchanged. Automated browser file selection is blocked by the ChatGPT extension's disabled file URL permission; native app inspection timed out. This is an automation limitation, not a demonstrated product upload failure. Upload and normalization were exercised through the isolated candidate API and Rust native pipeline. Saved preview fields are locked so later visual edits cannot misrepresent the stored approval version. Upload transport timeout now accommodates the bounded media process.

## Final release identifiers

Product implementation pushed as `908ca02` on `integration/concierge-v1`; website pushed as `8ad8b65` on `concierge-site`. Final amd64 production images: API `eef74ce882be`, social `0b564a9f8c6a`. Original API/social images retained under `:pre-composer`. Isolated candidate containers stopped after testing; their copied data is retained separately under `/opt/trendi/candidate-social`. Production services healthy following final image recreation. Two live browser verification drafts remain unapproved/unscheduled.
