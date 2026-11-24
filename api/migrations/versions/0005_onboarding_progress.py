"""Add onboarding_progress table for the 7-stage guided Studio onboarding hub.

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS onboarding_progress (
            tenant_id        uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
            completed_steps  jsonb NOT NULL DEFAULT '[]'::jsonb,
            current_stage    integer NOT NULL DEFAULT 1,
            launched_at      timestamptz,
            updated_at       timestamptz NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS onboarding_progress")
