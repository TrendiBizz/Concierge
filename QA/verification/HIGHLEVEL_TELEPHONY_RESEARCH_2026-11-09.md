# HighLevel telephony research — 9 November 2026

Scope: official HighLevel documentation only. Research findings, not an implementation or proof that Trendi's existing voice service works. No account changes or purchases made.

## Established facts

- **HighLevel integrates the carrier service into its product.** LC Phone removes the need for an agency or sub-account to connect a separate third-party telephony account to send/receive calls and SMS. This explains the simpler customer experience; telecom provisioning still exists behind the interface. [LC Phone overview and migration](https://help.gohighlevel.com/support/solutions/articles/48001204027-how-do-i-migrate-my-agency-and-sub-account-over-to-lc-phone-)
- **Existing numbers can reach its AI through forwarding.** HighLevel documents forwarding an existing cell/landline number to a HighLevel number, with Voice AI answering there. Existing-number preservation does not mean the AI directly controls the customer's smartphone. Avoid routing the HighLevel number back to the same forwarding number, which creates a loop. [Call forwarding guide](https://help.gohighlevel.com/support/solutions/articles/155000004201-call-forwarding-to-your-highlevel-phone-number)
- **Verified existing caller ID is an outbound feature.** HighLevel's 9 April 2026 announcement lets users verify ownership and make outbound calls displaying their existing number without buying a HighLevel number. It explicitly leaves inbound calls ringing on the existing phone. This feature alone does not deliver inbound AI answering or SMS integration. [Official announcement](https://ideas.gohighlevel.com/changelog/make-voice-calls-without-buying-a-phone-number-using-your-existing-phone-number)
- **Phone service has ongoing costs.** LC Phone bills for number rental and usage; country, number type, destination and messaging requirements affect the costs. Integrated setup does not remove these costs. [Pricing and billing guide](https://help.gohighlevel.com/support/solutions/articles/48001223556-lc-phone-pricing-billing-guide)

## Hosted SMS: important correction and limits

Porting is **not always required** to bring existing-number SMS into HighLevel. Its Number Hosting service can route supported messaging through LC Phone while voice stays with the original carrier. The official guide, updated 30 October 2026, specifies:

- Labs self-service: eligible **US local and toll-free numbers**, SMS only; agency owner/admin initiates the request.
- Support-assisted: eligible **US and Canadian** numbers, with supported SMS/MMS capabilities checked individually.
- **Mobile/cellular numbers are not supported. Numbers outside the US/Canada are not supported** by this workflow. A number already using SMS elsewhere is not eligible as currently configured; Support must confirm the next step.
- Ownership verification, authorization and carrier review are required. Labs includes a verification call, US physical service address and electronic authorization. Confirm SMS Ready and applicable messaging registration before use.

Consequently, this documented workflow cannot host the owner's existing **New Zealand Spark mobile number**. It is not evidence of a universal smartphone SMS connection. [Official Number Hosting eligibility and setup guide](https://help.gohighlevel.com/support/solutions/articles/48001230556-enable-your-landline-for-text-messages-in-highlevel)

## Recommendation for Trendi — design judgment, not a verified deployment

Copy HighLevel's **managed customer experience**: provide one Trendi setup flow that provisions an eligible business number, connects AI answering and messaging, and displays clear readiness checks. Keep carrier accounts, routing and agent infrastructure behind Trendi's interface. Let customers preserve their public voice number through supported carrier forwarding; offer porting where eligible. Treat existing-number messaging as a separate capability check rather than promising it works on every smartphone or country.

For the present Spark mobile, the next practical voice milestone is a managed inbound destination with working AI answering, followed by forwarding and a real external-call test. The reviewed HighLevel documents do not establish Spark-specific forwarding instructions or eligible NZ number/SMS supply. Those require separate provider verification. A Mac/iPhone automation bridge is not equivalent to this managed service.

Do not label customer telephony ready until external inbound call, AI response, human fallback, caller summary, and applicable inbound/outbound SMS tests pass. Worldwide coverage, local-number availability and country-specific onboarding should remain explicit availability checks.
