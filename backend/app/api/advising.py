"""The advisor dashboard and plan comments.

The rules are `services.advising.Policy`; this module loads the rows they
need and stores what they return.
"""

from dataclasses import replace

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.auth import as_actor, current_account, policy_for, require_account
from app.api.plans import demo_sessions
from app.api.queries import student_engine, student_planner
from app.api.students import semesters as semester_estimate
from app.config import settings
from app.db import get_session
from app.models.account import Account, AdvisorAssignment, AdvisorInvite, PlanComment
from app.models.catalog import CatalogYear, Course
from app.models.program import Program
from app.models.student import Student
from app.schemas.plan import (
    AdviseeSummary,
    AdvisorRef,
    CommentCreate,
    CommentOut,
    InviteAnswer,
    InviteCreate,
    InviteOut,
    MyAdvisors,
    ReplyCreate,
)
from app.schemas.prereq import normalize_id
from app.services import advising
from app.services.evaluator import label
from app.services.planner import Placement
from app.services.semesters import MAX_LOAD

router = APIRouter(tags=["advising"])


def _student(session: Session, key: str) -> Student:
    student = session.scalar(select(Student).where(Student.student_key == key))
    if student is None:
        raise HTTPException(404, f"no student {key!r}")
    return student


def _plan(session: Session, student: Student) -> list[Placement]:
    ids = {c.id: c.course_id for c in session.scalars(select(Course))}
    return [Placement(ids[p.course_id], p.term, p.override_note) for p in student.plan_items]


def _comments(session: Session, student: Student) -> list[tuple[advising.Comment, str]]:
    """The student's comments as the policy sees them, with author names."""
    ids = {c.id: c.course_id for c in session.scalars(select(Course))}
    authors = {a.id: a for a in session.scalars(select(Account))}
    rows = session.scalars(select(PlanComment).where(PlanComment.student_id == student.id))
    return [
        (
            advising.Comment(
                student.student_key,
                authors[r.author_id].key,
                r.body,
                ids.get(r.course_id) if r.course_id else None,
                r.term,
                r.resolved,
                r.created_at,
                id=r.id,
                parent_id=r.parent_id,
            ),
            authors[r.author_id].name,
        )
        for r in rows
    ]


def _out(c: advising.Comment, author_name: str) -> CommentOut:
    return CommentOut(
        id=c.id,
        student_key=c.student_key,
        author=c.author,
        author_name=author_name,
        body=c.body,
        course_id=c.course_id,
        label=label(c.course_id) if c.course_id else None,
        term=c.term,
        resolved=c.resolved,
        created=c.created,
        parent_id=c.parent_id,
    )


def _forbidden(exc: advising.Forbidden) -> HTTPException:
    return HTTPException(403, str(exc))


# -- dashboard -------------------------------------------------------------------


@router.get("/api/advisor/advisees", response_model=list[AdviseeSummary])
def advisees(
    account: Account = Depends(require_account), session: Session = Depends(get_session)
) -> list[AdviseeSummary]:
    """Each advisee at a glance: programs, credits, whether the minimum
    semesters still fit before graduation, and what the plan lacks."""
    policy = policy_for(session, account)
    try:
        keys = policy.advisees(as_actor(account))
    except advising.Forbidden as exc:
        raise _forbidden(exc) from None
    programs = {p.id: p.program_id for p in session.scalars(select(Program))}
    out = []
    for key in keys:
        student = _student(session, key)
        year = session.get(CatalogYear, student.catalog_year_id).label
        credits = {"completed": 0.0, "in_progress": 0.0, "planned": 0.0}
        for e in student_engine(session, student, year).record.entries:
            credits[e.state] += e.credits
        estimate = semester_estimate(key, add=[], max_load=MAX_LOAD, session=session)
        review = student_planner(session, student, year).review(_plan(session, student))
        open_comments = session.scalar(
            select(func.count(PlanComment.id)).where(
                PlanComment.student_id == student.id,
                PlanComment.parent_id.is_(None),
                PlanComment.resolved.is_(False),
            )
        )
        awaiting = advising.awaiting_advisor(c for c, _ in _comments(session, student))
        out.append(
            AdviseeSummary(
                student_key=key,
                name=student.name,
                class_standing=student.class_standing,
                programs=[programs[sp.program_id] for sp in student.programs],
                expected_graduation=student.expected_graduation,
                credits_completed=credits["completed"],
                credits_in_progress=credits["in_progress"],
                credits_planned=credits["planned"],
                min_terms=estimate.estimate,
                terms_left=estimate.terms_left,
                on_time=estimate.feasible,
                unplanned=sum(1 for n in estimate.needs if n.kind != "planned"),
                plan_problems=len(review.problems),
                overloaded_terms=review.overloaded,
                open_comments=open_comments or 0,
                awaiting_reply=awaiting,
            )
        )
    return out


# -- choosing advisees -------------------------------------------------------------
# The rules are Policy.invite / answer_invite / release; these store the result.


def _account_of(session: Session, key: str) -> Account | None:
    return session.scalar(select(Account).where(Account.key == key))


def _invites_out(session: Session, rows) -> list[InviteOut]:
    out = []
    for r in rows:
        advisor = session.get(Account, r.advisor_id)
        student = session.get(Student, r.student_id)
        out.append(InviteOut(student_key=student.student_key, advisor_key=advisor.key, advisor_name=advisor.name, created=r.created_at))
    return sorted(out, key=lambda i: i.created)


@router.get("/api/advisor/invites", response_model=list[InviteOut])
def my_invites(account: Account = Depends(require_account), session: Session = Depends(get_session)) -> list[InviteOut]:
    """The advisor's requests the students have not answered yet."""
    if account.role != "advisor":
        raise HTTPException(403, "only advisors send requests")
    return _invites_out(session, session.scalars(select(AdvisorInvite).where(AdvisorInvite.advisor_id == account.id)))


@router.post("/api/advisor/invites", response_model=InviteOut, status_code=201)
def send_invite(
    body: InviteCreate, account: Account = Depends(require_account), session: Session = Depends(get_session)
) -> InviteOut:
    """Ask a student, by their login, to be their advisor. Nothing of the
    record is visible until they accept."""
    key = body.student_key.strip()
    students = session.scalars(select(Account.key).where(Account.role == "student"))
    try:
        policy_for(session, account).invite(as_actor(account), key, students)
    except advising.Forbidden as exc:
        raise _forbidden(exc) from None
    except ValueError as exc:
        raise HTTPException(409 if "already" in str(exc) else 404, str(exc)) from None
    row = AdvisorInvite(advisor_id=account.id, student_id=_account_of(session, key).student_id)
    session.add(row)
    session.commit()
    return _invites_out(session, [row])[0]


@router.delete("/api/advisor/invites/{student_key}", status_code=204)
def withdraw_invite(
    student_key: str, account: Account = Depends(require_account), session: Session = Depends(get_session)
) -> None:
    try:
        policy_for(session, account).cancel_invite(as_actor(account), student_key)
    except advising.Forbidden as exc:
        raise _forbidden(exc) from None
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None
    student = _student(session, student_key)
    session.execute(
        delete(AdvisorInvite).where(AdvisorInvite.advisor_id == account.id, AdvisorInvite.student_id == student.id)
    )
    session.commit()


@router.delete("/api/advisor/advisees/{student_key}", status_code=204)
def remove_advisee(
    student_key: str, account: Account = Depends(require_account), session: Session = Depends(get_session)
) -> None:
    """Take a student off the advisor's list. The record, the plan and the
    comments stay; the advisor can no longer open them."""
    try:
        policy_for(session, account).release(as_actor(account), student_key)
    except advising.Forbidden as exc:
        raise _forbidden(exc) from None
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None
    student = _student(session, student_key)
    session.execute(
        delete(AdvisorAssignment).where(
            AdvisorAssignment.advisor_id == account.id, AdvisorAssignment.student_id == student.id
        )
    )
    session.commit()


def _my_advisors(session: Session, account: Account) -> MyAdvisors:
    advisors = session.scalars(
        select(Account)
        .join(AdvisorAssignment, AdvisorAssignment.advisor_id == Account.id)
        .where(AdvisorAssignment.student_id == account.student_id)
        .order_by(Account.name)
    )
    invites = session.scalars(select(AdvisorInvite).where(AdvisorInvite.student_id == account.student_id))
    return MyAdvisors(advisors=[AdvisorRef(key=a.key, name=a.name) for a in advisors], invites=_invites_out(session, invites))


@router.get("/api/me/advisors", response_model=MyAdvisors)
def my_advisors(account: Account = Depends(require_account), session: Session = Depends(get_session)) -> MyAdvisors:
    """A student's advisors, and the requests waiting for their answer."""
    if account.role != "student":
        raise HTTPException(403, "only students have advisors")
    return _my_advisors(session, account)


@router.post("/api/me/advisors/{advisor_key}", response_model=MyAdvisors)
def answer_invite(
    advisor_key: str,
    body: InviteAnswer,
    account: Account = Depends(require_account),
    session: Session = Depends(get_session),
) -> MyAdvisors:
    """Accept or decline an advisor's request. A yes lets them see the record."""
    try:
        accepted = policy_for(session, account).answer_invite(as_actor(account), advisor_key, body.accept)
    except advising.Forbidden as exc:
        raise _forbidden(exc) from None
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None
    advisor = _account_of(session, advisor_key)
    session.execute(
        delete(AdvisorInvite).where(AdvisorInvite.advisor_id == advisor.id, AdvisorInvite.student_id == account.student_id)
    )
    if accepted:
        session.add(AdvisorAssignment(advisor_id=advisor.id, student_id=account.student_id))
    session.commit()
    return _my_advisors(session, account)


# -- comments ----------------------------------------------------------------------


@router.get("/api/students/{key}/comments", response_model=list[CommentOut])
def list_comments(
    key: str,
    account: Account | None = Depends(current_account),
    demo: str | None = Header(default=None, alias="X-Demo-Session"),
    session: Session = Depends(get_session),
) -> list[CommentOut]:
    """Comments on a plan, unresolved first. The student and their advisors
    see them; a demo session sees the demo student's, read-only."""
    if account is not None:
        viewer, policy = as_actor(account), policy_for(session, account)
    elif demo and key == settings.demo_student and _live(demo):
        # The demo visitor sees the plan as its student would.
        viewer, policy = advising.Account(key, "student"), advising.Policy({})
    else:
        raise HTTPException(401, "log in to see the comments on this plan")
    student = _student(session, key)
    comments = _comments(session, student)
    names = {c.id: name for c, name in comments}
    try:
        thread = policy.thread(viewer, key, [c for c, _ in comments])
    except advising.Forbidden as exc:
        raise _forbidden(exc) from None
    return [_out(c, names[c.id]) for c in thread]


def _live(token: str) -> bool:
    try:
        demo_sessions.plan(token)
    except KeyError:
        return False
    return True


@router.post("/api/students/{key}/comments", response_model=CommentOut, status_code=201)
def add_comment(
    key: str,
    body: CommentCreate,
    account: Account = Depends(require_account),
    session: Session = Depends(get_session),
) -> CommentOut:
    """A comment that opens a conversation on the plan, or on one course in
    it: by an advisor, or by the student asking about their own plan."""
    student = _student(session, key)
    course_id = normalize_id(body.course_id) if body.course_id else None
    try:
        c = policy_for(session, account).comment(
            as_actor(account), key, _plan(session, student), body.body, course_id
        )
    except advising.Forbidden as exc:
        raise _forbidden(exc) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    pk = session.scalar(select(Course.id).where(Course.course_id == c.course_id)) if c.course_id else None
    row = PlanComment(student_id=student.id, author_id=account.id, body=c.body, course_id=pk, term=c.term)
    session.add(row)
    session.commit()
    session.refresh(row)
    return _out(
        advising.Comment(key, account.key, c.body, c.course_id, c.term, False, row.created_at, id=row.id),
        account.name,
    )


@router.post("/api/comments/{comment_id}/replies", response_model=CommentOut, status_code=201)
def reply_to_comment(
    comment_id: int,
    body: ReplyCreate,
    account: Account = Depends(require_account),
    session: Session = Depends(get_session),
) -> CommentOut:
    """An answer in a conversation, by the student or their advisor. Answering
    an answer joins the same conversation."""
    row = session.get(PlanComment, comment_id)
    if row is None:
        raise HTTPException(404, f"no comment {comment_id}")
    root_id = row.parent_id or row.id
    student = session.get(Student, row.student_id)
    parent = next(c for c, _ in _comments(session, student) if c.id == root_id)
    try:
        c = policy_for(session, account).reply(as_actor(account), parent, body.body)
    except advising.Forbidden as exc:
        raise _forbidden(exc) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    root = session.get(PlanComment, root_id)
    reply = PlanComment(
        student_id=student.id,
        author_id=account.id,
        body=c.body,
        course_id=root.course_id,
        term=c.term,
        parent_id=root_id,
    )
    session.add(reply)
    session.commit()
    session.refresh(reply)
    return _out(replace(c, id=reply.id, created=reply.created_at), account.name)


@router.post("/api/comments/{comment_id}/resolve", response_model=CommentOut)
def resolve_comment(
    comment_id: int,
    account: Account = Depends(require_account),
    session: Session = Depends(get_session),
) -> CommentOut:
    row = session.get(PlanComment, comment_id)
    if row is None:
        raise HTTPException(404, f"no comment {comment_id}")
    student = session.get(Student, row.student_id)
    c, author_name = next((c, n) for c, n in _comments(session, student) if c.id == comment_id)
    try:
        done = policy_for(session, account).resolve(as_actor(account), c)
    except advising.Forbidden as exc:
        raise _forbidden(exc) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    row.resolved = done.resolved
    session.commit()
    return _out(done, author_name)
