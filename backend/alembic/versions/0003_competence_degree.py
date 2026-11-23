"""competence per enrollment; degree-level programs

Revision ID: 0003
Revises: 0002
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The transcript certifies W/Q/S per section, so it belongs on the
    # enrollment: MATH 151 may or may not have been taken as a Q section.
    op.add_column("enrollment", sa.Column("competence", sa.String(1), nullable=True))
    op.create_check_constraint(
        "ck_enrollment_competence", "enrollment", "competence IN ('W', 'Q', 'S')"
    )
    # The B.A. graduation requirements are evaluated like a program.
    op.drop_constraint("ck_program_kind", "program", type_="check")
    op.create_check_constraint(
        "ck_program_kind", "program", "kind IN ('major', 'minor', 'degree')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM program WHERE kind = 'degree'")
    op.drop_constraint("ck_program_kind", "program", type_="check")
    op.create_check_constraint("ck_program_kind", "program", "kind IN ('major', 'minor')")
    op.drop_constraint("ck_enrollment_competence", "enrollment", type_="check")
    op.drop_column("enrollment", "competence")
