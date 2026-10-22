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
    # Batch mode uses SQLite's copy-and-move strategy in CI while still producing
    # a normal ALTER TABLE on PostgreSQL.
    with op.batch_alter_table("reviews") as batch_op:
        batch_op.add_column(sa.Column("owner_user_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_reviews_owner_user_id_users", "users",
            ["owner_user_id"], ["id"], ondelete="SET NULL",
        )
        batch_op.create_index("ix_reviews_owner_user_id", ["owner_user_id"])


def downgrade() -> None:
    raise RuntimeError("Destructive downgrades are disabled; add a forward-only migration.")
