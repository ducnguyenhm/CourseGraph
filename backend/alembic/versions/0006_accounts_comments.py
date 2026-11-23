"""accounts, advisor assignments, plan comments, placement overrides

Revision ID: 0006
Revises: 0005
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("plan_item", sa.Column("override_note", sa.Text, nullable=True))
    op.create_table(
        "account",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(32), nullable=False, unique=True),
        sa.Column("role", sa.String(8), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column(
            "student_id",
            sa.Integer,
            sa.ForeignKey("student.id", ondelete="CASCADE"),
            nullable=True,
            unique=True,
        ),
        sa.CheckConstraint("role IN ('student', 'advisor')", name="ck_account_role"),
        sa.CheckConstraint("(role = 'student') = (student_id IS NOT NULL)", name="ck_account_student"),
    )
    op.create_table(
        "advisor_assignment",
        sa.Column("advisor_id", sa.Integer, sa.ForeignKey("account.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("student_id", sa.Integer, sa.ForeignKey("student.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "plan_comment",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("student_id", sa.Integer, sa.ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("author_id", sa.Integer, sa.ForeignKey("account.id", ondelete="CASCADE"), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("course_id", sa.Integer, sa.ForeignKey("course.id"), nullable=True),
        sa.Column("term", sa.String(8), nullable=True),
        sa.Column("resolved", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("plan_comment")
    op.drop_table("advisor_assignment")
    op.drop_table("account")
    op.drop_column("plan_item", "override_note")
