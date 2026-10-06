from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.catalog import CatalogYear, Course, CourseEquivalence, CourseVersion
from app.models.program import Program, ProgramVersion
from app.models.student import Student
from app.schemas.prereq import normalize_id
from app.services.evaluator import StudentFacts
from app.services.programs import ProgramCourses, program_courses


def versions_for(
    session: Session,
    catalog_year: str,
    subject: str | None = None,
    include_stubs: bool = False,
) -> list[CourseVersion]:
    stmt = (
        select(CourseVersion)
        .join(Course)
        .join(CatalogYear)
        .where(CatalogYear.label == catalog_year)
        .options(joinedload(CourseVersion.course))
        .order_by(Course.subject, Course.number)
    )
    if subject:
        stmt = stmt.where(Course.subject == subject.upper())
    if not include_stubs:
        stmt = stmt.where(Course.stub.is_(False))
    return list(session.scalars(stmt))


def version_by_id(
    session: Session, course_id: str, catalog_year: str
) -> CourseVersion | None:
    stmt = (
        select(CourseVersion)
        .join(Course)
        .join(CatalogYear)
        .where(
            Course.course_id == normalize_id(course_id),
            CatalogYear.label == catalog_year,
        )
        .options(joinedload(CourseVersion.course))
    )
    return session.scalars(stmt).first()


def equivalence_map(session: Session) -> dict[str, str]:
    """from_id -> to_id, for resolving retired course references."""
    return {
        e.from_id: e.to_id
        for e in session.scalars(
            select(CourseEquivalence).where(CourseEquivalence.relation == "renumber")
        )
    }


def all_equivalences(session: Session) -> list[tuple[str, str, str]]:
    """Every equivalence, both relations — a transcript is credited with what
    each course counts as, not only with renumberings."""
    return [
        (e.from_id, e.to_id, e.relation) for e in session.scalars(select(CourseEquivalence))
    ]


def student_facts(session: Session, key: str) -> tuple[Student, StudentFacts] | None:
    student = session.scalar(select(Student).where(Student.student_key == key))
    if student is None:
        return None
    ids = {c.id: c.course_id for c in session.scalars(select(Course))}
    programs = {p.id: p.program_id for p in session.scalars(select(Program))}
    done = [ids[e.course_id] for e in student.enrollments if e.status == "completed"]
    doing = [ids[e.course_id] for e in student.enrollments if e.status == "in_progress"]
    planned = [ids[p.course_id] for p in student.plan_items]
    facts = StudentFacts.build(
        done,
        doing,
        planned,
        student.class_standing,
        [programs[sp.program_id] for sp in student.programs],
        all_equivalences(session),
    )
    return student, facts


def program_version(
    session: Session, program_id: str, catalog_year: str
) -> ProgramVersion | None:
    return session.scalar(
        select(ProgramVersion)
        .join(Program)
        .join(CatalogYear)
        .where(Program.program_id == program_id.upper(), CatalogYear.label == catalog_year)
        .options(joinedload(ProgramVersion.program), joinedload(ProgramVersion.requirements))
    )


def courses_of(session: Session, version: ProgramVersion, catalog_year: str) -> ProgramCourses:
    catalog = {
        v.course.course_id: (v.course.subject, v.course.number)
        for v in versions_for(session, catalog_year)
    }
    return program_courses(((r.rule_type, r.spec) for r in version.requirements), catalog)
