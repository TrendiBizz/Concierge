"""Add Meta user OAuth session storage and social account metadata for Meta App Review flows.

Revision ID: 0007
Revises: 0006
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE social_accounts ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute("""
        CREATE TABLE IF NOT EXISTS social_meta_sessions (
            customer_slug          text PRIMARY KEY REFERENCES social_customers(slug) ON DELETE CASCADE,
            meta_user_id           text NOT NULL DEFAULT '',
            meta_user_name         text NOT NULL DEFAULT '',
            user_token_enc         text NOT NULL,
            granted_scopes         text NOT NULL DEFAULT '',
            expires_at             timestamptz,
            selected_business_id   text NOT NULL DEFAULT '',
            selected_business_name text NOT NULL DEFAULT '',
            updated_at             timestamptz NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS social_meta_sessions")
    op.execute("ALTER TABLE social_accounts DROP COLUMN IF EXISTS metadata")
