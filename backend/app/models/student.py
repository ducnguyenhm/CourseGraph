from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
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
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[int] = mapped_column(ForeignKey("course.id"))
    term: Mapped[str] = mapped_column(String(8))  # '2024FA'
    status: Mapped[str] = mapped_column(String(16))
    grade: Mapped[str | None] = mapped_column(String(4), nullable=True)


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
