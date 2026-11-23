"""a student's start term and a current-term override

Revision ID: 0005
Revises: 0004
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Both optional. Without start_term, elapsed terms come from class
    # standing; without current_term, it is worked out from the record.
    op.add_column("student", sa.Column("start_term", sa.String(8), nullable=True))
    op.add_column("student", sa.Column("current_term", sa.String(8), nullable=True))


def downgrade() -> None:
    op.drop_column("student", "current_term")
    op.drop_column("student", "start_term")
