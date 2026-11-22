"""Add Meta messaging channel metadata and outbound reply columns.

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tenant_meta_channels ADD COLUMN IF NOT EXISTS page_id text NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE tenant_meta_channels ADD COLUMN IF NOT EXISTS waba_id text NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE tenant_meta_channels ADD COLUMN IF NOT EXISTS display_name text NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE tenant_meta_channels ADD COLUMN IF NOT EXISTS social_account_id text NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE tenant_meta_channels ADD COLUMN IF NOT EXISTS webhook_subscribed boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE meta_inbound_messages ADD COLUMN IF NOT EXISTS channel_external_id text NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE meta_inbound_messages ADD COLUMN IF NOT EXISTS template_name text NOT NULL DEFAULT ''")


def downgrade() -> None:
    op.execute("ALTER TABLE meta_inbound_messages DROP COLUMN IF EXISTS template_name")
    op.execute("ALTER TABLE meta_inbound_messages DROP COLUMN IF EXISTS channel_external_id")
    op.execute("ALTER TABLE tenant_meta_channels DROP COLUMN IF EXISTS webhook_subscribed")
    op.execute("ALTER TABLE tenant_meta_channels DROP COLUMN IF EXISTS social_account_id")
    op.execute("ALTER TABLE tenant_meta_channels DROP COLUMN IF EXISTS display_name")
    op.execute("ALTER TABLE tenant_meta_channels DROP COLUMN IF EXISTS waba_id")
    op.execute("ALTER TABLE tenant_meta_channels DROP COLUMN IF EXISTS page_id")
