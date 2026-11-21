"""drop the hermes_* tables (Hermes gateway was removed 2026-11-21)

The tables were empty on production when this was written. The downgrade recreates their
structure only (no data), copied from the former app/schema.sql block.

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS hermes_actions")
    op.execute("DROP TABLE IF EXISTS hermes_case_state")
    op.execute("DROP TABLE IF EXISTS hermes_tenant_settings")


def downgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS hermes_tenant_settings (
    tenant_id      uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    autonomy       text NOT NULL DEFAULT 'shadow' CHECK (autonomy IN ('shadow', 'draft_review', 'auto_routine')),
    min_confidence real NOT NULL DEFAULT 0.8 CHECK (min_confidence BETWEEN 0 AND 1),
    updated_at     timestamptz NOT NULL DEFAULT now()
)""")
    op.execute("""
CREATE TABLE IF NOT EXISTS hermes_case_state (
    tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    lead_id           uuid NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    automation_paused boolean NOT NULL DEFAULT false,
    updated_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, lead_id)
)""")
    op.execute("""
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
)""")
