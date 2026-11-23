"""The semester planner over HTTP, and demonstration-mode sessions.

A plan is read from the database, or, when the request carries an
`X-Demo-Session` token, from that visitor's private copy of the demo
student's plan, which is never written back. Who may move courses:

- a logged-in student, on their own plan;
- a demo session, on its copy of the demo plan.

Advisors see their advisees' plans read-only and comment on them instead.
Anyone else sees only the demo student's plan, read-only (`check_view`).
"""

from dataclasses import dataclass

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import check_view, current_account
from app.api.queries import student_planner, versions_for
from app.api.students import semesters as semester_estimate
from app.config import settings
from app.db import get_session
from app.models.account import Account, PlanComment
from app.models.catalog import CatalogYear, Course
from app.models.student import PlanItem, Student
from app.schemas.plan import (
    CheckOut,
    CheckRequest,
    DemoSessionOut,
    PlaceRequest,
    PlacementOut,
    PlanView,
    Suggestion,
    TakenOut,
)
from app.schemas.prereq import normalize_id
from app.services.demo import Sessions
from app.services.evaluator import label
from app.services.planner import Check, Placement, Planner, Rejected
from app.services.semesters import MAX_LOAD, SHORT_MAX_LOAD, past_terms, term_order

router = APIRouter(tags=["planner"])

# One API process under Docker Compose, so the sessions live in memory.
demo_sessions = Sessions([])

MAX_LOAD_QUERY = Query(default=MAX_LOAD, gt=0, le=6, description="Credits per term before an overload warning.")
DEMO_HEADER = Header(default=None, alias="X-Demo-Session")


@dataclass
class Access:
    student: Student
    catalog_year: str
    demo_token: str | None
    editable: bool
    reason: str | None  # why it is read-only, in words
    status: int = 403  # what a write answers when it is read-only


def _access(
    session: Session, key: str, account: Account | None, demo_token: str | None
) -> Access:
    if not demo_token:
        check_view(session, account, key)  # before the lookup: a refusal must not say who exists
    student = session.scalar(select(Student).where(Student.student_key == key))
    if student is None:
        raise HTTPException(404, f"no student {key!r}")
    year = session.get(CatalogYear, student.catalog_year_id).label
    if demo_token:
        if key != settings.demo_student:
            raise HTTPException(403, "a demo session plans only for the demo student")
        try:
            demo_sessions.plan(demo_token)
        except KeyError:
            # 410, not 401: the client starts a fresh demo session.
            raise HTTPException(410, "this demo session has ended; start a new one") from None
        return Access(student, year, demo_token, True, None)
    if account is not None and account.role == "advisor":
        return Access(student, year, None, False, "Advisors see a plan read-only and comment on it.")
    if account is not None and account.student_id == student.id:
        return Access(student, year, None, True, None)
    # Only the public demo student gets this far without being its owner.
    return Access(
        student, year, None, False, "Try the demo to change this plan.", 401 if account is None else 403
    )


def _writable(access: Access) -> None:
    if not access.editable:
        raise HTTPException(access.status, access.reason)


def _load(session: Session, access: Access) -> list[Placement]:
    if access.demo_token:
        return demo_sessions.plan(access.demo_token)
    ids = {c.id: c.course_id for c in session.scalars(select(Course))}
    return [Placement(ids[p.course_id], p.term, p.override_note) for p in access.student.plan_items]


def _save(session: Session, access: Access, plan: list[Placement]) -> None:
    if access.demo_token:
        demo_sessions.save(access.demo_token, plan)
        return
    pk = {c.course_id: c.id for c in session.scalars(select(Course))}
    access.student.plan_items.clear()
    session.flush()
    access.student.plan_items.extend(
        PlanItem(course_id=pk[p.course_id], term=p.term, override_note=p.override) for p in plan
    )
    session.commit()


def _removed(access: Access) -> list[str]:
    if access.demo_token:
        return demo_sessions.removed(access.demo_token)
    return list(access.student.removed_terms or [])


def _planner(session: Session, access: Access, max_load: float) -> Planner:
    return student_planner(
        session, access.student, access.catalog_year, max_load, removed=_removed(access)
    )


def _check_out(c: Check) -> CheckOut:
    return CheckOut(
        course_id=c.course_id,
        label=label(c.course_id),
        term=c.term,
        ok=c.ok,
        unmet=c.unmet,
        confirm=c.confirm,
        message=c.message,
        load=c.load,
        overloaded=c.overloaded,
        overridable=c.overridable,
    )


def _view(
    session: Session, access: Access, planner: Planner, plan: list[Placement], max_load: float
) -> PlanView:
    student = access.student
    titles = {
        v.course.course_id: v.title
        for v in versions_for(session, access.catalog_year, include_stubs=True)
    }
    review = planner.review(plan)
    # Open advisor comments per course. A demo session shows the demo
    # student's, read-only, so the walkthrough has something to show.
    open_comments = dict(
        session.execute(
            select(Course.course_id, func.count(PlanComment.id))
            .join(PlanComment, PlanComment.course_id == Course.id)
            .where(
                PlanComment.student_id == student.id,
                PlanComment.parent_id.is_(None),
                PlanComment.resolved.is_(False),
            )
            .group_by(Course.course_id)
        ).all()
    )

    def out(p: Placement) -> PlacementOut:
        c = review.checks[p.course_id]
        return PlacementOut(
            course_id=p.course_id,
            label=label(p.course_id),
            title=titles.get(p.course_id, ""),
            credits=planner.credits.get(p.course_id, 1.0),
            term=p.term,
            ok=c.ok,
            unmet=c.unmet,
            confirm=c.confirm,
            message=c.message,
            override=p.override,
            overridable=c.overridable,
            open_comments=open_comments.get(p.course_id, 0),
        )

    # The record, read-only, so every academic year of the degree shows.
    ids = {c.id: c.course_id for c in session.scalars(select(Course))}
    taken = [
        TakenOut(
            course_id=ids[e.course_id],
            label=label(ids[e.course_id]),
            title=titles.get(ids[e.course_id], ""),
            credits=planner.credits.get(ids[e.course_id], 1.0),
            term=e.term,
            status=e.status,
        )
        for e in sorted(student.enrollments, key=lambda e: (term_order(e.term), ids[e.course_id]))
    ]

    terms = planner.terms(student.expected_graduation)
    terms += [t for t in review.loads if t not in terms]
    terms.sort(key=term_order)

    # What the semester estimate still counts on, minus what the plan has.
    # The estimate reads the stored plan, so a demo session's own moves are
    # filtered here rather than re-estimated.
    planned = {p.course_id for p in plan}
    estimate = semester_estimate(student.student_key, add=[], max_load=max_load, session=session)
    suggestions = [
        Suggestion(
            course_id=n.course_id,
            label=n.label,
            title=n.title,
            credits=n.credits,
            kind=n.kind,
            reasons=n.reasons,
            round=n.round,
        )
        for n in estimate.needs
        if n.course_id and n.course_id not in planned and n.kind != "planned"
    ]
    return PlanView(
        student_key=student.student_key,
        name=student.name,
        current_term=planner.current_term,
        expected_graduation=student.expected_graduation,
        terms=terms,
        max_load=max_load,
        short_max_load=SHORT_MAX_LOAD,
        past_terms=past_terms(student.start_term, planner.current_term, [t.term for t in taken]),
        removed_terms=sorted(
            (t for t in planner.removed if term_order(t) >= term_order(planner.first)), key=term_order
        ),
        taken=taken,
        placements=[out(p) for p in sorted(plan, key=lambda p: (term_order(p.term), p.course_id))],
        loads=review.loads,
        overloaded=review.overloaded,
        problems=len(review.problems),
        suggestions=suggestions,
        editable=access.editable,
        demo=access.demo_token is not None,
        read_only_reason=access.reason,
    )


# -- the plan ----------------------------------------------------------------


@router.get("/api/students/{key}/plan", response_model=PlanView)
def get_plan(
    key: str,
    max_load: float = MAX_LOAD_QUERY,
    account: Account | None = Depends(current_account),
    demo: str | None = DEMO_HEADER,
    session: Session = Depends(get_session),
) -> PlanView:
    """The plan in columns, every placement checked, loads per term, and the
    courses the semester estimate still counts on that the plan lacks."""
    access = _access(session, key, account, demo)
    planner = _planner(session, access, max_load)
    return _view(session, access, planner, _load(session, access), max_load)


@router.post("/api/students/{key}/plan/check", response_model=CheckOut)
def check_placement(
    key: str,
    body: CheckRequest,
    max_load: float = MAX_LOAD_QUERY,
    account: Account | None = Depends(current_account),
    demo: str | None = DEMO_HEADER,
    session: Session = Depends(get_session),
) -> CheckOut:
    """Would this placement be accepted? Changes nothing: for showing a
    verdict while a course is dragged over a term."""
    access = _access(session, key, account, demo)
    planner = _planner(session, access, max_load)
    return _check_out(planner.check(_load(session, access), normalize_id(body.course_id), body.term))


@router.put("/api/students/{key}/plan/{course_id}", response_model=PlanView)
def place_course(
    key: str,
    course_id: str,
    body: PlaceRequest,
    max_load: float = MAX_LOAD_QUERY,
    account: Account | None = Depends(current_account),
    demo: str | None = DEMO_HEADER,
    session: Session = Depends(get_session),
) -> PlanView:
    """Place a course in a term, or move it there. A placement the
    prerequisites reject answers 409 with the check, naming what is unmet;
    send it again with an `override` note to record it anyway."""
    access = _access(session, key, account, demo)
    _writable(access)
    planner = _planner(session, access, max_load)
    try:
        plan = planner.place(_load(session, access), normalize_id(course_id), body.term, override=body.override)
    except Rejected as exc:
        raise HTTPException(409, _check_out(exc.check).model_dump()) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    _save(session, access, plan)
    return _view(session, access, planner, plan, max_load)


@router.delete("/api/students/{key}/plan/{course_id}", response_model=PlanView)
def remove_course(
    key: str,
    course_id: str,
    max_load: float = MAX_LOAD_QUERY,
    account: Account | None = Depends(current_account),
    demo: str | None = DEMO_HEADER,
    session: Session = Depends(get_session),
) -> PlanView:
    access = _access(session, key, account, demo)
    _writable(access)
    planner = _planner(session, access, max_load)
    plan = _load(session, access)
    cid = normalize_id(course_id)
    if not any(p.course_id == cid for p in plan):
        raise HTTPException(404, f"{label(cid)} is not in the plan")
    plan = planner.remove(plan, cid)
    _save(session, access, plan)
    return _view(session, access, planner, plan, max_load)


# -- terms ---------------------------------------------------------------------


@router.delete("/api/students/{key}/plan/terms/{term}", response_model=PlanView)
def remove_term(
    key: str,
    term: str,
    max_load: float = MAX_LOAD_QUERY,
    account: Account | None = Depends(current_account),
    demo: str | None = DEMO_HEADER,
    session: Session = Depends(get_session),
) -> PlanView:
    """Take a future term out of the plan: a semester away, a May Term
    skipped. Its courses have to go first (409), so nothing is lost quietly."""
    access = _access(session, key, account, demo)
    _writable(access)
    planner = _planner(session, access, max_load)
    plan = _load(session, access)
    try:
        planner.drop_term(plan, term)
    except ValueError as exc:
        held = any(p.term == term for p in plan)
        raise HTTPException(409 if held else 422, str(exc)) from None
    return _set_removed(session, access, sorted(planner.removed | {term}, key=term_order), max_load)


@router.put("/api/students/{key}/plan/terms/{term}", response_model=PlanView)
def restore_term(
    key: str,
    term: str,
    max_load: float = MAX_LOAD_QUERY,
    account: Account | None = Depends(current_account),
    demo: str | None = DEMO_HEADER,
    session: Session = Depends(get_session),
) -> PlanView:
    """Put a removed term back in the plan."""
    access = _access(session, key, account, demo)
    _writable(access)
    return _set_removed(session, access, [t for t in _removed(access) if t != term], max_load)


def _set_removed(session: Session, access: Access, terms: list[str], max_load: float) -> PlanView:
    if access.demo_token:
        demo_sessions.save_removed(access.demo_token, terms)
    else:
        access.student.removed_terms = terms
        session.commit()
    planner = _planner(session, access, max_load)
    return _view(session, access, planner, _load(session, access), max_load)


# -- demonstration mode --------------------------------------------------------


@router.post("/api/demo/session", response_model=DemoSessionOut, status_code=201)
def start_demo(session: Session = Depends(get_session)) -> DemoSessionOut:
    """A private copy of the demo student's plan, as it stands now. Nothing
    done under the token reaches the database."""
    student = session.scalar(select(Student).where(Student.student_key == settings.demo_student))
    if student is None:
        raise HTTPException(503, "the demo student is not seeded")
    ids = {c.id: c.course_id for c in session.scalars(select(Course))}
    seed = [Placement(ids[p.course_id], p.term, p.override_note) for p in student.plan_items]
    return DemoSessionOut(token=demo_sessions.start(seed), student_key=student.student_key)


@router.delete("/api/demo/session", status_code=204)
def end_demo(demo: str | None = DEMO_HEADER) -> Response:
    if demo:
        demo_sessions.end(demo)
    return Response(status_code=204)
