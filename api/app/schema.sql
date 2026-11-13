CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS tenants (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug              text UNIQUE NOT NULL,
    name              text NOT NULL,
    public_key        text UNIQUE NOT NULL,
    site_url          text,
    allowed_origins   text[] NOT NULL DEFAULT '{}',
    persona           text NOT NULL DEFAULT '',
    greeting          text NOT NULL DEFAULT '',
    cta_text          text NOT NULL DEFAULT 'Need a quick answer? Click here',
    accent_color      text NOT NULL DEFAULT '#2563eb',
    voice             text NOT NULL DEFAULT 'eve',
    voice_enabled     boolean NOT NULL DEFAULT false,
    voice_daily_limit integer NOT NULL DEFAULT 200,
    booking_url       text,
    lead_webhook_url  text,
    incentive         text NOT NULL DEFAULT '',
    demo_questions    jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id         bigserial PRIMARY KEY,
    tenant_id  uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    url        text NOT NULL,
    title      text NOT NULL DEFAULT '',
    content    text NOT NULL,
    embedding  vector(__DIM__) NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_tenant_idx ON chunks (tenant_id);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS conversations (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id  text NOT NULL,
    channel     text NOT NULL DEFAULT 'chat',
    page_url    text,
    utm         jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, session_id, channel)
);

CREATE TABLE IF NOT EXISTS messages (
    id               bigserial PRIMARY KEY,
    conversation_id  uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role             text NOT NULL,
    content          text NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_conv_idx ON messages (conversation_id, id);

CREATE TABLE IF NOT EXISTS leads (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_id  uuid REFERENCES conversations(id) ON DELETE SET NULL,
    name             text NOT NULL DEFAULT '',
    company          text NOT NULL DEFAULT '',
    email            text NOT NULL DEFAULT '',
    phone            text NOT NULL DEFAULT '',
    message          text NOT NULL DEFAULT '',
    channel          text NOT NULL DEFAULT 'chat',
    page_url         text,
    utm              jsonb NOT NULL DEFAULT '{}'::jsonb,
    webhook_status   text NOT NULL DEFAULT 'none',
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS leads_tenant_idx ON leads (tenant_id, created_at DESC);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS source_key text;
CREATE UNIQUE INDEX IF NOT EXISTS leads_channel_source_idx
ON leads(tenant_id, channel, source_key) WHERE source_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS voice_tokens (
    id         bigserial PRIMARY KEY,
    tenant_id  uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    minted_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS voice_tokens_idx ON voice_tokens (tenant_id, minted_at DESC);

-- ===================================================================
-- Phase 2 additions (idempotent): booking, automation, SMS/email, CRM
-- ===================================================================
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS timezone text NOT NULL DEFAULT 'Pacific/Auckland';
-- A new client is a New Zealand business until somebody tells us otherwise: a US default made every
-- booking, reminder and business-hours calculation wrong for a customer who never noticed the setting.
ALTER TABLE tenants ALTER COLUMN timezone SET DEFAULT 'Pacific/Auckland';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS business_hours jsonb NOT NULL DEFAULT
    '{"mon":[["09:00","17:00"]],"tue":[["09:00","17:00"]],"wed":[["09:00","17:00"]],"thu":[["09:00","17:00"]],"fri":[["09:00","17:00"]],"sat":[],"sun":[]}'::jsonb;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS slot_minutes integer NOT NULL DEFAULT 30;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS min_notice_hours integer NOT NULL DEFAULT 2;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS max_days_ahead integer NOT NULL DEFAULT 30;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS native_booking boolean NOT NULL DEFAULT false;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS notify_email text;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS sms_enabled boolean NOT NULL DEFAULT false;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS sms_from text;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS lead_sms_template text NOT NULL DEFAULT '';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS review_url text;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS lead_value_cents integer NOT NULL DEFAULT 0;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS report_token text;
CREATE UNIQUE INDEX IF NOT EXISTS tenants_report_token_idx ON tenants (report_token);

ALTER TABLE leads ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'new';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS notes text NOT NULL DEFAULT '';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS value_cents integer NOT NULL DEFAULT 0;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS consent_contact boolean NOT NULL DEFAULT false;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

ALTER TABLE conversations ADD COLUMN IF NOT EXISTS pending_booking jsonb;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS flag text;

CREATE TABLE IF NOT EXISTS appointments (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    lead_id          uuid REFERENCES leads(id) ON DELETE SET NULL,
    conversation_id  uuid REFERENCES conversations(id) ON DELETE SET NULL,
    starts_at        timestamptz NOT NULL,
    ends_at          timestamptz NOT NULL,
    name             text NOT NULL DEFAULT '',
    phone            text NOT NULL DEFAULT '',
    email            text NOT NULL DEFAULT '',
    notes            text NOT NULL DEFAULT '',
    status           text NOT NULL DEFAULT 'booked',
    consent_contact  boolean NOT NULL DEFAULT false,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS appointments_tenant_idx ON appointments (tenant_id, starts_at);

CREATE TABLE IF NOT EXISTS outbox (
    id              bigserial PRIMARY KEY,
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    kind            text NOT NULL,
    channel         text NOT NULL,
    to_addr         text NOT NULL,
    subject         text NOT NULL DEFAULT '',
    body            text NOT NULL,
    send_at         timestamptz NOT NULL DEFAULT now(),
    status          text NOT NULL DEFAULT 'pending',
    attempts        integer NOT NULL DEFAULT 0,
    last_error      text NOT NULL DEFAULT '',
    dedupe_key      text,
    appointment_id  uuid REFERENCES appointments(id) ON DELETE CASCADE,
    lead_id         uuid REFERENCES leads(id) ON DELETE SET NULL,
    claimed_at      timestamptz,
    sent_at         timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS outbox_dedupe_idx ON outbox (dedupe_key) WHERE dedupe_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS outbox_due_idx ON outbox (status, send_at);

-- A customer's own phone can remain with its existing carrier. Devices poll out
-- over HTTPS; no inbound port, owner password or global administration key.
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS sms_transport text NOT NULL DEFAULT '';
CREATE TABLE IF NOT EXISTS sms_devices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    from_number text NOT NULL,
    enabled boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen timestamptz,
    verified_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS sms_one_device_idx ON sms_devices(tenant_id) WHERE enabled;
ALTER TABLE sms_devices ADD COLUMN IF NOT EXISTS inbound_verified_at timestamptz;
CREATE TABLE IF NOT EXISTS device_sms_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    device_id uuid NOT NULL REFERENCES sms_devices(id),
    outbox_id bigint REFERENCES outbox(id),
    request_key text NOT NULL,
    recipient text NOT NULL,
    body text NOT NULL,
    status text NOT NULL DEFAULT 'queued',
    created_at timestamptz NOT NULL DEFAULT now(),
    claimed_at timestamptz,
    finished_at timestamptz,
    receipt text NOT NULL DEFAULT '',
    operational boolean NOT NULL DEFAULT false,
    UNIQUE(tenant_id,request_key)
);
CREATE TABLE IF NOT EXISTS device_sms_inbound (
    device_id uuid NOT NULL REFERENCES sms_devices(id),
    message_id text NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(device_id,message_id)
);

CREATE TABLE IF NOT EXISTS opt_outs (
    tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    contact     text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, contact)
);

-- Lead scoring (rule-based, see app/scoring.py)
ALTER TABLE leads ADD COLUMN IF NOT EXISTS score integer NOT NULL DEFAULT 0;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS score_label text NOT NULL DEFAULT 'cold';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS score_reasons jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS scored_at timestamptz;
CREATE INDEX IF NOT EXISTS leads_score_idx ON leads (tenant_id, score DESC);

-- Reactivation campaigns (see app/campaigns.py). Marketing consent is separate from consent_contact.
ALTER TABLE leads ADD COLUMN IF NOT EXISTS consent_marketing boolean NOT NULL DEFAULT false;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS consent_marketing_basis text NOT NULL DEFAULT '';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS consent_marketing_at timestamptz;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS campaigns_enabled boolean NOT NULL DEFAULT false;
-- Owner's own switch: stop Concierge answering or sending for this business. Distinct from the
-- operator kill switch (settings.outbound_paused), which is deployment-wide.
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS paused_at timestamptz;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS paused_by text;

CREATE TABLE IF NOT EXISTS campaigns (
    id              bigserial PRIMARY KEY,
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name            text NOT NULL,
    channel         text NOT NULL CHECK (channel IN ('sms', 'email')),
    subject         text NOT NULL DEFAULT '',
    body            text NOT NULL,
    filters         jsonb NOT NULL DEFAULT '{}'::jsonb,
    status          text NOT NULL DEFAULT 'draft',
    recipient_count integer NOT NULL DEFAULT 0,
    created_at      timestamptz NOT NULL DEFAULT now(),
    queued_at       timestamptz
);
CREATE INDEX IF NOT EXISTS campaigns_tenant_idx ON campaigns (tenant_id, created_at DESC);
ALTER TABLE outbox ADD COLUMN IF NOT EXISTS campaign_id bigint REFERENCES campaigns(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS outbox_campaign_idx ON outbox (campaign_id) WHERE campaign_id IS NOT NULL;

-- Per-client scoring weights and response-time alerts (see app/scoring.py, app/sla.py)
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS scoring jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS sla_minutes integer NOT NULL DEFAULT 0;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS sla_min_score integer NOT NULL DEFAULT 70;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS sla_alerted_at timestamptz;

-- To-dos, sales pipeline and calendar feed (see app/tasks.py, app/sales.py, app/ical.py)
CREATE TABLE IF NOT EXISTS tasks (
    id            bigserial PRIMARY KEY,
    tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    lead_id       uuid REFERENCES leads(id) ON DELETE SET NULL,
    title         text NOT NULL,
    notes         text NOT NULL DEFAULT '',
    due_at        timestamptz,
    status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done')),
    kind          text NOT NULL DEFAULT 'manual',
    source        text NOT NULL DEFAULT 'manual',
    created_at    timestamptz NOT NULL DEFAULT now(),
    completed_at  timestamptz
);
CREATE INDEX IF NOT EXISTS tasks_tenant_idx ON tasks (tenant_id, status, due_at);

ALTER TABLE leads ADD COLUMN IF NOT EXISTS won_at timestamptz;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS lost_at timestamptz;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS lost_reason text NOT NULL DEFAULT '';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS next_action_at timestamptz;

CREATE TABLE IF NOT EXISTS lead_events (
    id           bigserial PRIMARY KEY,
    lead_id      uuid NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    from_status  text NOT NULL,
    to_status    text NOT NULL,
    note         text NOT NULL DEFAULT '',
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS lead_events_tenant_idx ON lead_events (tenant_id, created_at DESC);

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS calendar_token text;
CREATE UNIQUE INDEX IF NOT EXISTS tenants_calendar_token_idx ON tenants (calendar_token);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS weekly_digest boolean NOT NULL DEFAULT false;


-- Human-reviewed email replies: no message is sent until explicit approval.
CREATE TABLE IF NOT EXISTS email_drafts (
    id            bigserial PRIMARY KEY,
    tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    source_id     text,
    sender        text NOT NULL,
    subject       text NOT NULL DEFAULT '',
    inbound_body  text NOT NULL,
    reply_body    text NOT NULL,
    status        text NOT NULL DEFAULT 'draft'
                  CHECK (status IN ('draft', 'approved', 'discarded', 'quarantined')),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    approved_at   timestamptz
);
ALTER TABLE email_drafts ADD COLUMN IF NOT EXISTS auth jsonb;
ALTER TABLE email_drafts ADD COLUMN IF NOT EXISTS risk text;
ALTER TABLE email_drafts ADD COLUMN IF NOT EXISTS flags jsonb;
ALTER TABLE email_drafts DROP CONSTRAINT IF EXISTS email_drafts_status_check;
ALTER TABLE email_drafts ADD CONSTRAINT email_drafts_status_check
    CHECK (status IN ('draft', 'approved', 'discarded', 'quarantined'));
CREATE UNIQUE INDEX IF NOT EXISTS email_drafts_source_idx
    ON email_drafts (tenant_id, source_id) WHERE source_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS email_drafts_inbox_idx
    ON email_drafts (tenant_id, status, created_at DESC);

-- Voice remains opt-in for new tenants; existing choices stay unchanged.
ALTER TABLE tenants ALTER COLUMN voice_enabled SET DEFAULT false;


-- Opt-in telephone receptionist, requiring number ownership and valid Twilio signatures.
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS phone_enabled boolean NOT NULL DEFAULT false;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS phone_daily_limit integer NOT NULL DEFAULT 30;
CREATE TABLE IF NOT EXISTS phone_numbers (
    e164         text PRIMARY KEY,
    tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    enabled      boolean NOT NULL DEFAULT false,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS phone_numbers_tenant_idx ON phone_numbers (tenant_id);
CREATE TABLE IF NOT EXISTS phone_calls (
    call_sid     text PRIMARY KEY,
    tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id   text,
    from_number  text NOT NULL DEFAULT '',
    to_number    text NOT NULL,
    status       text NOT NULL DEFAULT 'ringing',
    started_at   timestamptz NOT NULL DEFAULT now(),
    ended_at     timestamptz
);
CREATE INDEX IF NOT EXISTS phone_calls_tenant_idx ON phone_calls (tenant_id, started_at DESC);
-- Audio capture is never automatic: recording requires an explicit caller
-- phrase on an opted-in call, per-tenant permission and operator enablement.
ALTER TABLE phone_calls ADD COLUMN IF NOT EXISTS recording_consent text NOT NULL DEFAULT 'not_requested';
ALTER TABLE phone_calls ADD COLUMN IF NOT EXISTS recording_sid text;
ALTER TABLE phone_calls ADD COLUMN IF NOT EXISTS recording_status text NOT NULL DEFAULT 'not_started';
ALTER TABLE phone_calls ADD COLUMN IF NOT EXISTS consent_at timestamptz;



-- Tenant owner access, isolated from the global operator token.
CREATE TABLE IF NOT EXISTS tenant_users (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 email text NOT NULL,
 role text NOT NULL CHECK (role IN ('viewer','editor','owner')),
 password_hash text NOT NULL,
 active boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (tenant_id,email)
);
CREATE TABLE IF NOT EXISTS tenant_invites (
 id bigserial PRIMARY KEY,
 tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 email text NOT NULL,
 role text NOT NULL CHECK (role IN ('viewer','editor','owner')),
 purpose text NOT NULL CHECK (purpose IN ('invite','recovery')),
 token_hash text UNIQUE NOT NULL,
 expires_at timestamptz NOT NULL,
 used_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS tenant_sessions (
 id bigserial PRIMARY KEY,
 user_id uuid NOT NULL REFERENCES tenant_users(id) ON DELETE CASCADE,
 token_hash text UNIQUE NOT NULL,
 expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS tenant_sessions_user_idx ON tenant_sessions(user_id);

-- Shared owner-login limiter; no raw client IP or email is persisted.
CREATE TABLE IF NOT EXISTS owner_login_limits (
 key_hash text PRIMARY KEY,
 attempts integer NOT NULL,
 window_until timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS owner_login_limits_expiry_idx ON owner_login_limits(window_until);

-- Private mailbox ownership verified by operator; never accept tenant from email.
CREATE TABLE IF NOT EXISTS inbound_mailboxes (
 recipient text PRIMARY KEY,
 tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 provider text NOT NULL CHECK (provider IN ('cloudflare')),
 enabled boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS inbound_mailboxes_tenant_idx ON inbound_mailboxes(tenant_id);

-- Durable and tenant-scoped Twenty bridge delivery; never silently deliver to
-- another customer's CRM. Uncertain outcomes require manual reconciliation.
CREATE TABLE IF NOT EXISTS twenty_deliveries (
    id          bigserial PRIMARY KEY,
    tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    event       text NOT NULL CHECK (event IN ('lead.created', 'appointment.booked')),
    source_id   text NOT NULL,
    payload     jsonb NOT NULL,
    status      text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','sending','sent','failed','uncertain')),
    attempts    integer NOT NULL DEFAULT 0,
    next_at     timestamptz NOT NULL DEFAULT now(),
    claimed_at  timestamptz,
    last_error  text NOT NULL DEFAULT '',
    delivered_at timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE(tenant_id,event,source_id)
);
CREATE INDEX IF NOT EXISTS twenty_delivery_due_idx
ON twenty_deliveries(status,next_at);

-- Customer authorizations do not activate channels. They are owner declarations
-- and must be paired with separately verified provider grants and operator enablement.
CREATE TABLE IF NOT EXISTS tenant_channel_authorizations (
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    channel text NOT NULL CHECK (channel IN
        ('telephone','call_recording','email_read','email_send',
         'sms_read','sms_send','social')),
    authorized boolean NOT NULL DEFAULT false,
    actor_id uuid NOT NULL,  -- immutable owner principal even after account deletion
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(tenant_id,channel)
);
CREATE TABLE IF NOT EXISTS tenant_channel_authorization_audit (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    channel text NOT NULL CHECK (channel IN
        ('telephone','call_recording','email_read','email_send',
         'sms_read','sms_send','social')),
    authorized boolean NOT NULL,
    actor_id uuid NOT NULL,  -- preserve audit identity after user deletion
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS tenant_channel_audit_tenant_idx
ON tenant_channel_authorization_audit(tenant_id, created_at DESC);

-- A setup request is not number ownership, provisioning or activation.
CREATE TABLE IF NOT EXISTS managed_phone_setups (
    tenant_id uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    designated_number text NOT NULL,
    connection text NOT NULL CHECK(connection IN ('existing_sip','existing_twilio','mobile_forwarding')),
    answer_mode text NOT NULL CHECK(answer_mode IN ('all_calls','unanswered')),
    owner_number text NOT NULL,
    status text NOT NULL DEFAULT 'requested' CHECK(status IN ('requested','provisioning','test_required','active')),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Voice recordings remain private; external links are explicit, short-lived shares.
CREATE TABLE IF NOT EXISTS voice_sessions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 token_hash text NOT NULL UNIQUE,
 recording_consent boolean NOT NULL DEFAULT false,
 expires_at timestamptz NOT NULL DEFAULT now()+interval '30 minutes',
 finalized_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS voice_recordings (
 session_id uuid PRIMARY KEY REFERENCES voice_sessions(id) ON DELETE CASCADE,
 tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 mime_type text NOT NULL CHECK(mime_type IN ('audio/webm','audio/ogg','audio/mp4')),
 audio bytea NOT NULL CHECK(octet_length(audio)<=12582912),
 sha256 text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE voice_sessions ADD COLUMN IF NOT EXISTS delivery_request jsonb;
CREATE INDEX IF NOT EXISTS voice_recordings_tenant_idx ON voice_recordings(tenant_id,conversation_id);
CREATE TABLE IF NOT EXISTS voice_recording_shares (
 token_hash text PRIMARY KEY,
 session_id uuid NOT NULL REFERENCES voice_recordings(session_id) ON DELETE CASCADE,
 tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 expires_at timestamptz NOT NULL DEFAULT now()+interval '24 hours'
);

-- Explicit business-owned destination; public mobile number remains unchanged.
CREATE TABLE IF NOT EXISTS mobile_forwarding_connections (
 tenant_id uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
 destination text UNIQUE NOT NULL REFERENCES phone_numbers(e164) ON DELETE CASCADE,
 carrier text NOT NULL CHECK(carrier IN ('spark_nz','other')),
 created_at timestamptz NOT NULL DEFAULT now()
);

-- Telephone AudioSocket capture uses bounded mono PCM WAV, shared owner playback.
ALTER TABLE voice_recordings DROP CONSTRAINT IF EXISTS voice_recordings_mime_type_check;
ALTER TABLE voice_recordings ADD CONSTRAINT voice_recordings_mime_type_check
 CHECK(mime_type IN ('audio/webm','audio/ogg','audio/mp4','audio/wav'));

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS notify_phone text;
-- Per-tenant dialling country, so a local number becomes the RIGHT E.164 form. The global default
-- is '1' (US); a business outside +1 previously inherited it and produced wrong numbers, which also
-- split one customer across two case identities.
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS default_country_code text NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS quotations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 lead_id uuid NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
 title text NOT NULL, currency text NOT NULL,
 status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','reviewed','accepted','declined','void')),
 lines jsonb NOT NULL, contact jsonb NOT NULL,
 tax_basis_points integer NOT NULL CHECK(tax_basis_points BETWEEN 0 AND 10000),
 subtotal_cents bigint NOT NULL CHECK(subtotal_cents>=0),
 tax_cents bigint NOT NULL CHECK(tax_cents>=0), total_cents bigint NOT NULL CHECK(total_cents>=0),
 notes text NOT NULL DEFAULT '', version integer NOT NULL DEFAULT 1,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS quotations_tenant_idx ON quotations(tenant_id,created_at DESC);
CREATE TABLE IF NOT EXISTS enquiry_sources (
 tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 channel text NOT NULL, source_key text NOT NULL,
 lead_id uuid NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
 original_text text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,channel,source_key)
);
CREATE TABLE IF NOT EXISTS calendar_connections (
 tenant_id uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
 calendar_id text NOT NULL DEFAULT 'primary', enabled boolean NOT NULL DEFAULT true,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS calendar_oauth_states (
 token_hash text PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 user_id uuid NOT NULL, expires_at timestamptz NOT NULL DEFAULT now()+interval '10 minutes'
);
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS calendar_sync_requested boolean NOT NULL DEFAULT false;
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS calendar_notice_done boolean NOT NULL DEFAULT false;
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS calendar_state text NOT NULL DEFAULT 'unconnected';
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS calendar_event_id text;
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS calendar_error text NOT NULL DEFAULT '';
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS calendar_synced_at timestamptz;
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS invitation_state text NOT NULL DEFAULT 'pending';
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS calendar_attempts integer NOT NULL DEFAULT 0;
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS calendar_retry_at timestamptz NOT NULL DEFAULT now();
CREATE UNIQUE INDEX IF NOT EXISTS appointment_conversation_slot_idx ON appointments(tenant_id,conversation_id,starts_at) WHERE conversation_id IS NOT NULL;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS pending_ack jsonb;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS email_auto_reply boolean NOT NULL DEFAULT false;
CREATE TABLE IF NOT EXISTS email_secretary_jobs (
 id bigserial PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 source_key text NOT NULL, sender text NOT NULL, subject text NOT NULL, body text NOT NULL,
 status text NOT NULL DEFAULT 'pending', attempts integer NOT NULL DEFAULT 0,
 claimed_at timestamptz, error text NOT NULL DEFAULT '', UNIQUE(tenant_id,source_key)
);

-- Unified customer case timeline (see app/casetimeline.py).
-- A case is a CUSTOMER, not a conversation: one person who emails, texts and calls is one case,
-- whatever channel each message arrived on. `case_key` is derived from the strongest available
-- identity (E.164 phone, else lower-cased email) and is tenant-scoped.
CREATE TABLE IF NOT EXISTS customer_cases (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    case_key          text NOT NULL,
    display_name      text NOT NULL DEFAULT '',
    company           text NOT NULL DEFAULT '',
    primary_phone     text NOT NULL DEFAULT '',
    primary_email     text NOT NULL DEFAULT '',
    -- Set when the owner personally replies: automation must stop chasing this customer.
    automation_paused boolean NOT NULL DEFAULT false,
    takeover_at       timestamptz,
    takeover_by       text NOT NULL DEFAULT '',
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, case_key)
);
CREATE INDEX IF NOT EXISTS customer_cases_tenant_idx ON customer_cases (tenant_id, updated_at DESC);

-- Append-only cross-channel history. `source_key` makes provider webhook replays idempotent.
CREATE TABLE IF NOT EXISTS case_events (
    id          bigserial PRIMARY KEY,
    case_id     uuid NOT NULL REFERENCES customer_cases(id) ON DELETE CASCADE,
    tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    channel     text NOT NULL,
    direction   text NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    -- Set for messages; NULL for non-message events (booking, quote, note).
    source_key  text,
    body        text NOT NULL DEFAULT '',
    occurred_at timestamptz NOT NULL DEFAULT now(),
    -- When this inbound message was answered, so unanswered work can be found without guessing.
    answered_at timestamptz,
    UNIQUE (tenant_id, channel, source_key)
);
CREATE INDEX IF NOT EXISTS case_events_case_idx ON case_events (case_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS case_events_unanswered_idx
    ON case_events (tenant_id, occurred_at) WHERE direction = 'inbound' AND answered_at IS NULL;

-- Link existing per-channel records to the unified case. Nullable: existing rows keep working.
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS case_id uuid REFERENCES customer_cases(id) ON DELETE SET NULL;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS case_id uuid REFERENCES customer_cases(id) ON DELETE SET NULL;

-- Per-message follow-up. The old tasks_follow_up_idx allowed ONE follow-up per lead forever, so a
-- second customer message produced no new work. This adds a message-scoped unique index.
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS case_id uuid REFERENCES customer_cases(id) ON DELETE CASCADE;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS message_key text;
-- Replace the original one-per-lead index: it otherwise rejects every second message task.
DROP INDEX IF EXISTS tasks_follow_up_idx;
CREATE UNIQUE INDEX IF NOT EXISTS tasks_legacy_follow_up_idx
    ON tasks (lead_id) WHERE kind = 'follow_up' AND message_key IS NULL;
-- Unknown contacts have no case_id yet, but their replay must still not create duplicate work.
CREATE UNIQUE INDEX IF NOT EXISTS tasks_lead_message_follow_up_idx
    ON tasks (lead_id, message_key) WHERE kind = 'follow_up' AND message_key IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS tasks_message_follow_up_idx
    ON tasks (case_id, message_key) WHERE kind = 'follow_up' AND message_key IS NOT NULL;

-- Hermes gateway support (see app/hermes_ops.py). All additive; everything stays off until HERMES_GATEWAY_ENABLED.
CREATE TABLE IF NOT EXISTS hermes_tenant_settings (
    tenant_id      uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    autonomy       text NOT NULL DEFAULT 'shadow' CHECK (autonomy IN ('shadow', 'draft_review', 'auto_routine')),
    min_confidence real NOT NULL DEFAULT 0.8 CHECK (min_confidence BETWEEN 0 AND 1),
    updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS hermes_case_state (
    tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    lead_id           uuid NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    automation_paused boolean NOT NULL DEFAULT false,
    updated_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, lead_id)
);
CREATE TABLE IF NOT EXISTS hermes_actions (
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    idempotency_key text NOT NULL,
    lead_id         uuid NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    op              text NOT NULL,
    fingerprint     text NOT NULL,
    state           text NOT NULL,
    result          jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, idempotency_key)
);

-- Inbound email safety (Phase 1): per-tenant sender policy and an audit trail.
CREATE TABLE IF NOT EXISTS inbound_sender_rules (
    id         bigserial PRIMARY KEY,
    tenant_id  uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    pattern    text NOT NULL,
    action     text NOT NULL CHECK (action IN ('allow', 'block')),
    created_by text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, pattern, action)
);
CREATE TABLE IF NOT EXISTS inbound_audit (
    id         bigserial PRIMARY KEY,
    tenant_id  uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    draft_id   bigint,
    action     text NOT NULL,
    actor      text NOT NULL DEFAULT '',
    detail     jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS inbound_audit_tenant_idx
    ON inbound_audit (tenant_id, created_at DESC);

-- Query tuning for common owner/chat reads (2026-11-11).
CREATE INDEX IF NOT EXISTS leads_conversation_idx ON leads (tenant_id, conversation_id, created_at);
CREATE INDEX IF NOT EXISTS conversations_tenant_started_idx ON conversations (tenant_id, started_at DESC);

-- Transcript identity for the Rust voice shell (replaces per-call in-memory map).
ALTER TABLE messages ADD COLUMN IF NOT EXISTS item_id text;
CREATE UNIQUE INDEX IF NOT EXISTS messages_item_idx
    ON messages (conversation_id, item_id) WHERE item_id IS NOT NULL;

-- Company product catalogue and inventory for quotations. Cost is private to the
-- owner; assistants and staff-facing lists only ever see the sale price.
CREATE TABLE IF NOT EXISTS products (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    sku text NOT NULL,
    name text NOT NULL,
    description text NOT NULL DEFAULT '',
    unit text NOT NULL DEFAULT 'each',
    sale_price_cents bigint NOT NULL CHECK (sale_price_cents >= 0),
    cost_price_cents bigint CHECK (cost_price_cents IS NULL OR cost_price_cents >= 0),
    stock_quantity integer NOT NULL DEFAULT 0,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, sku)
);
CREATE INDEX IF NOT EXISTS products_tenant_idx ON products (tenant_id, active, name);
CREATE TABLE IF NOT EXISTS product_stock_movements (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    product_id uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    delta integer NOT NULL,
    reason text NOT NULL DEFAULT '',
    actor text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS product_stock_movements_idx ON product_stock_movements (tenant_id, product_id, created_at DESC);

-- Per-tenant reply address: replies to owner alerts come back into that tenant's CRM.
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS reply_address text;
CREATE UNIQUE INDEX IF NOT EXISTS tenants_reply_address_idx ON tenants (reply_address) WHERE reply_address IS NOT NULL;

-- Customer design/plan uploads for quotation takeoff.
CREATE TABLE IF NOT EXISTS design_uploads (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    uploaded_by text NOT NULL DEFAULT '',
    filename text NOT NULL,
    content_type text NOT NULL DEFAULT 'application/octet-stream',
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    sha256 text NOT NULL,
    storage_path text NOT NULL,
    status text NOT NULL DEFAULT 'uploaded' CHECK (status IN ('uploaded','parsed','failed')),
    summary jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS design_uploads_tenant_idx ON design_uploads (tenant_id, created_at DESC);


-- Marketing media: branded images and short videos rendered server-side.
CREATE TABLE IF NOT EXISTS media_brand (
    tenant_id uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    name text NOT NULL DEFAULT '',
    accent text NOT NULL DEFAULT '#c8f560',
    contact text NOT NULL DEFAULT '',
    logo_data text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS media_assets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('image','video','ai')),
    template text NOT NULL DEFAULT '',
    prompt text NOT NULL DEFAULT '',
    format text NOT NULL DEFAULT 'square',
    content_type text NOT NULL,
    storage_path text NOT NULL,
    created_by text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS media_assets_tenant_idx ON media_assets (tenant_id, created_at DESC);

ALTER TABLE media_assets ADD COLUMN IF NOT EXISTS size_bytes bigint NOT NULL DEFAULT 0;

ALTER TABLE quotations ADD COLUMN IF NOT EXISTS public_token text;
ALTER TABLE quotations ADD COLUMN IF NOT EXISTS sent_at timestamptz;
ALTER TABLE quotations ADD COLUMN IF NOT EXISTS accepted_at timestamptz;
ALTER TABLE quotations ADD COLUMN IF NOT EXISTS declined_at timestamptz;
UPDATE quotations SET public_token = replace(gen_random_uuid()::text, '-', '') WHERE public_token IS NULL;
ALTER TABLE quotations ALTER COLUMN public_token SET DEFAULT replace(gen_random_uuid()::text, '-', '');
CREATE UNIQUE INDEX IF NOT EXISTS quotations_public_token_idx ON quotations (public_token);

CREATE TABLE IF NOT EXISTS design_links (
    token text PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_by text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS ui_translation_cache (
    locale text NOT NULL,
    source text NOT NULL,
    translated text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (locale, source)
);

-- ---------------------------------------------------------------------------
-- Email operations (2026-11-12 assessment): bounce handling, suppression list,
-- authoritative consent audit, per-mailbox inbound limits.
-- ---------------------------------------------------------------------------

-- An address that hard-bounced, was blocked by the provider, or complained. Outbound
-- mail to a suppressed address is never attempted; a human may lift it.
CREATE TABLE IF NOT EXISTS email_suppressions (
    tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    address     text NOT NULL,
    reason      text NOT NULL DEFAULT '',
    source      text NOT NULL DEFAULT '',
    detail      jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, address)
);
CREATE INDEX IF NOT EXISTS email_suppressions_created_idx
    ON email_suppressions (tenant_id, created_at DESC);

-- Which address an audit row is about (refused message, blocked sender, bounce).
ALTER TABLE inbound_audit ADD COLUMN IF NOT EXISTS address text;

-- The Message-ID we sent, so a DSN or provider event can be matched to its outbox row.
ALTER TABLE outbox ADD COLUMN IF NOT EXISTS message_id text;
CREATE INDEX IF NOT EXISTS outbox_message_id_idx
    ON outbox (message_id) WHERE message_id IS NOT NULL;

-- Rate limiting is per mailbox, which needs the recipient recorded on the draft.
ALTER TABLE email_drafts ADD COLUMN IF NOT EXISTS recipient text NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS email_drafts_recipient_idx
    ON email_drafts (tenant_id, recipient, created_at DESC);

-- Consent provenance: an operator may grant on a customer's behalf, which is NOT an
-- owner principal, so actor_id is nullable and actor_kind/actor_label say who acted.
ALTER TABLE tenant_channel_authorizations ALTER COLUMN actor_id DROP NOT NULL;
ALTER TABLE tenant_channel_authorization_audit ALTER COLUMN actor_id DROP NOT NULL;
ALTER TABLE tenant_channel_authorization_audit
    ADD COLUMN IF NOT EXISTS actor_kind text NOT NULL DEFAULT 'owner';
ALTER TABLE tenant_channel_authorization_audit
    ADD COLUMN IF NOT EXISTS actor_label text NOT NULL DEFAULT '';

-- The audit table is now written by the database, not by the application, so an
-- out-of-band UPDATE (direct SQL) can no longer leave consent changes invisible.
CREATE OR REPLACE FUNCTION concierge_consent_audit() RETURNS trigger AS $fn$
BEGIN
    IF TG_OP = 'UPDATE'
       AND NEW.authorized IS NOT DISTINCT FROM OLD.authorized
       AND NEW.actor_id IS NOT DISTINCT FROM OLD.actor_id THEN
        RETURN NEW;
    END IF;
    INSERT INTO tenant_channel_authorization_audit
        (tenant_id, channel, authorized, actor_id, actor_kind, actor_label)
    VALUES (NEW.tenant_id, NEW.channel, NEW.authorized, NEW.actor_id,
            COALESCE(NULLIF(current_setting('concierge.actor_kind', true), ''), 'direct'),
            COALESCE(current_setting('concierge.actor_label', true), ''));
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tenant_channel_authorization_audit_trg
    ON tenant_channel_authorizations;
CREATE TRIGGER tenant_channel_authorization_audit_trg
    AFTER INSERT OR UPDATE ON tenant_channel_authorizations
    FOR EACH ROW EXECUTE FUNCTION concierge_consent_audit();

-- Missed-call text-back (competitor-gap item A, 2026-11-12).
-- One reply per caller number per day, and a row for every decision so the owner can see what
-- happened and the audit can explain why (see api/app/missed_calls.py).
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS missed_call_textback boolean NOT NULL DEFAULT true;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS missed_call_template text NOT NULL DEFAULT '';
CREATE TABLE IF NOT EXISTS missed_call_recoveries (
    id         bigserial PRIMARY KEY,
    call_sid   text NOT NULL,
    tenant_id  uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    contact    text NOT NULL DEFAULT '',
    lead_id    uuid REFERENCES leads(id) ON DELETE SET NULL,
    outbox_id  bigint,
    status     text NOT NULL DEFAULT 'queued',
    reason     text NOT NULL DEFAULT '',
    day        date NOT NULL DEFAULT current_date,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, call_sid)
);
CREATE INDEX IF NOT EXISTS missed_call_recoveries_tenant_idx
    ON missed_call_recoveries (tenant_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS missed_call_recoveries_one_per_day
    ON missed_call_recoveries (tenant_id, contact, day) WHERE status = 'queued' AND contact <> '';

-- After-call intelligence (competitor-gap item D, 2026-11-12): one validated record per call, so
-- an owner never has to read a transcript to know what happened and what to do next.
CREATE TABLE IF NOT EXISTS call_insights (
    id         bigserial PRIMARY KEY,
    call_sid   text NOT NULL,
    tenant_id  uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    lead_id    uuid REFERENCES leads(id) ON DELETE SET NULL,
    summary    text NOT NULL DEFAULT '',
    outcome    text NOT NULL DEFAULT 'unresolved',
    sentiment  text NOT NULL DEFAULT 'neutral' CHECK (sentiment IN ('positive','neutral','negative')),
    next_step  text NOT NULL DEFAULT '',
    model      text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, call_sid)
);
CREATE INDEX IF NOT EXISTS call_insights_tenant_idx ON call_insights (tenant_id, created_at DESC);

-- Getting paid on an accepted quotation (competitor-gap item E, 2026-11-12).
-- Processor-free by design: the customer declares, the owner confirms, and every transition is
-- appended to quote_payments so revenue can be reported (item F) rather than guessed.
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS payment_instructions text NOT NULL DEFAULT '';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS payment_url text NOT NULL DEFAULT '';
ALTER TABLE quotations ADD COLUMN IF NOT EXISTS payment_status text NOT NULL DEFAULT 'unpaid';
ALTER TABLE quotations ADD COLUMN IF NOT EXISTS payment_reference text NOT NULL DEFAULT '';
ALTER TABLE quotations ADD COLUMN IF NOT EXISTS payment_declared_at timestamptz;
ALTER TABLE quotations ADD COLUMN IF NOT EXISTS payment_confirmed_at timestamptz;
CREATE TABLE IF NOT EXISTS quote_payments (
    id            bigserial PRIMARY KEY,
    tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    quotation_id  uuid NOT NULL REFERENCES quotations(id) ON DELETE CASCADE,
    kind          text NOT NULL,
    amount_cents  bigint NOT NULL DEFAULT 0,
    reference     text NOT NULL DEFAULT '',
    by_kind       text NOT NULL DEFAULT '',
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS quote_payments_tenant_idx ON quote_payments (tenant_id, created_at DESC);

-- Supervision audit trail (2026-11-12). The phone greeting tells callers a team member may
-- listen, so every listen/whisper/join is recorded: who, which call, which mode, and — from
-- the two timestamps, never a guess — how long. `marker` is the value the originate writes to
-- CONCIERGE_SPY so the PBX channel carrying a leg can be found and ended again.
CREATE TABLE IF NOT EXISTS supervision_sessions (
    id                bigserial PRIMARY KEY,
    tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    call_sid          text NOT NULL,
    mode              text NOT NULL,
    supervisor        text NOT NULL DEFAULT '',
    supervisor_number text NOT NULL DEFAULT '',
    marker            text NOT NULL DEFAULT '',
    spy_channel       text NOT NULL DEFAULT '',
    started_at        timestamptz NOT NULL DEFAULT now(),
    ended_at          timestamptz,
    ended_reason      text NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS supervision_sessions_tenant_idx
    ON supervision_sessions (tenant_id, started_at DESC);
CREATE INDEX IF NOT EXISTS supervision_sessions_call_idx
    ON supervision_sessions (call_sid, started_at DESC);
CREATE INDEX IF NOT EXISTS supervision_sessions_open_idx
    ON supervision_sessions (tenant_id) WHERE ended_at IS NULL;

-- A business whose owner works in writing only (for example a Deaf owner): no human is ever rung,
-- the assistant never offers a transfer or a phone call-back, and take-over/listen-in are refused.
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS owner_text_only boolean NOT NULL DEFAULT false;

-- Operator switches (outbound_paused: the flood kill switch) and the index the flood guard counts with.
CREATE TABLE IF NOT EXISTS system_flags (
    key        text PRIMARY KEY,
    value      text NOT NULL DEFAULT '',
    updated_by text NOT NULL DEFAULT '',
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS outbox_claimed_idx ON outbox (channel, claimed_at)
    WHERE status IN ('sent', 'awaiting_receipt');

-- Session 19: a dedicated call number (alerts and transfers no longer have to share notify_phone)
-- and the reason a phone call failed (the 12 Nov failure evidence was lost to a restart).
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS owner_call_phone text;
ALTER TABLE phone_calls ADD COLUMN IF NOT EXISTS failure_reason text NOT NULL DEFAULT '';
-- Session 19: opt-in acknowledgement (with a reference) for verified inbound email.
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS inbound_ack boolean NOT NULL DEFAULT false;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS inbound_ack_text text;
-- Session 19: Web Push subscriptions for owner alerts (installed portal).
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id          bigserial PRIMARY KEY,
    tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    endpoint    text NOT NULL UNIQUE,
    p256dh      text NOT NULL,
    auth        text NOT NULL,
    user_agent  text NOT NULL DEFAULT '',
    created_at  timestamptz NOT NULL DEFAULT now(),
    last_ok_at  timestamptz,
    failures    integer NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS push_subscriptions_tenant_idx ON push_subscriptions (tenant_id);

-- A customer can be reached at more than one address: a mobile and a landline, a work and a
-- personal email. Until now a person had exactly one primary_phone and one primary_email, so
-- someone who called from their mobile and emailed from work looked like two strangers, and the
-- owner saw one customer as two. Identity is (tenant, kind, value): an address belongs to exactly
-- one customer within a business, which is what makes it safe to match on.
CREATE TABLE IF NOT EXISTS customer_addresses (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    case_id uuid NOT NULL REFERENCES customer_cases(id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('phone','email')),
    value text NOT NULL,
    label text NOT NULL DEFAULT '',
    source text NOT NULL DEFAULT 'inbound',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, kind, value)
);
CREATE INDEX IF NOT EXISTS customer_addresses_case_idx ON customer_addresses (case_id);

-- Backfill: every customer already known becomes reachable at their stored identifiers, so the
-- new matching works on existing history rather than only on traffic that arrives from now on.
INSERT INTO customer_addresses (tenant_id, case_id, kind, value, source)
SELECT tenant_id, id, 'phone', primary_phone, 'backfill'
FROM customer_cases WHERE primary_phone <> ''
ON CONFLICT (tenant_id, kind, value) DO NOTHING;

INSERT INTO customer_addresses (tenant_id, case_id, kind, value, source)
SELECT tenant_id, id, 'email', lower(primary_email), 'backfill'
FROM customer_cases WHERE primary_email <> ''
ON CONFLICT (tenant_id, kind, value) DO NOTHING;

-- A business that already runs its own CRM must be able to get its customer data out, and to
-- have new activity pushed to it, instead of being locked in. Two pieces: one webhook per tenant
-- (the push side), and a small outbox so a failed delivery is retried rather than lost.
CREATE TABLE IF NOT EXISTS tenant_webhooks (
    tenant_id uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    url text NOT NULL,
    secret text NOT NULL,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS webhook_events (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    event text NOT NULL,
    payload jsonb NOT NULL,
    attempts int NOT NULL DEFAULT 0,
    delivered_at timestamptz,
    last_error text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS webhook_events_pending_idx
    ON webhook_events (created_at) WHERE delivered_at IS NULL;

-- A B2B enquiry carries a company as well as a person. Storing only the person lost half of what
-- the customer told us in their own signature.
ALTER TABLE leads ADD COLUMN IF NOT EXISTS company text NOT NULL DEFAULT '';
ALTER TABLE customer_cases ADD COLUMN IF NOT EXISTS company text NOT NULL DEFAULT '';

-- How a business turns a measurement into money. One row per quoting method the owner offers, so a
-- cladding contractor can price by net clad area per m2 while another business prices per hour or as
-- a fixed callout. Kept separate from products: a rate per square metre is not a stock item.
CREATE TABLE IF NOT EXISTS quote_profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name text NOT NULL,
    unit text NOT NULL DEFAULT 'm²',
    rate_cents bigint NOT NULL DEFAULT 0 CHECK (rate_cents >= 0 AND rate_cents <= 100000000),
    waste_percent numeric(5,2) NOT NULL DEFAULT 0 CHECK (waste_percent >= 0 AND waste_percent <= 100),
    minimum_cents bigint NOT NULL DEFAULT 0 CHECK (minimum_cents >= 0),
    measurement text NOT NULL DEFAULT 'net_cladding'
        CHECK (measurement IN ('net_cladding','net_wall','gross_wall')),
    currency text NOT NULL DEFAULT 'NZD',
    tax_basis_points integer NOT NULL DEFAULT 1500 CHECK (tax_basis_points BETWEEN 0 AND 10000),
    is_default boolean NOT NULL DEFAULT false,
    active boolean NOT NULL DEFAULT true,
    notes text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS quote_profiles_tenant_idx ON quote_profiles(tenant_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS quote_profiles_one_default ON quote_profiles(tenant_id) WHERE is_default;

-- A quotation a business can hand a customer must be a document: who issued it, their GST number,
-- a reference, and how long the price stands. Without these a "quote" is a price on a screen.
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS gst_number text NOT NULL DEFAULT '';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS nzbn text NOT NULL DEFAULT '';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS business_address text NOT NULL DEFAULT '';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS business_phone text NOT NULL DEFAULT '';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS quote_terms text NOT NULL DEFAULT '';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS quote_valid_days integer NOT NULL DEFAULT 30
    CHECK (quote_valid_days BETWEEN 1 AND 365);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS quote_sequence integer NOT NULL DEFAULT 0;
ALTER TABLE quotations ADD COLUMN IF NOT EXISTS reference text;
ALTER TABLE quotations ADD COLUMN IF NOT EXISTS valid_until date;
CREATE UNIQUE INDEX IF NOT EXISTS quotations_reference_unique ON quotations(tenant_id, reference);
