"""Add idempotent GitHub webhook and pull-request review mappings.

Revision ID: 20261018_03
Revises: 20261018_02
"""

from alembic import op
import sqlalchemy as sa

revision = "20261018_03"
down_revision = "20261018_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "github_webhook_deliveries",
        sa.Column("delivery_id", sa.String(36), primary_key=True),
        sa.Column("event_name", sa.String(40), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("repository", sa.String(200), nullable=False),
        sa.Column("pull_request_number", sa.Integer(), nullable=False),
        sa.Column("commit_sha", sa.String(64), nullable=False),
        sa.Column("review_id", sa.String(64), sa.ForeignKey("reviews.id", ondelete="RESTRICT")),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enqueue_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "github_pull_request_reviews",
        sa.Column("repository", sa.String(200), primary_key=True),
        sa.Column("pull_request_number", sa.Integer(), primary_key=True),
        sa.Column("commit_sha", sa.String(64), primary_key=True),
        sa.Column(
            "review_id", sa.String(64), sa.ForeignKey("reviews.id", ondelete="RESTRICT"),
            nullable=False, unique=True,
        ),
        sa.Column("installation_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    raise RuntimeError("Destructive downgrades are disabled; add a forward-only migration.")
