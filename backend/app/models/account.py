from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Account(Base):
    """A login. A student account is attached to its student row (the key is
    the student_key) and is the only thing that may edit it; an advisor
    account has none. A student row with no account has no page that shows
    it (`check_view`)."""

    __tablename__ = "account"
    __table_args__ = (
        CheckConstraint("role IN ('student', 'advisor')", name="ck_account_role"),
        CheckConstraint(
            "(role = 'student') = (student_id IS NOT NULL)", name="ck_account_student"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(32), unique=True)
    role: Mapped[str] = mapped_column(String(8))
    name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(256))
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), unique=True, nullable=True
    )


class AdvisorAssignment(Base):
    __tablename__ = "advisor_assignment"

    advisor_id: Mapped[int] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), primary_key=True
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), primary_key=True
    )


class AdvisorInvite(Base):
    """An advisor's request to advise a student, until the student answers.
    It grants nothing: access comes only from an AdvisorAssignment, which
    the student's yes creates."""

    __tablename__ = "advisor_invite"

    advisor_id: Mapped[int] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), primary_key=True
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlanComment(Base):
    """A comment on a plan, or on one course in it, or an answer to one.

    Keyed by student and course, not by plan_item row: re-seeding or moving a
    course replaces plan rows, and the comment should outlive that. `term` is
    where the course sat when the comment was written."""

    __tablename__ = "plan_comment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[int] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"))
    body: Mapped[str] = mapped_column(Text)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("course.id"), nullable=True)
    term: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # The conversation this answers; None for the comment that opened it.
    # Resolving is recorded on that first comment.
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("plan_comment.id", ondelete="CASCADE"), index=True, nullable=True
    )
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
