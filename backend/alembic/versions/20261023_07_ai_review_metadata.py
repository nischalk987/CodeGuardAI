"""Persist optional AI review status independently from deterministic results.

Revision ID: 20261023_07
Revises: 20261023_06
"""
from alembic import op
import sqlalchemy as sa

revision = "20261023_07"
down_revision = "20261023_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reviews",
        sa.Column("ai_review_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "reviews",
        sa.Column("ai_review_status", sa.String(length=16), nullable=False, server_default="disabled"),
    )
    op.add_column("reviews", sa.Column("ai_review_message", sa.String(length=240), nullable=True))


def downgrade() -> None:
    raise RuntimeError("Destructive downgrades are disabled; add a forward-only migration.")
