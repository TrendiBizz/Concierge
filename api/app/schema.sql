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
