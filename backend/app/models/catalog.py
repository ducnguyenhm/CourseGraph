from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class CatalogYear(Base):
    __tablename__ = "catalog_year"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(16), unique=True)
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    versions: Mapped[list["CourseVersion"]] = relationship(back_populates="catalog_year")


class Course(Base):
    """Persistent identity of a course, independent of any catalog year.

    Retired courses live here too: CSC-233 no longer appears in the 2026-27
    catalog but is still cited as a prerequisite by MATH-323, and students hold
    credit for it.
    """

    __tablename__ = "course"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[str] = mapped_column(String(16), unique=True)  # 'CSC-235'
    subject: Mapped[str] = mapped_column(String(8), index=True)
    number: Mapped[int] = mapped_column(Integer)
    retired: Mapped[bool] = mapped_column(Boolean, default=False)
    # Outside the curated scope; present only so references resolve.
    stub: Mapped[bool] = mapped_column(Boolean, default=False)

    versions: Mapped[list["CourseVersion"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class CourseVersion(Base):
    """A course as defined in one particular catalog year."""

    __tablename__ = "course_version"
    __table_args__ = (
        UniqueConstraint("course_id", "catalog_year_id", name="uq_course_version_year"),
        Index("ix_course_version_year_course", "catalog_year_id", "course_id"),
        Index("ix_course_version_prereq_gin", "prereq_expr", postgresql_using="gin"),
        CheckConstraint(
            "credits_min IS NULL OR credits_max IS NULL OR credits_min <= credits_max",
            name="ck_credits_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("course.id", ondelete="CASCADE"))
    catalog_year_id: Mapped[int] = mapped_column(ForeignKey("catalog_year.id"))

    title: Mapped[str] = mapped_column(String(256))
    # A range, not a number: CSC-296 runs 0.25-1.0 course units.
    credits_min: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)
    credits_max: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)

    distribution: Mapped[str | None] = mapped_column(String(8), nullable=True)
    competence_variants: Mapped[list] = mapped_column(JSONB, default=list)
    attributes: Mapped[list] = mapped_column(JSONB, default=list)

    prereq_raw: Mapped[str] = mapped_column(Text, default="")
    prereq_expr: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Curated fields the model does not yet interpret (antireq, cross_listed,
    # repeatable, offered, formerly, notes, counts_toward_major...). Kept so
    # curation effort is never silently discarded.
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)

    course: Mapped[Course] = relationship(back_populates="versions")
    catalog_year: Mapped[CatalogYear] = relationship(back_populates="versions")


class CourseEquivalence(Base):
    """Directed: completing `from` satisfies `to`.

    'renumber' — the same course under a new id (CSC-233 -> CSC-236).
    'satisfies' — additive; MATH-136 stays on record AND counts as MATH-151.
    """

    __tablename__ = "course_equivalence"
    __table_args__ = (
        UniqueConstraint("from_id", "to_id", "relation", name="uq_equivalence"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_id: Mapped[str] = mapped_column(String(16), index=True)
    to_id: Mapped[str] = mapped_column(String(16))
    relation: Mapped[str] = mapped_column(String(24))
    note: Mapped[str] = mapped_column(Text, default="")
