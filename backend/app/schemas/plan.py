from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    key: str
    password: str


class AccountOut(BaseModel):
    key: str
    role: str  # student | advisor
    name: str
    # The student record a student account is attached to.
    student_key: str | None


class LoginResponse(BaseModel):
    token: str
    account: AccountOut


class DemoSessionOut(BaseModel):
    token: str
    student_key: str


class TakenOut(BaseModel):
    """A course already on the record, shown read-only in its past term."""

    course_id: str
    label: str
    title: str
    credits: float
    term: str
    status: str  # completed | in_progress


class PlacementOut(BaseModel):
    course_id: str
    label: str
    title: str
    credits: float
    term: str
    ok: bool
    unmet: list[str]
    confirm: list[str]
    message: str | None
    override: str | None
    overridable: bool
    open_comments: int = 0


class CheckOut(BaseModel):
    course_id: str
    label: str
    term: str
    ok: bool
    unmet: list[str]
    confirm: list[str]
    message: str | None
    load: float
    overloaded: bool
    overridable: bool


class Suggestion(BaseModel):
    """A course the semester estimate still counts on and the plan lacks."""

    course_id: str
    label: str
    title: str
    credits: float
    kind: str  # required | chosen | prerequisite
    reasons: list[str]
    round: int  # earliest term it could go in; 1 = the plan's first column


class PlanView(BaseModel):
    student_key: str
    name: str
    current_term: str | None
    expected_graduation: str
    # The planner's columns: every term through graduation (fall, Winter Term,
    # spring, May Term), plus any later term the plan already uses.
    terms: list[str]
    max_load: float
    # Winter and May Term: Extended Studies courses only, up to this many credits.
    short_max_load: float
    # The terms already gone through, from the first academic year on, and the
    # record's courses in them: the planner shows the whole degree.
    past_terms: list[str] = []
    taken: list[TakenOut] = []
    # Future terms the student took out of the plan; each can be put back.
    removed_terms: list[str] = []
    placements: list[PlacementOut]
    loads: dict[str, float]
    overloaded: list[str]
    problems: int
    suggestions: list[Suggestion]
    # Who is looking: may they move courses, and is it a throwaway demo copy?
    editable: bool
    demo: bool
    read_only_reason: str | None = None


class PlaceRequest(BaseModel):
    term: str = Field(examples=["2026FA"])
    # A justification note, to record a placement the prerequisites reject.
    override: str | None = None


class CheckRequest(BaseModel):
    course_id: str
    term: str


class CommentCreate(BaseModel):
    body: str
    course_id: str | None = None


class ReplyCreate(BaseModel):
    body: str


class CommentOut(BaseModel):
    id: int
    student_key: str
    author: str
    author_name: str
    body: str
    course_id: str | None
    label: str | None
    term: str | None
    resolved: bool
    created: datetime
    # The conversation this answers; None for the comment that opened it.
    parent_id: int | None = None


class AdviseeSummary(BaseModel):
    student_key: str
    name: str
    class_standing: str
    programs: list[str]
    expected_graduation: str
    credits_completed: float
    credits_in_progress: float
    credits_planned: float
    # The minimum-semester estimate against the terms left.
    min_terms: int
    terms_left: int
    on_time: bool
    # Courses the estimate still counts on that are not in the plan yet.
    unplanned: int
    plan_problems: int
    overloaded_terms: list[str]
    # Open conversations, and those whose last word is the student's.
    open_comments: int
    awaiting_reply: int = 0


class InviteCreate(BaseModel):
    # The student's login.
    student_key: str


class InviteOut(BaseModel):
    """A request to advise, as the advisor sees it (the student's login only:
    nothing of the record until they accept) or as the student sees it."""

    student_key: str
    advisor_key: str
    advisor_name: str
    created: datetime


class InviteAnswer(BaseModel):
    accept: bool


class AdvisorRef(BaseModel):
    key: str
    name: str


class MyAdvisors(BaseModel):
    """A student's advisors, and the advisors asking to be."""

    advisors: list[AdvisorRef]
    invites: list[InviteOut]
