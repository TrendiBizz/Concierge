# Meta review packet — 9 November 2026

Status: draft, not submitted. The screenshot/receipt evidence proves real posts; a continuous portal recording covering OAuth, previews and exact approval is still required. No authentication credentials are included here.

## Reviewer navigation

1. Open https://concierge.trendibizz.com/owner-ui and sign in using the dedicated review Business ID, email and password below. This is an isolated workspace with no customer data. No payment is required.
2. Open Permissions and authorize the social capability for the review workspace, then open Social accounts and drafts.
3. Choose Connect Facebook Pages or Connect Instagram. Facebook Login is used to authorize access to the Pages you administer and the professional Instagram account linked to the selected Page. Use your own test Page and professional Instagram account; no personal-profile posting is supported. Grant the requested permissions and return to Concierge.
4. Confirm the correct Page or Instagram identity is listed. Enter Post text, choose one destination, and upload a photo. Instagram publishing requires an image. Choose Prepare platform previews and inspect/edit the exact destination, caption and media. Save the draft.
5. Approve the exact saved version and schedule it for now or a future time. A restricted worker delivers only explicitly approved Facebook/Instagram jobs in this isolated review workspace, usually within 20 seconds. Refresh social drafts to view processing and published/failed status. Never approve a post you do not want sent to the selected test account. Editing invalidates the old approval.
6. Verify the published post in the selected Page or Instagram account. You can disconnect the linked account from Concierge. Disconnecting revokes future access; it does not delete previously published posts.
Meta API use: pages_show_list lists administered Pages; pages_read_engagement reads selected Page identity/context; pages_manage_posts publishes approved Page posts; business_management discovers managed business assets needed to resolve the selected Page/Instagram relationship; instagram_basic reads the connected professional account identity; instagram_content_publish creates/publishes approved Instagram media. Tokens are encrypted and workspace-scoped.

## Permission explanations

### instagram_content_publish

Trendi Concierge lets the owner of an Instagram professional account connected to a Facebook Page upload a photo, write a caption, review the exact destination, media and caption, then explicitly approve and schedule publication. instagram_content_publish is required to create the media container and publish the approved organic feed post to that selected professional account. Drafts are not published without owner approval; editing invalidates approval. The service tracks the provider result and shows published or failed status in that same workspace. Tokens are encrypted and scoped to that customer. We do not use this permission to publish to personal accounts or to send unsolicited content.

### instagram_basic

Trendi Concierge uses instagram_basic to identify the Instagram professional account associated with the Facebook Page selected by its administrator. It reads the account ID and username so the customer can verify the destination before composing or approving content. This is necessary to prevent a post being directed to the wrong business identity and to connect the account to the correct customer workspace. It is used with instagram_content_publish for owner-approved organic content; no personal Instagram password is collected or stored.

### business_management

Trendi Concierge uses business_management during customer-initiated Facebook Login to discover Pages owned or managed through the business portfolios to which the authenticated administrator already has access. This resolves eligible business-managed Pages and their connected Instagram professional identities when the normal administered-Page listing is incomplete. The owner selects the destination to connect; the service verifies actual granted business and asset access and stores tokens encrypted within that workspace. This is necessary to support customers whose Page is managed through a business portfolio. It is not used to create businesses, alter ownership, manage advertisements, or access unrelated assets.

### pages_read_engagement

Trendi Concierge uses pages_read_engagement to read basic identity and publishing context of the Facebook Page selected by its administrator and resolve its connected Instagram professional account where applicable. This lets the customer see and verify the correct business destination before approving a post and lets the service validate Page context for publishing. We do not provide an audience-profiling, engagement-analytics or messaging product through this permission. Access is limited to the selected managed assets and customer workspace; tokens are encrypted.

### pages_show_list

Trendi Concierge uses pages_show_list after the customer initiates Facebook Login to list the Facebook Pages the authenticated person administers. The customer chooses which Page to connect and sees its identity in the composer before any post is approved. This permission is necessary to discover eligible destinations and obtain the Page-scoped access needed for owner-approved publishing and the linked professional Instagram identity. The service verifies the actual permissions granted, keeps connections scoped to the customer workspace, and does not publish to unselected Pages.

## Final evidence gate

The first login clip is 15 seconds. The later 09.11.03.mov records chat for most of the 230-second run and only brief portal views; do not claim it covers preview/approval. Preserve it privately. User approved all five allowed-usage agreements; saved checked states were verified in the Meta UI. The existing pages_manage_posts form needs its uploaded recording checked/replaced with adequate genuine evidence.
