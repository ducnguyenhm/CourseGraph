"""comment replies: a plan comment opens a conversation the student answers in

Revision ID: 0007
Revises: 0006
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "plan_comment",
        sa.Column(
            "parent_id",
            sa.Integer,
            sa.ForeignKey("plan_comment.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_plan_comment_parent_id", "plan_comment", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_plan_comment_parent_id", table_name="plan_comment")
    op.drop_column("plan_comment", "parent_id")
