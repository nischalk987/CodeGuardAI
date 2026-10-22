"""Create registered users table.

Revision ID: 20261022_04
Revises: 20261018_03
"""
from alembic import op
import sqlalchemy as sa

revision = "20261022_04"
down_revision = "20261018_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    raise RuntimeError("Destructive downgrades are disabled; add a forward-only migration.")
