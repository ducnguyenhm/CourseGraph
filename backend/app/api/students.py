from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import owner, viewable
from app.api.queries import (
    all_equivalences,
    program_version,
    requirement_tree,
    student_engine,
    student_orderer,
    student_term,
)
from app.db import get_session
from app.models.catalog import CatalogYear, Course, CourseVersion
from app.models.program import Program
from app.models.account import Account
from app.models.student import Enrollment, Student, StudentProgram
from app.schemas.prereq import normalize_id, parse
from app.schemas.program import (
    AuditNode,
    AuditResponse,
    AuditSummary,
    BoundsOut,
    CreditTotals,
    EnrollmentCreate,
    EnrollmentOut,
    EnrollmentUpdate,
    ExploreResponse,
    NeedOut,
    PlanItemOut,
    ProgramImpact,
    ProgramProgress,
    ProgramSummary,
    ProgressResponse,
    RequirementLine,
    SemesterEstimate,
    SharedCourse,
    StudentDetail,
    StudentUpdate,
)
from app.services.explore import explore
from app.services.requirements import FOUNDATION_AREAS, Outcome, overlaps
from app.services.semesters import MAX_LOAD, current_term, estimate

# Every route here is about one student's record, so each checks who is
# asking: reads with `viewable` (the student, their advisor), writes with
# `owner` as well (the student alone).
router = APIRouter(prefix="/api/students", tags=["students"], dependencies=[Depends(viewable)])

# Within a year: Winter Term, spring, May Term, summer, fall.
TERM_ORDER = {"WI": 0, "SP": 1, "MY": 2, "SU": 3, "FA": 4}


def term_key(term: str) -> tuple[str, int]:
    return term[:4], TERM_ORDER.get(term[4:], 5)


def _student(session: Session, key: str) -> Student:
    student = session.scalar(select(Student).where(Student.student_key == key))
    if student is None:
        raise HTTPException(404, f"no student {key!r}")
    return student


def _version(session: Session, course_pk: int, year_id: int) -> CourseVersion | None:
    return session.scalar(
        select(CourseVersion).where(
            CourseVersion.course_id == course_pk, CourseVersion.catalog_year_id == year_id
        )
    )


def _areas(v: CourseVersion | None) -> list[str]:
    if v is None:
        return []
    tags = set(v.attributes or []) | ({v.distribution} if v.distribution else set())
    return sorted(tags & FOUNDATION_AREAS)


def _competence_options(v: CourseVersion | None) -> list[str]:
    if v is None:
        return []
    return sorted({*(v.competence_variants or []), *(v.attributes or [])} & {"W", "Q", "S"})


@router.get("/{key}", response_model=StudentDetail)
def get_student(key: str, session: Session = Depends(get_session)) -> StudentDetail:
    student = _student(session, key)
    courses = {c.id: c for c in session.scalars(select(Course))}
    programs = {p.id: p.program_id for p in session.scalars(select(Program))}
    counts_as: dict[str, list[str]] = {}
    for f, t, _ in all_equivalences(session):
        counts_as.setdefault(f, []).append(t)

    def enrollment(e: Enrollment) -> EnrollmentOut:
        c = courses[e.course_id]
        v = _version(session, c.id, student.catalog_year_id)
        credits = v.credits_max if v and v.credits_max is not None else (v.credits_min if v else None)
        return EnrollmentOut(
            id=e.id,
            course_id=c.course_id,
            label=c.course_id.replace("-", " "),
            title=v.title if v else "",
            credits=float(credits) if credits is not None else None,
            term=e.term,
            status=e.status,
            grade=e.grade,
            competence=e.competence,
            competence_options=_competence_options(v),
            areas=_areas(v),
            area_choice=e.area_choice,
            added_by_student=bool(v and (v.extra or {}).get("added_by") == "student"),
            counts_as=counts_as.get(c.course_id, []),
        )

    return StudentDetail(
        student_key=student.student_key,
        name=student.name,
        catalog_year=session.get(CatalogYear, student.catalog_year_id).label,
        class_standing=student.class_standing,
        expected_graduation=student.expected_graduation,
        start_term=student.start_term,
        current_term=student.current_term,
        current_term_auto=current_term((e.term, e.status) for e in student.enrollments),
        programs=sorted(programs[sp.program_id] for sp in student.programs),
        enrollments=[
            enrollment(e)
            for e in sorted(
                student.enrollments,
                key=lambda e: (term_key(e.term), courses[e.course_id].course_id),
            )
        ],
        plan=[
            PlanItemOut(
                id=p.id,
                course_id=courses[p.course_id].course_id,
                label=courses[p.course_id].course_id.replace("-", " "),
                term=p.term,
            )
            for p in sorted(student.plan_items, key=lambda p: term_key(p.term))
        ],
    )


# -- a student's own record --------------------------------------------------
#
# Records entered here live only in the database. They are never written back
# to the seed fixtures, so a real transcript cannot end up in the repository.


def set_programs(session: Session, student: Student, program_ids: list[str]) -> None:
    known = {p.program_id: p.id for p in session.scalars(select(Program))}
    unknown = [p for p in program_ids if p.upper() not in known]
    if unknown:
        raise HTTPException(422, f"unknown program(s): {', '.join(unknown)}")
    # The degree applies to everyone; it is not something one declares.
    student.programs.clear()
    session.flush()
    student.programs.extend(
        StudentProgram(program_id=known[p.upper()]) for p in dict.fromkeys(p.upper() for p in program_ids)
    )


@router.patch("/{key}", response_model=StudentDetail)
def update_student(
    key: str,
    body: StudentUpdate,
    student: Student = Depends(owner),
    session: Session = Depends(get_session),
) -> StudentDetail:
    """Change name, standing, start, current or graduation term, or declared
    programs. Moving graduation earlier or later changes the planner's terms."""
    changes = body.model_dump(exclude_unset=True)
    if "programs" in changes:
        set_programs(session, student, changes.pop("programs") or [])
    for field, value in changes.items():
        if value is None and field not in CLEARABLE:
            raise HTTPException(422, f"{field} cannot be empty")
        setattr(student, field, value)
    check_terms(student)
    if "name" in changes:
        # The login shows the same name.
        for account in session.scalars(select(Account).where(Account.student_id == student.id)):
            account.name = student.name
    session.commit()
    return get_student(key, session)


CLEARABLE = ("start_term", "current_term")


def check_terms(student: Student) -> None:
    """Start, current and graduation terms in order, where set."""
    named = [
        (label, t)
        for label, t in (
            ("start term", student.start_term),
            ("current term", student.current_term),
            ("expected graduation", student.expected_graduation),
        )
        if t
    ]
    for (a, ta), (b, tb) in zip(named, named[1:]):
        if term_key(ta) > term_key(tb):
            raise HTTPException(422, f"{a} {ta} is after {b} {tb}")


def _check_choices(v: CourseVersion | None, cid: str, competence: str | None, area: str | None) -> None:
    if competence and competence not in _competence_options(v):
        raise HTTPException(422, f"{cid} is not offered with {competence} competence")
    if area and area not in _areas(v):
        raise HTTPException(
            422, f"{cid} does not carry {area}; its areas are {', '.join(_areas(v)) or 'none'}"
        )


@router.post("/{key}/enrollments", response_model=StudentDetail, status_code=201)
def add_enrollment(
    key: str,
    body: EnrollmentCreate,
    student: Student = Depends(owner),
    session: Session = Depends(get_session),
) -> StudentDetail:
    """Add a course taken or in progress. A course the catalog does not have
    (most subjects outside CSC, MATH and ECON) needs `new_course`, and is
    stored as a stub marked as entered by the student."""
    try:
        cid = normalize_id(body.course_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    course = session.scalar(select(Course).where(Course.course_id == cid))
    version = _version(session, course.id, student.catalog_year_id) if course else None

    if version is None and not (course and course.retired):
        if body.new_course is None:
            raise HTTPException(
                422, f"{cid} is not in the catalog; describe it with new_course"
            )
        nc = body.new_course
        if course is None:
            subject, number = cid.split("-")
            course = Course(course_id=cid, subject=subject, number=int(number), stub=True)
            session.add(course)
            session.flush()
        areas = list(dict.fromkeys(nc.areas))
        version = CourseVersion(
            course_id=course.id,
            catalog_year_id=student.catalog_year_id,
            title=nc.title,
            credits_min=nc.credits,
            credits_max=nc.credits,
            # First area as the distribution, any "-or-" alternative as an
            # attribute: the same encoding the curated fixtures use.
            distribution=areas[0] if areas else None,
            attributes=areas[1:] + list(nc.attributes),
            competence_variants=sorted(set(nc.competence_variants) | ({body.competence} if body.competence else set())),
            prereq_expr=parse(None).model_dump(exclude_none=True),
            extra={"added_by": "student"},
        )
        session.add(version)
        session.flush()

    _check_choices(version, cid, body.competence, body.area_choice)
    if any(e.course_id == course.id and e.term == body.term for e in student.enrollments):
        raise HTTPException(409, f"{cid} is already on the record for {body.term}")
    student.enrollments.append(
        Enrollment(
            course_id=course.id,
            term=body.term,
            status=body.status,
            grade=body.grade,
            competence=body.competence,
            area_choice=body.area_choice,
        )
    )
    # A course now on the record no longer belongs in the plan.
    student.plan_items[:] = [p for p in student.plan_items if p.course_id != course.id]
    session.commit()
    return get_student(key, session)


def _enrollment(student: Student, enrollment_id: int) -> Enrollment:
    e = next((e for e in student.enrollments if e.id == enrollment_id), None)
    if e is None:
        raise HTTPException(404, f"no enrollment {enrollment_id} for {student.student_key!r}")
    return e


@router.patch("/{key}/enrollments/{enrollment_id}", response_model=StudentDetail)
def update_enrollment(
    key: str,
    enrollment_id: int,
    body: EnrollmentUpdate,
    student: Student = Depends(owner),
    session: Session = Depends(get_session),
) -> StudentDetail:
    """Change a course on the record. Send `area_choice: null` to hand the
    choice back to the engine."""
    e = _enrollment(student, enrollment_id)
    changes = body.model_dump(exclude_unset=True)
    course = session.get(Course, e.course_id)
    _check_choices(
        _version(session, e.course_id, student.catalog_year_id),
        course.course_id,
        changes.get("competence"),
        changes.get("area_choice"),
    )
    for field, value in changes.items():
        if value is None and field in ("term", "status"):
            raise HTTPException(422, f"{field} cannot be empty")
        setattr(e, field, value)
    session.commit()
    return get_student(key, session)


@router.delete("/{key}/enrollments/{enrollment_id}", status_code=204)
def delete_enrollment(
    enrollment_id: int,
    student: Student = Depends(owner),
    session: Session = Depends(get_session),
) -> Response:
    student.enrollments.remove(_enrollment(student, enrollment_id))
    session.commit()
    return Response(status_code=204)


def _node(o: Outcome) -> AuditNode:
    return AuditNode(
        label=o.label,
        rule_type=o.rule_type,
        spec=o.spec,
        notes=o.notes,
        state=o.state,
        applied=o.applied,
        need=o.need,
        have=o.have,
        remaining=o.remaining,
        in_courses=o.in_courses,
        options=o.options,
        chosen=o.chosen,
        children=[_node(c) for c in o.children],
    )


@router.get("/{key}/audit/{program_id}", response_model=AuditResponse)
def audit_program(
    key: str, program_id: str, session: Session = Depends(get_session)
) -> AuditResponse:
    """Evaluate the student against one program, declared or not, in the
    catalog they matriculated under."""
    student = session.scalar(select(Student).where(Student.student_key == key))
    if student is None:
        raise HTTPException(404, f"no student {key!r}")
    catalog_year = session.get(CatalogYear, student.catalog_year_id).label
    version = program_version(session, program_id, catalog_year)
    if version is None:
        raise HTTPException(404, f"{program_id} not found in catalog {catalog_year}")

    audit = student_engine(session, student, catalog_year).audit(
        version.program.program_id, requirement_tree(version)
    )
    return _audit_response(student, version.program, catalog_year, audit)


def _audit_response(student: Student, p: Program, catalog_year: str, audit) -> AuditResponse:
    leaves = list(audit.leaves())
    count = lambda state: sum(1 for o in leaves if o.state == state)  # noqa: E731
    rule_types: set[str] = set()

    def collect(o: Outcome) -> None:
        rule_types.add(o.rule_type)
        for c in o.children:
            collect(c)

    collect(audit.root)
    return AuditResponse(
        student_key=student.student_key,
        program=ProgramSummary(
            program_id=p.program_id, kind=p.kind, name=p.name, department=p.department
        ),
        catalog_year=catalog_year,
        declared=any(sp.program_id == p.id for sp in student.programs),
        summary=AuditSummary(
            complete=count("complete"),
            in_progress=count("in_progress"),
            planned=count("planned"),
            outstanding=count("outstanding"),
            rule_types=sorted(rule_types),
        ),
        root=_node(audit.root),
    )


DEGREE = "DEGREE-BA"


@router.get("/{key}/semesters", response_model=SemesterEstimate)
def semesters(
    key: str,
    add: list[str] = Query(default=[], description="Programs to evaluate as if declared."),
    max_load: float = Query(default=MAX_LOAD, gt=0, le=6, description="Credits per term."),
    session: Session = Depends(get_session),
) -> SemesterEstimate:
    """The minimum number of terms the student still needs for their declared
    programs and the B.A. degree (plus any `add`ed programs): the longer of
    the prerequisite chain and remaining credits over `max_load`."""
    student = _student(session, key)
    catalog_year = session.get(CatalogYear, student.catalog_year_id).label
    declared = {p.id: p.program_id for p in session.scalars(select(Program))}
    ids = [declared[sp.program_id] for sp in student.programs]
    added = [a.upper() for a in add if a.upper() not in ids]
    ids = list(dict.fromkeys(ids + [DEGREE] + added))

    engine = student_engine(session, student, catalog_year)
    audits = []
    for pid in ids:
        version = program_version(session, pid, catalog_year)
        if version is None:
            raise HTTPException(404, f"{pid} not found in catalog {catalog_year}")
        audits.append(engine.audit(pid, requirement_tree(version)))

    orderer = student_orderer(session, student, catalog_year, engine)
    r = estimate(
        engine,
        orderer,
        audits,
        current_term=student_term(student),
        graduation=student.expected_graduation,
        max_load=max_load,
        removed=student.removed_terms or [],
    )
    titles = _titles(session, student)
    return SemesterEstimate(
        student_key=student.student_key,
        programs=ids,
        added=added,
        current_term=r.current_term,
        expected_graduation=student.expected_graduation,
        terms_left=r.terms_left,
        chain_bound=r.chain_bound,
        chain=r.chain,
        remaining_credits=r.remaining_credits,
        credit_basis=r.credit_basis,
        max_load=max_load,
        credit_bound=r.credit_bound,
        estimate=r.estimate,
        binding=r.binding,
        feasible=r.feasible,
        extra_terms=max(0, r.estimate - r.terms_left),
        needs=[_need(n, titles) for n in r.needs],
        assumed=r.assumed,
        note=ESTIMATE_NOTE,
    )


ESTIMATE_NOTE = (
    "Assumes every course is offered every term. Where a requirement offers a choice, a "
    "course already needed elsewhere is assumed first, then the earliest open without "
    "permission."
)


def _titles(session: Session, student: Student) -> dict[str, str]:
    return {
        v.course.course_id: v.title
        for v in session.scalars(
            select(CourseVersion).where(CourseVersion.catalog_year_id == student.catalog_year_id)
        )
    }


def _need(n, titles: dict[str, str]) -> NeedOut:
    return NeedOut(
        course_id=n.course_id,
        label=n.course_id.replace("-", " ") if n.course_id else "Not in the loaded catalog",
        title=titles.get(n.course_id, "") if n.course_id else "",
        credits=n.credits,
        kind=n.kind,
        reasons=n.reasons,
        round=n.round,
    )


def _bounds(r) -> BoundsOut:
    return BoundsOut(
        estimate=r.estimate,
        chain_bound=r.chain_bound,
        chain=r.chain,
        credit_bound=r.credit_bound,
        remaining_credits=r.remaining_credits,
        credit_basis=r.credit_basis,
        binding=r.binding,
        feasible=r.feasible,
        extra_terms=max(0, r.estimate - r.terms_left),
    )


def _line(o: Outcome) -> RequirementLine:
    return RequirementLine(
        label=o.label,
        rule_type=o.rule_type,
        state=o.state,
        applied=o.applied,
        need=o.need,
        have=o.have,
        options=o.options,
    )


@router.get("/{key}/explore", response_model=ExploreResponse)
def explore_programs(
    key: str,
    add: list[str] = Query(description="Programs to evaluate as if declared, e.g. MINOR-DATA."),
    max_load: float = Query(default=MAX_LOAD, gt=0, le=6, description="Credits per term."),
    session: Session = Depends(get_session),
) -> ExploreResponse:
    """What adding one or more programs would cost the student: requirements
    already met, courses that count twice, new courses and credits, and the
    change in the minimum number of terms."""
    student = _student(session, key)
    catalog_year = session.get(CatalogYear, student.catalog_year_id).label
    by_pk = {p.id: p for p in session.scalars(select(Program))}
    declared_ids = [by_pk[sp.program_id].program_id for sp in student.programs] + [DEGREE]
    added_ids = [
        a for a in dict.fromkeys(x.upper() for x in add) if a not in declared_ids
    ]
    if not added_ids:
        raise HTTPException(422, "add at least one program the student has not declared")

    def load(pid: str):
        version = program_version(session, pid, catalog_year)
        if version is None:
            raise HTTPException(404, f"{pid} not found in catalog {catalog_year}")
        return pid, version.program.kind, requirement_tree(version)

    declared = [load(p) for p in declared_ids]
    added = [load(p) for p in added_ids]
    if any(kind == "degree" for _, kind, _ in added):
        raise HTTPException(422, "the degree requirements apply to everyone; add a major or minor")

    engine = student_engine(session, student, catalog_year)
    orderer = student_orderer(session, student, catalog_year, engine)
    x = explore(
        engine,
        orderer,
        declared,
        added,
        current_term=student_term(student),
        graduation=student.expected_graduation,
        max_load=max_load,
        removed=student.removed_terms or [],
    )
    titles = _titles(session, student)
    summaries = {p.program_id: p for p in by_pk.values()}
    shared = lambda d: [  # noqa: E731
        SharedCourse(course_id=c, label=c.replace("-", " "), programs=ps) for c, ps in d.items()
    ]
    return ExploreResponse(
        student_key=student.student_key,
        declared=declared_ids,
        added=added_ids,
        current_term=x.combined.current_term,
        expected_graduation=student.expected_graduation,
        terms_left=x.combined.terms_left,
        max_load=max_load,
        baseline=_bounds(x.baseline),
        combined=_bounds(x.combined),
        additional_terms=x.additional_terms,
        new_courses=[_need(n, titles) for n in x.new_courses],
        new_credits=x.new_credits,
        extra_credits_to_graduate=x.extra_credits_to_graduate,
        programs=[
            ProgramImpact(
                program=ProgramSummary(
                    program_id=i.program_id,
                    kind=i.kind,
                    name=summaries[i.program_id].name,
                    department=summaries[i.program_id].department,
                ),
                satisfied=[_line(o) for o in i.satisfied],
                underway=[_line(o) for o in i.underway],
                outstanding=[_line(o) for o in i.outstanding],
                shared_done=shared(i.shared_done),
                shared_needed=shared(i.shared_needed),
                new_courses=[_need(n, titles) for n in i.new_courses],
                new_credits=i.new_credits,
                warnings=i.warnings,
            )
            for i in x.impacts
        ],
        note=ESTIMATE_NOTE,
    )


@router.get("/{key}/progress", response_model=ProgressResponse)
def progress(key: str, session: Session = Depends(get_session)) -> ProgressResponse:
    """Every declared program and the degree, audited together: the degree
    progress view. Courses counting toward more than one program are listed
    in `shared`, since double counting decides multi-program feasibility."""
    student = _student(session, key)
    catalog_year = session.get(CatalogYear, student.catalog_year_id).label
    by_pk = {p.id: p for p in session.scalars(select(Program))}
    order = {"major": 0, "minor": 1, "degree": 2}
    programs = sorted(
        [by_pk[sp.program_id] for sp in student.programs]
        + [p for p in by_pk.values() if p.program_id == DEGREE],
        key=lambda p: (order.get(p.kind, 3), p.program_id),
    )
    engine = student_engine(session, student, catalog_year)

    def totals(ids) -> CreditTotals:
        sums = {"completed": 0.0, "in_progress": 0.0, "planned": 0.0}
        for cid in ids:
            e = engine.by_id[cid]
            sums[e.state] += e.credits
        return CreditTotals(**sums)

    out, audits = [], []
    for p in programs:
        version = program_version(session, p.program_id, catalog_year)
        if version is None:
            continue
        a = engine.audit(p.program_id, requirement_tree(version))
        audits.append((p, a))
        open_slots = sum(
            int(o.remaining) for o in a.leaves() if o.in_courses and o.rule_type != "credit_minimum"
        )
        out.append(
            ProgramProgress(
                audit=_audit_response(student, p, catalog_year, a),
                credits=totals(a.applied),
                courses_open=open_slots,
            )
        )

    degree_credits = next(
        (
            o.need
            for p, a in audits
            if p.kind == "degree"
            for o in a.leaves()
            if o.rule_type == "credit_minimum" and o.spec.get("scope", "record") == "record"
        ),
        0.0,
    )
    return ProgressResponse(
        student_key=student.student_key,
        name=student.name,
        catalog_year=catalog_year,
        class_standing=student.class_standing,
        expected_graduation=student.expected_graduation,
        credits=totals(e.course_id for e in engine.record.entries),
        credits_required=degree_credits,
        programs=out,
        shared=overlaps(a for p, a in audits if p.kind != "degree"),
    )
