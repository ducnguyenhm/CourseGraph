"""the Foundations area a student pins an either-or course to

Revision ID: 0004
Revises: 0003
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # REL 130 is "Arts and Humanities-or-Global Learning". NULL lets the
    # requirement engine choose; a value fixes it for this enrollment.
    op.add_column("enrollment", sa.Column("area_choice", sa.String(4), nullable=True))
    op.create_check_constraint(
        "ck_enrollment_area_choice",
        "enrollment",
        "area_choice IN ('AH', 'SM', 'SS', 'LA', 'GL', 'PPD')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_enrollment_area_choice", "enrollment", type_="check")
    op.drop_column("enrollment", "area_choice")
