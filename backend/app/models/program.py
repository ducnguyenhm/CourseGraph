from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Program(Base):
    """A major or minor as a persistent identity ('MAJOR-CSC')."""

    __tablename__ = "program"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    program_id: Mapped[str] = mapped_column(String(32), unique=True)
    kind: Mapped[str] = mapped_column(String(8))  # 'major' | 'minor' | 'degree'
    name: Mapped[str] = mapped_column(String(128))
    department: Mapped[str] = mapped_column(String(8))

    versions: Mapped[list["ProgramVersion"]] = relationship(
        back_populates="program", cascade="all, delete-orphan"
    )


class ProgramVersion(Base):
    """A program's requirements as one catalog year states them."""

    __tablename__ = "program_version"
    __table_args__ = (
        UniqueConstraint("program_id", "catalog_year_id", name="uq_program_version_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("program.id", ondelete="CASCADE"))
    catalog_year_id: Mapped[int] = mapped_column(ForeignKey("catalog_year.id"))
    total_courses: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")

    program: Mapped[Program] = relationship(back_populates="versions")
    requirements: Mapped[list["Requirement"]] = relationship(
        back_populates="program_version",
        cascade="all, delete-orphan",
        order_by="Requirement.position",
    )


class Requirement(Base):
    """One node of a program's requirement tree.

    Self-referential because real requirements nest: a group of core courses,
    plus n electives from a set, plus one allied course. `rule_type` picks the
    shape of `spec`:

    - all_of / any_of     — children only
    - specific_course     — {"course_id": "CSC-121"}
    - n_from_set          — {"n": 2, "courses": [...]} or
                            {"n": 3, "subject": "CSC", "min_number": 300, "exclude": [...]}
    - credit_minimum      — {"credits": 31, "subject"?, "min_number"?, "attribute"?,
                             "scope"?: "record" | "program"}
    - attribute_count     — {"n": 1, "attribute": "W", "scope"?, "exclusive"?,
                             "distinct_subjects"?, "distinct_group"?}

    Evaluated against a student's record by `services/requirements.py`.
    """

    __tablename__ = "requirement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    program_version_id: Mapped[int] = mapped_column(
        ForeignKey("program_version.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("requirement.id", ondelete="CASCADE"), nullable=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str] = mapped_column(String(256), default="")
    rule_type: Mapped[str] = mapped_column(String(24))
    spec: Mapped[dict] = mapped_column(JSONB, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")

    program_version: Mapped[ProgramVersion] = relationship(back_populates="requirements")
