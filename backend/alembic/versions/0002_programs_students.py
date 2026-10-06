"""programs, requirements, and student records

Revision ID: 0002
Revises: 0001
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "program",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("program_id", sa.String(32), nullable=False, unique=True),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("department", sa.String(8), nullable=False),
        sa.CheckConstraint("kind IN ('major', 'minor')", name="ck_program_kind"),
    )

    op.create_table(
        "program_version",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "program_id",
            sa.Integer(),
            sa.ForeignKey("program.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "catalog_year_id",
            sa.Integer(),
            sa.ForeignKey("catalog_year.id"),
            nullable=False,
        ),
        sa.Column("total_courses", sa.Text(), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint("program_id", "catalog_year_id", name="uq_program_version_year"),
    )

    op.create_table(
        "requirement",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "program_version_id",
            sa.Integer(),
            sa.ForeignKey("program_version.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.Integer(),
            sa.ForeignKey("requirement.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("label", sa.String(256), nullable=False, server_default=""),
        sa.Column("rule_type", sa.String(24), nullable=False),
        sa.Column(
            "spec", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.CheckConstraint(
            "rule_type IN ('all_of', 'any_of', 'specific_course', 'n_from_set', "
            "'credit_minimum', 'attribute_count')",
            name="ck_requirement_rule_type",
        ),
    )
    op.create_index("ix_requirement_program_version_id", "requirement", ["program_version_id"])

    op.create_table(
        "student",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_key", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "catalog_year_id", sa.Integer(), sa.ForeignKey("catalog_year.id"), nullable=False
        ),
        sa.Column("class_standing", sa.String(16), nullable=False),
        sa.Column("expected_graduation", sa.String(8), nullable=False),
        sa.CheckConstraint(
            "class_standing IN ('first_year', 'sophomore', 'junior', 'senior')",
            name="ck_student_standing",
        ),
    )

    op.create_table(
        "student_program",
        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("student.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "program_id",
            sa.Integer(),
            sa.ForeignKey("program.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "enrollment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("student.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("course.id"), nullable=False),
        sa.Column("term", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("grade", sa.String(4), nullable=True),
        sa.CheckConstraint(
            "status IN ('completed', 'in_progress')", name="ck_enrollment_status"
        ),
    )
    op.create_index("ix_enrollment_student_id", "enrollment", ["student_id"])

    op.create_table(
        "plan_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("student.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("course.id"), nullable=False),
        sa.Column("term", sa.String(8), nullable=False),
    )
    op.create_index("ix_plan_item_student_id", "plan_item", ["student_id"])


def downgrade() -> None:
    op.drop_table("plan_item")
    op.drop_table("enrollment")
    op.drop_table("student_program")
    op.drop_table("student")
    op.drop_index("ix_requirement_program_version_id", table_name="requirement")
    op.drop_table("requirement")
    op.drop_table("program_version")
    op.drop_table("program")
