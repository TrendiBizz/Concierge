"""baseline: existing schema as defined by app/schema.sql

The live schema is created and evolved idempotently by app/schema.sql, which the API applies at
startup. This revision is deliberately a no-op: it marks that state as the starting point so later
revisions can build on it. It does not create, drop or alter anything. On production run
`alembic stamp head` once; on a fresh database start the API once (applies schema.sql), then stamp.

Revision ID: 0001
Revises:
"""
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
