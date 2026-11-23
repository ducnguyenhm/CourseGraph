"""Load curated catalog fixtures into PostgreSQL.

Reads the curated per-subject files as published, validates the union before
writing anything, and refuses a fixture set with unresolvable prerequisite
references or a cycle rather than half-loading it.

    python -m scripts.seed data/csc_catalog_2025_26.json data/math_catalog_2025_26.json
    python -m scripts.seed --if-empty
    python -m scripts.seed --check data/corrupt/csc_cycle_direct.json data/math_catalog_2025_26.json data/econ_catalog_2025_26.json

`--check` validates and reports without ever opening a database session, so a
deliberately corrupted fixture can be demonstrated against a live stack
without any risk to it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.account import Account, AdvisorAssignment
from app.models.catalog import CatalogYear, Course, CourseEquivalence, CourseVersion
from app.models.program import Program, ProgramVersion, Requirement
from app.models.student import Enrollment, PlanItem, Student, StudentProgram
from app.schemas.prereq import normalize_id, parse
from app.services.fixtures import check, read_programs, read_students
from app.services.programs import RequirementRow
from app.services.validation import CatalogError

DEFAULT_FIXTURES = [
    "data/csc_catalog_2025_26.json",
    "data/math_catalog_2025_26.json",
    "data/econ_catalog_2025_26.json",
    "data/other_stubs_2025_26.json",
]
DEFAULT_PROGRAMS = "data/programs_2025_26.json"
DEFAULT_STUDENTS = "data/demo_student.json"
DEFAULT_ACCOUNTS = "data/demo_accounts.json"

# Verbatim prerequisite sentences from the catalog PDF, kept apart from the
# curated fixtures so the fixtures stay as published. Keyed by course id.
PREREQ_TEXT = Path("data/prereq_text_2025_26.json")

# Fields the schema models explicitly; everything else is preserved in `extra`.
MODELLED = {
    "id", "subject", "number", "title", "credits_min", "credits_max",
    "distribution", "competence_variants", "attributes", "prereq", "stub",
}


def read_prereq_text(catalog_year: str) -> dict[str, str]:
    if not PREREQ_TEXT.exists():
        return {}
    doc = json.loads(PREREQ_TEXT.read_text())
    if str(doc["catalog_year"]) != catalog_year:
        return {}
    return {normalize_id(k): v for k, v in doc["prereq_text"].items()}


def upsert(
    session: Session,
    catalog_year: str,
    entries: list[dict],
    equivalences: list[dict],
    retired: set[str],
) -> int:
    prereq_text = read_prereq_text(catalog_year)
    year = session.scalar(select(CatalogYear).where(CatalogYear.label == catalog_year))
    if year is None:
        year = CatalogYear(label=catalog_year)
        session.add(year)
        session.flush()

    def course_row(
        cid: str, *, stub: bool | None = None, is_retired: bool = False
    ) -> Course:
        row = session.scalar(select(Course).where(Course.course_id == cid))
        if row is None:
            subject, number = cid.split("-")
            row = Course(course_id=cid, subject=subject, number=int(number), stub=False)
            session.add(row)
            session.flush()
        # A fixture entry says definitively whether the course is a stub, so a
        # stub later curated for real (ECON-100) stops being one. Rows touched
        # only as equivalence endpoints or retired ids keep what they had.
        if stub is not None:
            row.stub = stub
        row.retired = is_retired or row.retired
        return row

    for entry in entries:
        cid = normalize_id(entry["id"])
        course = course_row(cid, stub=entry.get("stub", False))

        version = session.scalar(
            select(CourseVersion).where(
                CourseVersion.course_id == course.id,
                CourseVersion.catalog_year_id == year.id,
            )
        )
        if version is None:
            version = CourseVersion(course_id=course.id, catalog_year_id=year.id)
            session.add(version)

        version.title = entry["title"]
        version.credits_min = entry.get("credits_min")
        version.credits_max = entry.get("credits_max")
        version.distribution = entry.get("distribution")
        version.competence_variants = entry.get("competence_variants", [])
        version.attributes = entry.get("attributes", [])
        version.prereq_expr = parse(entry.get("prereq")).model_dump(exclude_none=True)
        version.prereq_raw = prereq_text.get(cid, "")
        version.extra = {k: v for k, v in entry.items() if k not in MODELLED}

    # Retired courses keep an identity row so references to them resolve, but
    # get no version in a year whose catalog no longer lists them.
    for cid in retired:
        course_row(cid, is_retired=True)

    for eq in equivalences:
        f, t = normalize_id(eq["from"]), normalize_id(eq["to"])
        course_row(f)
        course_row(t)
        exists = session.scalar(
            select(CourseEquivalence).where(
                CourseEquivalence.from_id == f,
                CourseEquivalence.to_id == t,
                CourseEquivalence.relation == eq["relation"],
            )
        )
        if exists is None:
            session.add(
                CourseEquivalence(
                    from_id=f, to_id=t, relation=eq["relation"], note=eq.get("note", "")
                )
            )

    session.commit()
    return len(entries)


def upsert_programs(session: Session, catalog_year: str, programs: list[dict]) -> int:
    """Requirements are derived wholly from the fixture, so a program version's
    rows are replaced on every seed rather than merged."""
    year = session.scalar(select(CatalogYear).where(CatalogYear.label == catalog_year))
    for p in programs:
        program = session.scalar(select(Program).where(Program.program_id == p["id"]))
        if program is None:
            program = Program(program_id=p["id"])
            session.add(program)
        program.kind, program.name, program.department = p["kind"], p["name"], p["department"]
        session.flush()

        version = session.scalar(
            select(ProgramVersion).where(
                ProgramVersion.program_id == program.id,
                ProgramVersion.catalog_year_id == year.id,
            )
        )
        if version is not None:
            # One SQL delete; ON DELETE CASCADE removes its requirement rows.
            # An ORM delete would also try to delete each child row itself,
            # after the database cascade had already removed them.
            session.execute(delete(ProgramVersion).where(ProgramVersion.id == version.id))
            session.flush()
        version = ProgramVersion(
            program_id=program.id,
            catalog_year_id=year.id,
            total_courses=p.get("total_courses", ""),
            notes=p.get("notes", ""),
        )
        session.add(version)
        session.flush()

        def insert(row: RequirementRow, parent: int | None, position: int) -> None:
            req = Requirement(
                program_version_id=version.id,
                parent_id=parent,
                position=position,
                label=row.label,
                rule_type=row.rule_type,
                spec=row.spec,
                notes=row.notes,
            )
            session.add(req)
            session.flush()
            for i, child in enumerate(row.children):
                insert(child, req.id, i)

        insert(p["root"], None, 0)
    session.commit()
    return len(programs)


def upsert_students(session: Session, catalog_year: str, students: list[dict]) -> int:
    """The fixture is the whole record for a seeded student: transcript, plan
    and declarations are replaced, not merged."""
    year = session.scalar(select(CatalogYear).where(CatalogYear.label == catalog_year))
    course_pk = {c.course_id: c.id for c in session.scalars(select(Course))}
    program_pk = {p.program_id: p.id for p in session.scalars(select(Program))}

    for s in students:
        student = session.scalar(select(Student).where(Student.student_key == s["id"]))
        if student is None:
            student = Student(student_key=s["id"])
            session.add(student)
        student.name = s["name"]
        student.catalog_year_id = year.id
        student.class_standing = s["class_standing"]
        student.expected_graduation = s["expected_graduation"]
        student.start_term = s.get("start_term")
        student.current_term = s.get("current_term")
        student.programs.clear()
        student.enrollments.clear()
        student.plan_items.clear()
        session.flush()

        student.programs.extend(
            StudentProgram(program_id=program_pk[p]) for p in s.get("programs", [])
        )
        student.enrollments.extend(
            Enrollment(
                course_id=course_pk[normalize_id(e["course_id"])],
                term=e["term"],
                status=e.get("status", "completed"),
                grade=e.get("grade"),
                competence=e.get("competence"),
            )
            for e in s.get("enrollments", [])
        )
        student.plan_items.extend(
            PlanItem(course_id=course_pk[normalize_id(e["course_id"])], term=e["term"])
            for e in s.get("plan", [])
        )
    session.commit()
    return len(students)


def read_accounts(path: Path, student_ids: set[str]) -> list[dict]:
    """A student account's key is its student's key; an advisor's advisees
    must be seeded students."""
    accounts = json.loads(path.read_text())["accounts"]
    problems = []
    for a in accounts:
        if a["role"] not in ("student", "advisor"):
            problems.append(f"account {a['key']}: bad role {a['role']!r}")
        if a["role"] == "student" and a["key"] not in student_ids:
            problems.append(f"student account {a['key']} has no seeded student")
        for s in a.get("advisees", []):
            if s not in student_ids:
                problems.append(f"advisor {a['key']} advises unknown student {s}")
    if problems:
        raise CatalogError(f"{len(problems)} problem(s) found:\n" + "\n".join(f"  {p}" for p in problems))
    return accounts


def upsert_accounts(session: Session, accounts: list[dict]) -> int:
    """Logins and advisor assignments, replaced from the fixture. Passwords
    are hashed here; the fixture's are public demo passwords. Only the
    assignments to fixture students are replaced: a student who signed up and
    picked a seeded advisor keeps that advisor across a re-seed."""
    from app.services.auth import hash_password

    students = {s.student_key: s for s in session.scalars(select(Student))}
    seeded = {k for a in accounts for k in a.get("advisees", [])} | {
        a["key"] for a in accounts if a["role"] == "student"
    }
    seeded_ids = [students[k].id for k in seeded if k in students]
    for a in accounts:
        account = session.scalar(select(Account).where(Account.key == a["key"]))
        if account is None:
            account = Account(key=a["key"])
            session.add(account)
        account.role = a["role"]
        student = students.get(a["key"]) if a["role"] == "student" else None
        account.student_id = student.id if student else None
        account.name = a.get("name") or (student.name if student else a["key"])
        account.password_hash = hash_password(a["password"])
        session.flush()
        session.execute(
            delete(AdvisorAssignment).where(
                AdvisorAssignment.advisor_id == account.id,
                AdvisorAssignment.student_id.in_(seeded_ids),
            )
        )
        session.add_all(
            AdvisorAssignment(advisor_id=account.id, student_id=students[k].id)
            for k in a.get("advisees", [])
        )
    session.commit()
    return len(accounts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("fixtures", nargs="*", default=None)
    ap.add_argument("--if-empty", action="store_true")
    ap.add_argument(
        "--check", action="store_true", help="validate only; never touch the database"
    )
    ap.add_argument("--programs", default=DEFAULT_PROGRAMS)
    ap.add_argument("--students", default=DEFAULT_STUDENTS)
    ap.add_argument("--accounts", default=DEFAULT_ACCOUNTS)
    args = ap.parse_args(argv)

    paths = [Path(p) for p in (args.fixtures or DEFAULT_FIXTURES)]
    missing = [p for p in paths if not p.exists()]
    if missing:
        print(f"fixture(s) not found: {', '.join(map(str, missing))}", file=sys.stderr)
        return 0 if args.if_empty else 1

    try:
        fixtures = check(paths)
        programs = (
            read_programs(Path(args.programs), fixtures)
            if Path(args.programs).exists()
            else []
        )
        students = (
            read_students(Path(args.students), fixtures, {p["id"] for p in programs})
            if Path(args.students).exists()
            else []
        )
        accounts = (
            read_accounts(Path(args.accounts), {s["id"] for s in students})
            if Path(args.accounts).exists()
            else []
        )
    except CatalogError as exc:
        print(f"refusing to load:\n{exc}", file=sys.stderr)
        return 1

    if args.check:
        print(
            f"ok: {len(fixtures.entries)} courses, {len(fixtures.equivalences)} "
            f"equivalences, {len(fixtures.retired)} retired ids, {len(programs)} "
            f"programs, {len(students)} students, {len(accounts)} accounts for {fixtures.catalog_year} "
            f"— no dangling references, no cycles"
        )
        return 0

    # Imported here so the --check path above never opens a session.
    from app.db import SessionLocal

    year = fixtures.catalog_year
    with SessionLocal() as session:
        # --if-empty decides per part, so a database seeded before programs and
        # students existed still picks them up on the next start.
        def empty(count_stmt) -> bool:
            return not args.if_empty or not session.scalar(count_stmt)

        if empty(
            select(func.count(CourseVersion.id))
            .join(CatalogYear)
            .where(CatalogYear.label == year)
        ):
            n = upsert(session, year, fixtures.entries, fixtures.equivalences, fixtures.retired)
            print(
                f"seeded {n} courses, {len(fixtures.equivalences)} equivalences, "
                f"{len(fixtures.retired)} retired ids into {year}"
            )
        else:
            print(f"{year} catalog already loaded — skipping")

        if programs and empty(
            select(func.count(ProgramVersion.id))
            .join(CatalogYear)
            .where(CatalogYear.label == year)
        ):
            print(f"seeded {upsert_programs(session, year, programs)} programs")
        if students and empty(select(func.count(Student.id))):
            print(f"seeded {upsert_students(session, year, students)} students")
        if accounts and empty(select(func.count(Account.id))):
            print(f"seeded {upsert_accounts(session, accounts)} accounts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
