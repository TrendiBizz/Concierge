"""Add unified Concierge social publishing tables (replaces separate social service SQLite DB).

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS social_customers (
            slug text PRIMARY KEY,
            name text NOT NULL,
            rules jsonb NOT NULL DEFAULT '{}'::jsonb,
            approval_contact text NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS social_accounts (
            id text PRIMARY KEY,
            customer_slug text NOT NULL REFERENCES social_customers(slug) ON DELETE CASCADE,
            network text NOT NULL,
            external_id text NOT NULL,
            display_name text NOT NULL DEFAULT '',
            token_enc text NOT NULL,
            refresh_enc text,
            granted_scopes text NOT NULL DEFAULT '',
            authorized_at timestamptz NOT NULL DEFAULT now(),
            disconnected_at timestamptz,
            expires_at timestamptz,
            needs_reauth boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (customer_slug, network, external_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_social_accounts_customer ON social_accounts(customer_slug)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS social_oauth_pending (
            state_hash text PRIMARY KEY,
            customer_slug text NOT NULL REFERENCES social_customers(slug) ON DELETE CASCADE,
            network text NOT NULL,
            verifier_enc text NOT NULL,
            expires_at timestamptz NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_social_oauth_pending_exp ON social_oauth_pending(expires_at)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS social_posts (
            id text PRIMARY KEY,
            customer_slug text NOT NULL REFERENCES social_customers(slug) ON DELETE CASCADE,
            content text NOT NULL,
            link text NOT NULL DEFAULT '',
            hashtags text NOT NULL DEFAULT '',
            account_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
            media jsonb NOT NULL DEFAULT '[]'::jsonb,
            options jsonb NOT NULL DEFAULT '{}'::jsonb,
            status text NOT NULL DEFAULT 'draft',
            scheduled_at timestamptz,
            revision integer NOT NULL DEFAULT 1,
            approved_revision integer,
            attempts integer NOT NULL DEFAULT 0,
            last_error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_social_posts_due ON social_posts(status, scheduled_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_social_posts_customer ON social_posts(customer_slug, created_at DESC)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS social_approvals (
            token_hash text PRIMARY KEY,
            customer_slug text NOT NULL,
            post_id text NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
            revision integer NOT NULL,
            scheduled_at timestamptz,
            expires_at timestamptz NOT NULL,
            used boolean NOT NULL DEFAULT false
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_social_approvals_post ON social_approvals(post_id)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS social_post_results (
            post_id text NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
            account_id text NOT NULL,
            external_post_id text,
            external_url text,
            error text,
            ok boolean NOT NULL,
            at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (post_id, account_id, ok)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS social_events (
            id bigserial PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT now(),
            customer_slug text NOT NULL,
            post_id text,
            kind text NOT NULL,
            detail text NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_social_events_customer ON social_events(customer_slug, at DESC)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS social_media_assets (
            id text PRIMARY KEY,
            customer_slug text NOT NULL,
            kind text NOT NULL,
            mime text NOT NULL,
            bytes bigint NOT NULL,
            width integer NOT NULL DEFAULT 0,
            height integer NOT NULL DEFAULT 0,
            duration_seconds double precision NOT NULL DEFAULT 0,
            storage_path text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_social_media_customer ON social_media_assets(customer_slug)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS social_media_assets")
    op.execute("DROP TABLE IF EXISTS social_events")
    op.execute("DROP TABLE IF EXISTS social_post_results")
    op.execute("DROP TABLE IF EXISTS social_approvals")
    op.execute("DROP TABLE IF EXISTS social_posts")
    op.execute("DROP TABLE IF EXISTS social_oauth_pending")
    op.execute("DROP TABLE IF EXISTS social_accounts")
    op.execute("DROP TABLE IF EXISTS social_customers")
