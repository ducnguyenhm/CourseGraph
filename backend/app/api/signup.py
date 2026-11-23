"""Signing up: a new student account with its own, empty record.

Kept apart from `auth.py` because it builds a record with the helpers in
`students.py`, which itself depends on `auth.py`. Only students sign up; an
advisor account comes from the seed fixture, since an advisor who could
create themselves could also claim any student.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import account_out
from app.api.students import check_terms, set_programs
from app.config import settings
from app.db import get_session
from app.models.account import Account, AdvisorAssignment
from app.models.catalog import CatalogYear
from app.models.student import Student
from app.schemas.plan import LoginResponse
from app.schemas.program import AdvisorOut, SignupRequest
from app.services.auth import hash_password, make_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/advisors", response_model=list[AdvisorOut])
def advisors(session: Session = Depends(get_session)) -> list[AdvisorOut]:
    """The advisors a new student can pick from."""
    rows = session.scalars(select(Account).where(Account.role == "advisor").order_by(Account.name))
    return [AdvisorOut(key=a.key, name=a.name) for a in rows]


@router.post("/signup", response_model=LoginResponse, status_code=201)
def signup(body: SignupRequest, session: Session = Depends(get_session)) -> LoginResponse:
    """Create the account and record, and log in. The login is also the
    record's key, so it must be free as both."""
    if session.scalar(select(Account.id).where(Account.key == body.key)) or session.scalar(
        select(Student.id).where(Student.student_key == body.key)
    ):
        raise HTTPException(409, f"the login {body.key!r} is taken")
    advisor = None
    if body.advisor:
        advisor = session.scalar(
            select(Account).where(Account.key == body.advisor, Account.role == "advisor")
        )
        if advisor is None:
            raise HTTPException(422, f"no advisor {body.advisor!r}")

    year = session.scalar(select(CatalogYear).where(CatalogYear.label == settings.default_catalog_year))
    student = Student(
        student_key=body.key,
        name=body.name.strip(),
        catalog_year_id=year.id,
        class_standing=body.class_standing,
        expected_graduation=body.expected_graduation,
        start_term=body.start_term,
    )
    check_terms(student)
    session.add(student)
    session.flush()
    set_programs(session, student, body.programs)
    account = Account(
        key=body.key,
        role="student",
        name=student.name,
        password_hash=hash_password(body.password),
        student_id=student.id,
    )
    session.add(account)
    if advisor is not None:
        session.add(AdvisorAssignment(advisor_id=advisor.id, student_id=student.id))
    session.commit()
    return LoginResponse(token=make_token(account.key, settings.secret_key), account=account_out(session, account))
