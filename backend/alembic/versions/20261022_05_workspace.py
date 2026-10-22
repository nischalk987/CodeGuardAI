"""Add user-owned repositories and review ownership.

Revision ID: 20261022_05
Revises: 20261022_04
"""
from alembic import op
import sqlalchemy as sa

revision = "20261022_05"
down_revision = "20261022_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_repositories",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("url", sa.String(length=300), nullable=False),
        sa.Column("default_branch", sa.String(length=100), nullable=False, server_default="main"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_user_id", "url", name="uq_user_repository_url"),
    )
    op.create_index("ix_user_repositories_owner_user_id", "user_repositories", ["owner_user_id"])
    op.add_column("reviews", sa.Column("owner_user_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_reviews_owner_user_id_users", "reviews", "users",
        ["owner_user_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_reviews_owner_user_id", "reviews", ["owner_user_id"])


def downgrade() -> None:
    raise RuntimeError("Destructive downgrades are disabled; add a forward-only migration.")
