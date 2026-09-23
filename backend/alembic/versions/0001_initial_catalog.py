"""initial versioned catalog schema

Revision ID: 0001
Revises:
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_year",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(16), nullable=False, unique=True),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "course",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.String(16), nullable=False, unique=True),
        sa.Column("subject", sa.String(8), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("retired", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("stub", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_course_subject", "course", ["subject"])

    op.create_table(
        "course_version",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey("course.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "catalog_year_id",
            sa.Integer(),
            sa.ForeignKey("catalog_year.id"),
            nullable=False,
        ),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("credits_min", sa.Numeric(4, 2), nullable=True),
        sa.Column("credits_max", sa.Numeric(4, 2), nullable=True),
        sa.Column("distribution", sa.String(8), nullable=True),
        sa.Column(
            "competence_variants",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "attributes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("prereq_raw", sa.Text(), nullable=False, server_default=""),
        sa.Column("prereq_expr", postgresql.JSONB(), nullable=False),
        sa.Column(
            "extra",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.UniqueConstraint("course_id", "catalog_year_id", name="uq_course_version_year"),
        sa.CheckConstraint(
            "credits_min IS NULL OR credits_max IS NULL OR credits_min <= credits_max",
            name="ck_credits_range",
        ),
    )
    op.create_index(
        "ix_course_version_year_course",
        "course_version",
        ["catalog_year_id", "course_id"],
    )
    op.create_index(
        "ix_course_version_prereq_gin",
        "course_version",
        ["prereq_expr"],
        postgresql_using="gin",
    )

    op.create_table(
        "course_equivalence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("from_id", sa.String(16), nullable=False),
        sa.Column("to_id", sa.String(16), nullable=False),
        sa.Column("relation", sa.String(24), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint("from_id", "to_id", "relation", name="uq_equivalence"),
    )
    op.create_index("ix_course_equivalence_from", "course_equivalence", ["from_id"])


def downgrade() -> None:
    op.drop_table("course_equivalence")
    op.drop_table("course_version")
    op.drop_index("ix_course_subject", table_name="course")
    op.drop_table("course")
    op.drop_table("catalog_year")
