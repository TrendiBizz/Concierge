# Concierge portal workflow checkpoint
Objective: complete all seven requirements in HANDOFF_CONCIERGE_PORTAL_WORKFLOW_2026-11-09.md.
Authorization: implement, test, commit, push and deploy; no new purchases or test messages. No agents. Preserve unrelated assets and secrets.
Workspace: /Users/jo/work-staging/concierge-integration, integration/concierge-v1.
Milestone: owner notification phone stored on tenant, validated as international E.164, exposed in owner onboarding, excluded from cloning. Generic owner alerts queue SMS only with sms_enabled and sms_send authorization; existing device confirmation remains in transport.
Verification: 129 API tests passed; git diff --check passed. No external messages sent. These changes have not been deployed or verified as received.
Remaining: wire voice completion to owner SMS and recording links; trace portal text/email and explicit enquirer acknowledgements; website import; external calendar availability/event/invite; CRM Quotations; tenant isolation/retry acceptance; deployment with rollback and actual authorized integration verification.
Next action: update voice_records._finish_enquiry transactionally with owner recording link/SMS, then verify channel paths. Existing authoritative scope and production connection details are in the handoff.
