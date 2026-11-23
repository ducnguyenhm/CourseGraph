from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.catalog import CatalogYear, Course, CourseEquivalence, CourseVersion
from app.models.program import Program, ProgramVersion
from app.models.student import Student
from app.schemas.prereq import normalize_id, parse
from app.services.evaluator import StudentFacts
from app.services.programs import ProgramCourses, RequirementRow, program_courses
from app.services.ordering import Orderer
from app.services.requirements import CourseInfo, Engine, Record
from app.services.planner import Planner
from app.services.semesters import MAX_LOAD, current_term, starting_term, terms_elapsed


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


def requirement_tree(version: ProgramVersion) -> RequirementRow:
    """A program version's requirement rows, reassembled into their tree."""
    children: dict[int | None, list] = {}
    for r in version.requirements:
        children.setdefault(r.parent_id, []).append(r)

    def build(r) -> RequirementRow:
        return RequirementRow(
            label=r.label,
            rule_type=r.rule_type,
            spec=r.spec,
            notes=r.notes,
            children=[build(c) for c in sorted(children.get(r.id, []), key=lambda c: c.position)],
        )

    return build(children[None][0])


def course_infos(session: Session, catalog_year: str) -> dict[str, CourseInfo]:
    """What the requirement engine needs to know about every course, stubs
    included: a transcript holds courses from departments not curated here."""
    out: dict[str, CourseInfo] = {}
    for v in versions_for(session, catalog_year, include_stubs=True):
        tags = set(v.attributes or [])
        if v.distribution:
            tags.add(v.distribution)
        # Variable-credit courses (CSC 184: 0-0.5) count at their maximum.
        credits = v.credits_max if v.credits_max is not None else v.credits_min
        out[v.course.course_id] = CourseInfo(
            v.course.subject,
            v.course.number,
            float(credits) if credits is not None else 1.0,
            frozenset(tags),
            stub=v.course.stub,
        )
    return out


def student_engine(session: Session, student: Student, catalog_year: str) -> Engine:
    """The requirement engine over a student's transcript and plan."""
    ids = {c.id: c.course_id for c in session.scalars(select(Course))}
    taken = [
        (ids[e.course_id], e.status, e.competence, e.area_choice) for e in student.enrollments
    ]
    taken += [(ids[p.course_id], "planned", None) for p in student.plan_items]
    catalog = course_infos(session, catalog_year)
    return Engine(Record.build(taken, catalog, all_equivalences(session)), catalog)


def student_term(student: Student) -> str:
    """The term the student is in: theirs if they set one, else the one in
    progress on the record, else the latest on it. A new account has no
    courses yet, so it falls back to today's term (or the start term)."""
    return (
        student.current_term
        or current_term((e.term, e.status) for e in student.enrollments)
        or starting_term(student.start_term, date.today())
    )


def student_orderer(session: Session, student: Student, catalog_year: str, engine: Engine) -> Orderer:
    """Prerequisite rounds counted from where the student is: courses done
    or in progress sit at round 0, and standing waits start from the terms
    already behind them."""
    trees = {
        v.course.course_id: parse(v.prereq_expr)
        for v in versions_for(session, catalog_year, include_stubs=True)
    }
    done = set().union(
        *(e.counts_as for e in engine.record.entries if e.state in ("completed", "in_progress"))
    )
    return Orderer(
        trees,
        equivalence_map(session),
        done=done,
        terms_elapsed=terms_elapsed(
            [e.term for e in student.enrollments],
            student.class_standing,
            start=student.start_term,
            current=student_term(student),
        ),
    )


def student_planner(
    session: Session,
    student: Student,
    catalog_year: str,
    max_load: float = MAX_LOAD,
    removed: list[str] | None = None,
) -> Planner:
    """The semester planner over a student's record. The plan itself is not
    read here: the database's and a demo session's are passed per call, and
    so are a demo session's removed terms (`removed`)."""
    _, facts = student_facts(session, student.student_key)
    infos = course_infos(session, catalog_year)
    trees = {
        v.course.course_id: parse(v.prereq_expr)
        for v in versions_for(session, catalog_year, include_stubs=True)
    }
    return Planner(
        trees,
        facts,
        current_term=student_term(student),
        terms_elapsed=terms_elapsed(
            [e.term for e in student.enrollments],
            student.class_standing,
            start=student.start_term,
            current=student_term(student),
        ),
        credits={cid: info.credits for cid, info in infos.items()},
        max_load=max_load,
        equivalences=all_equivalences(session),
        extended=[cid for cid, info in infos.items() if "ES" in info.tags],
        removed=student.removed_terms if removed is None else removed,
    )
