"""Logging in, and the dependencies other routers use to know who is asking.

The catalog (courses, programs, the bare graph) is open to everyone. A
student's record is not: every read of one goes through `check_view`, so each
login sees only its own student, and an advisor only their advisees. The
fictional demo student is the exception, public so that demo mode works
without an account. Every write to a record goes through `owner`: only the
student, logged in.
"""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.models.account import Account, AdvisorAssignment, AdvisorInvite
from app.models.student import Student
from app.schemas.plan import AccountOut, LoginRequest, LoginResponse
from app.services import advising
from app.services.auth import make_token, read_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def current_account(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> Account | None:
    """The logged-in account, None when anonymous. A bad or expired token is
    401, not anonymous, so the client knows to log in again."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    key = read_token(token, settings.secret_key) if scheme.lower() == "bearer" else None
    account = session.scalar(select(Account).where(Account.key == key)) if key else None
    if account is None:
        raise HTTPException(401, "your login has expired; log in again")
    return account


def require_account(account: Account | None = Depends(current_account)) -> Account:
    if account is None:
        raise HTTPException(401, "log in first")
    return account


def policy_for(session: Session, account: Account) -> advising.Policy:
    """The advising rules, loaded for one account: an advisor's assignments
    and requests, or the requests waiting for a student."""
    if account.role != "advisor":
        asking = session.scalars(
            select(Account.key)
            .join(AdvisorInvite, AdvisorInvite.advisor_id == Account.id)
            .where(AdvisorInvite.student_id == account.student_id)
        )
        return advising.Policy({}, {a: {account.key} for a in asking})
    keys = session.scalars(
        select(Student.student_key)
        .join(AdvisorAssignment, AdvisorAssignment.student_id == Student.id)
        .where(AdvisorAssignment.advisor_id == account.id)
    )
    asked = session.scalars(
        select(Student.student_key)
        .join(AdvisorInvite, AdvisorInvite.student_id == Student.id)
        .where(AdvisorInvite.advisor_id == account.id)
    )
    return advising.Policy({account.key: set(keys)}, {account.key: set(asked)})


def as_actor(account: Account) -> advising.Account:
    return advising.Account(account.key, account.role)


def check_view(session: Session, account: Account | None, key: str) -> None:
    """Refuse a read of student `key`'s record unless it is the demo student,
    the account's own student, or an advisee. The refusal does not say whether
    the student exists."""
    if key == settings.demo_student:
        return
    if account is None:
        raise HTTPException(401, "log in to see a student's record")
    if account.role == "advisor":
        if policy_for(session, account).can_view(as_actor(account), key):
            return
        raise HTTPException(403, f"{account.name} does not advise this student")
    own = session.scalar(select(Student.student_key).where(Student.id == account.student_id))
    if own != key:
        raise HTTPException(403, "you can see only your own record")


def owner(
    key: str,
    account: Account | None = Depends(current_account),
    session: Session = Depends(get_session),
) -> Student:
    """For a write to a record: only the student it belongs to, logged in.
    Advisors read and comment; a demo session plans in memory and never edits
    the stored record."""
    if account is None:
        raise HTTPException(401, "log in to change your record")
    student = session.get(Student, account.student_id) if account.student_id else None
    if student is None or student.student_key != key:
        raise HTTPException(403, "you can change only your own record")
    return student


def viewable(
    key: str,
    account: Account | None = Depends(current_account),
    session: Session = Depends(get_session),
) -> None:
    """`check_view` as a dependency, for routes under /api/students/{key}."""
    check_view(session, account, key)


def account_out(session: Session, account: Account) -> AccountOut:
    student = session.get(Student, account.student_id) if account.student_id else None
    return AccountOut(
        key=account.key,
        role=account.role,
        name=account.name,
        student_key=student.student_key if student else None,
    )


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)) -> LoginResponse:
    account = session.scalar(select(Account).where(Account.key == body.key.strip()))
    if account is None or not verify_password(body.password, account.password_hash):
        # One message for both, so the form does not reveal which keys exist.
        raise HTTPException(401, "wrong login or password")
    return LoginResponse(token=make_token(account.key, settings.secret_key), account=account_out(session, account))


@router.get("/me", response_model=AccountOut)
def me(account: Account = Depends(require_account), session: Session = Depends(get_session)) -> AccountOut:
    return account_out(session, account)
