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
    voice_enabled     boolean NOT NULL DEFAULT true,
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

CREATE TABLE IF NOT EXISTS voice_tokens (
    id         bigserial PRIMARY KEY,
    tenant_id  uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    minted_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS voice_tokens_idx ON voice_tokens (tenant_id, minted_at DESC);

-- ===================================================================
-- Phase 2 additions (idempotent): booking, automation, SMS/email, CRM
-- ===================================================================
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS timezone text NOT NULL DEFAULT 'America/Chicago';
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
