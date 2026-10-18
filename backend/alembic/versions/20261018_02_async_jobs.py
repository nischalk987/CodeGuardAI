"""Add review job correlation and idempotency metadata.

Revision ID: 20261018_02
Revises: 20261018_01
"""

from alembic import op
import sqlalchemy as sa

revision = "20261018_02"
down_revision = "20261018_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reviews", sa.Column("correlation_id", sa.String(length=36), nullable=True))
    op.add_column("reviews", sa.Column("failure_reason", sa.Text(), nullable=True))
    op.add_column("reviews", sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    op.add_column("reviews", sa.Column("request_hash", sa.String(length=64), nullable=True))
    op.create_index(
        "uq_reviews_idempotency_key", "reviews", ["idempotency_key"], unique=True
    )


def downgrade() -> None:
    raise RuntimeError("Destructive downgrades are disabled; add a forward-only migration.")
