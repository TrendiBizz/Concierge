# Meta App Review — Screencast & Use-Case Notes (Trendi Concierge / SocialSync)

> **Status:** Ready for Jo's review and submission in the Meta App Dashboard. Every claim below describes implemented behaviour in this repository; nothing is invented.

## 1. App & Webhook Summary
- **Product:** Trendi Concierge (`https://concierge.trendibizz.com/studio`)
- **Meta App:** SocialSync (existing Meta app configured on the Trendi Concierge server)
- **Webhook Callback URL:** `https://concierge.trendibizz.com/webhooks/meta/messaging`
- **Webhook Objects Active:**
  - `page` (`messages`, `messaging_postbacks`)
  - `instagram` (`messages`, `messaging_postbacks`)
  - `whatsapp_business_account` (`messages`)
- **OAuth Redirect URI:** `https://concierge.trendibizz.com/owner/social/oauth/callback`
- **Privacy Policy:** `https://trendibizz.com/privacy` (and workspace privacy controls in Studio → Privacy)

## 2. Permissions Requested & Exact Use-Case Notes

### `pages_messaging`
- **Why Trendi Concierge needs it:** Small and medium service businesses use Trendi Concierge's unified Studio Inbox to read and reply to customer enquiries sent to their Facebook Page via Messenger, alongside website chat, texts, and email.
- **How it is used in the app:**
  1. The business owner signs in to Trendi Concierge Studio and connects their Facebook Page via Facebook Login.
  2. When a customer sends a Messenger message to that Page, Meta delivers the webhook event to Trendi Concierge (`X-Hub-Signature-256` verified) and routes it to that tenant's Studio Inbox.
  3. The business owner or editor replies from Studio → Inbox within Meta's 24-hour customer messaging window; Trendi Concierge sends the reply via the Graph API (`POST /{page-id}/messages` with `messaging_type: "RESPONSE"`). Replies outside the 24-hour window are blocked in the API and UI.

### `pages_manage_metadata`
- **Why Trendi Concierge needs it:** To subscribe each tenant-selected Facebook Page to the app's messaging webhooks upon connection (`POST /{page-id}/subscribed_apps` with `subscribed_fields=messages,messaging_postbacks`) and to unsubscribe the Page when the tenant disconnects (`DELETE /{page-id}/subscribed_apps`).
- **How it is used in the app:** Only Pages explicitly authorized by the tenant in the Facebook Login dialog are subscribed. Disconnecting the account in Studio → Social or Studio → Integrations immediately unsubscribes the Page and removes its stored encrypted token.

### `instagram_basic`
- **Why Trendi Concierge needs it:** To identify the Instagram professional (Business or Creator) account linked to the tenant's authorized Facebook Page (`/{page-id}?fields=instagram_business_account{id,username}`) so the tenant sees which Instagram handle is connected in Studio and inbound Instagram DMs route to the correct workspace.

### `instagram_manage_messages`
- **Why Trendi Concierge needs it:** To receive Instagram Direct Messages sent to the tenant's connected Instagram professional account in Studio → Inbox and let the business owner or editor send human replies back within Meta's 24-hour messaging window (`POST /{ig-id}/messages`).
- **How it is used in the app:** Inbound DMs arrive via the verified `instagram` webhook object and are matched strictly to the tenant that connected that Instagram account. Outbound replies are allowed only within 24 hours of the customer's last inbound message.

### `whatsapp_business_messaging` & `whatsapp_business_management`
- **Why Trendi Concierge needs them:** To let business owners connect their WhatsApp Business Account (WABA) and phone number via WhatsApp Embedded Signup (Facebook Login for Business) in Studio → Integrations, subscribe their WABA to the app (`POST /{waba-id}/subscribed_apps`), receive customer WhatsApp enquiries in Studio → Inbox, and reply within WhatsApp's 24-hour customer service window (or via an approved WhatsApp message template outside 24 hours if the tenant has approved templates).
- **How they are used in the app:**
  - `whatsapp_business_management`: discovers the authorized WABA and phone number IDs, subscribes/unsubscribes the WABA webhook, and reads the tenant's approved message templates (`GET /{waba-id}/message_templates?status=APPROVED`).
  - `whatsapp_business_messaging`: sends replies from Studio → Inbox (`POST /{phone-number-id}/messages`).

## 3. Screencast Scripts (Record One Short Video per Permission Group)

### Screencast A — Facebook Messenger (`pages_messaging`, `pages_manage_metadata`)
1. Open `https://concierge.trendibizz.com/studio` and sign in as a test business owner.
2. Go to **Social**, click **Connect** on Facebook, complete the Facebook Login consent dialog selecting the test Facebook Page, and return to Studio showing the Page connected.
3. Open **Integrations** → **Meta Messaging** and show the connected Page listed with **Webhook active**.
4. From a separate Facebook test account, send a Messenger message to the test Page (e.g. "Hi, do you have availability next week?").
5. In Studio → **Inbox** (filter **Messenger**), show the incoming message appearing in the conversation list and thread, with **24h reply window open**.
6. Type a reply in the Inbox composer and send it; switch back to Messenger to show the reply delivered.
7. Optionally demonstrate **Disconnect** in Studio → Social / Integrations to show the channel removed and unsubscribed.

### Screencast B — Instagram DMs (`instagram_basic`, `instagram_manage_messages`)
1. In Studio → **Social**, click **Connect** on Instagram, complete Facebook Login selecting the Facebook Page linked to the test Instagram Business account.
2. Open **Integrations** → **Meta Messaging** to show the Instagram Business handle listed with **Webhook active**.
3. From a test Instagram account, send a DM to the connected Instagram Business account.
4. In Studio → **Inbox** (filter **Instagram**), open the thread, show the incoming DM and **24h reply window open**, and send a reply.
5. Switch back to Instagram to show the reply received.

### Screencast C — WhatsApp Business (`whatsapp_business_messaging`, `whatsapp_business_management`)
1. In Studio → **Integrations** → **Meta Messaging**, click **Connect WhatsApp Business** to launch Facebook Login for Business (WhatsApp Embedded Signup).
2. Complete the Embedded Signup flow selecting the test WABA and phone number; return to Studio showing the WhatsApp number connected with **Webhook active**.
3. Send a WhatsApp message to the connected business number from a test phone.
4. In Studio → **Inbox** (filter **WhatsApp**), open the thread showing the incoming message and **24h reply window open**, and send a reply.
5. Show the reply arriving in WhatsApp on the test phone.

## 4. Security & Data Handling Facts for Reviewers
- All Meta webhook POST requests are verified with `X-Hub-Signature-256` (HMAC-SHA256 using the Meta App Secret) before any database write.
- All per-tenant Page, Instagram, and WhatsApp access tokens are encrypted at rest using AES-256-GCM with tenant- and channel-bound additional authenticated data (`aad`).
- Each tenant can only read and reply to conversations belonging to their own connected Page/IG/WhatsApp IDs (enforced by tenant-scoped queries and PostgreSQL Row-Level Security).
- Disconnecting a channel unsubscribes webhooks (`DELETE /{page-id}/subscribed_apps` or `DELETE /{waba-id}/subscribed_apps`) and deletes the stored encrypted token immediately.
