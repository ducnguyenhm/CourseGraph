from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Student(Base):
    """A student record. No login yet — authentication is Checkpoint 4, and it
    will attach an account to this row rather than replace it."""

    __tablename__ = "student"
    __table_args__ = (
        CheckConstraint(
            "class_standing IN ('first_year', 'sophomore', 'junior', 'senior')",
            name="ck_student_standing",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_key: Mapped[str] = mapped_column(String(32), unique=True)  # 'demo'
    name: Mapped[str] = mapped_column(String(128))
    # The catalog the student matriculated under — what they are evaluated by.
    catalog_year_id: Mapped[int] = mapped_column(ForeignKey("catalog_year.id"))
    # Stored, not derived: deriving it needs a "current term" and a credits rule.
    class_standing: Mapped[str] = mapped_column(String(16))
    expected_graduation: Mapped[str] = mapped_column(String(8))  # '2027SP'
    # The first term at the university. NULL: elapsed terms fall back on standing.
    start_term: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # Set by the student to override the term worked out from the record.
    current_term: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # Future terms the student took out of their plan (a semester away, a May
    # Term skipped): the planner shows no column for them.
    removed_terms: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )

    programs: Mapped[list["StudentProgram"]] = relationship(cascade="all, delete-orphan")
    enrollments: Mapped[list["Enrollment"]] = relationship(cascade="all, delete-orphan")
    plan_items: Mapped[list["PlanItem"]] = relationship(cascade="all, delete-orphan")


class StudentProgram(Base):
    """A declared major or minor."""

    __tablename__ = "student_program"

    student_id: Mapped[int] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), primary_key=True
    )
    program_id: Mapped[int] = mapped_column(
        ForeignKey("program.id", ondelete="CASCADE"), primary_key=True
    )


class Enrollment(Base):
    """The transcript: what was taken, as facts.

    References `course`, not `course_version`, so an entry for CSC-122 survives
    the renumbering and resolves through course_equivalence.
    """

    __tablename__ = "enrollment"
    __table_args__ = (
        CheckConstraint(
            "status IN ('completed', 'in_progress')", name="ck_enrollment_status"
        ),
        CheckConstraint("competence IN ('W', 'Q', 'S')", name="ck_enrollment_competence"),
        CheckConstraint(
            "area_choice IN ('AH', 'SM', 'SS', 'LA', 'GL', 'PPD')",
            name="ck_enrollment_area_choice",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[int] = mapped_column(ForeignKey("course.id"))
    term: Mapped[str] = mapped_column(String(8))  # '2024FA'
    status: Mapped[str] = mapped_column(String(16))
    grade: Mapped[str | None] = mapped_column(String(4), nullable=True)
    # W/Q/S certified in this section, if any. Per enrollment because the
    # catalog offers the course with or without it (competence_variants).
    competence: Mapped[str | None] = mapped_column(String(1), nullable=True)
    # For a course printed "X-or-Y" (REL 130: AH or GL), the Foundations area
    # the student wants it to count toward. NULL lets the engine choose.
    area_choice: Mapped[str | None] = mapped_column(String(4), nullable=True)


class PlanItem(Base):
    """A planned course: an intention, not a fact. Kept apart from enrollment
    because the Checkpoint 4 planner edits these and advisors comment on them."""

    __tablename__ = "plan_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[int] = mapped_column(ForeignKey("course.id"))
    term: Mapped[str] = mapped_column(String(8))
    # Why a placement the planner rejects was recorded anyway (consent, a
    # waiver). NULL for an ordinary placement.
    override_note: Mapped[str | None] = mapped_column(Text, nullable=True)
