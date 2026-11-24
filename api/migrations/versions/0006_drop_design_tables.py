"""drop design_uploads, quote_profiles and design_links (3D/Designs feature removed 2026-11-25)

Production rows when this was written: design_uploads 0, quote_profiles 1 (a rate-0 "Nu-Wall cladding"
default profile), design_links 1 (expired 2026-11-18). The downgrade recreates structure only, no data.

Revision ID: 0006
Revises: 0005
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS design_uploads")
    op.execute("DROP TABLE IF EXISTS quote_profiles")
    op.execute("DROP TABLE IF EXISTS design_links")


def downgrade() -> None:
    op.execute("""
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
)""")
    op.execute("CREATE INDEX IF NOT EXISTS design_uploads_tenant_idx ON design_uploads (tenant_id, created_at DESC)")
    op.execute("""
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
)""")
    op.execute("CREATE INDEX IF NOT EXISTS quote_profiles_tenant_idx ON quote_profiles(tenant_id, created_at)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS quote_profiles_one_default ON quote_profiles(tenant_id) WHERE is_default")
    op.execute("""
CREATE TABLE IF NOT EXISTS design_links (
    token text PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_by text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
)""")
