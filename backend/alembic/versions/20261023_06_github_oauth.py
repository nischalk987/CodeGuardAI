"""Persist user-scoped encrypted GitHub OAuth connection.

Revision ID: 20261023_06
Revises: 20261022_05
"""
from alembic import op
import sqlalchemy as sa

revision = "20261023_06"
down_revision = "20261022_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "github_oauth_connections",
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("github_login", sa.String(length=100), nullable=False),
        sa.Column("encrypted_access_token", sa.Text(), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    raise RuntimeError("Destructive downgrades are disabled; add a forward-only migration.")
