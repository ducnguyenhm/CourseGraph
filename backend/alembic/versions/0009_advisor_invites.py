"""advisor invites: an advisor's request to advise a student, until answered

Revision ID: 0009
Revises: 0008
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "advisor_invite",
        sa.Column("advisor_id", sa.Integer, sa.ForeignKey("account.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("student_id", sa.Integer, sa.ForeignKey("student.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("advisor_invite")
