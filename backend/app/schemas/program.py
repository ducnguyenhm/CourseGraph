from typing import Literal

from pydantic import BaseModel, Field


class ProgramSummary(BaseModel):
    program_id: str
    kind: str  # major | minor | degree
    name: str
    department: str


class RequirementNode(BaseModel):
    label: str
    rule_type: str
    spec: dict
    notes: str
    children: list["RequirementNode"]


class ProgramDetail(ProgramSummary):
    catalog_year: str
    total_courses: str
    notes: str
    requirements: RequirementNode
    # Named outright, so every student in the program takes them.
    fixed_courses: list[str]
    # Drawn from a set ("three CSC courses at the 300 level"); some are taken.
    elective_courses: list[str]


class OrderedCourse(BaseModel):
    course_id: str
    label: str
    title: str
    # Named by the program itself, rather than pulled in as a prerequisite.
    in_program: bool


class ProgramOrderResponse(BaseModel):
    program_id: str
    catalog_year: str
    # rounds[n] can all be taken in term n+1; an empty round is a term the
    # chain must wait out (e.g. for senior standing).
    rounds: list[list[OrderedCourse]]
    order: list[str]
    # Branch choices and standing waits the order relies on, in words.
    assumed: list[str]
    note: str


class EnrollmentOut(BaseModel):
    id: int
    course_id: str
    label: str
    title: str
    credits: float | None
    term: str
    status: str
    grade: str | None
    competence: str | None
    # Competence this course can carry, for the edit form.
    competence_options: list[str]
    # Foundations areas the course carries; two or more means the student
    # may pin one with area_choice.
    areas: list[str]
    area_choice: str | None
    # Entered by a student, not curated from the catalog.
    added_by_student: bool
    # What this entry is credited as now: CSC-122 -> ["CSC-235"].
    counts_as: list[str]


class PlanItemOut(BaseModel):
    id: int
    course_id: str
    label: str
    term: str


class StudentDetail(BaseModel):
    student_key: str
    name: str
    catalog_year: str
    class_standing: str
    expected_graduation: str
    start_term: str | None
    # The student's own setting; None when it is worked out from the record.
    current_term: str | None
    # What the record says: the term in progress, else the latest.
    current_term_auto: str | None
    programs: list[str]
    enrollments: list[EnrollmentOut]
    plan: list[PlanItemOut]


class AuditNode(BaseModel):
    label: str
    rule_type: str
    spec: dict
    notes: str
    # complete | in_progress | planned | outstanding
    state: str
    # Courses meeting it (or, for a credit or attribute count, counted by it).
    applied: list[str]
    need: float
    have: float
    remaining: float
    # need/have are courses; false for credit and attribute counts, and for
    # groups made only of those.
    in_courses: bool
    # Catalog courses not on the record that would count here.
    options: list[str]
    # False on an any_of branch the evaluation did not use.
    chosen: bool
    children: list["AuditNode"]


class AuditSummary(BaseModel):
    # Leaf requirements of the branches used, by state.
    complete: int
    in_progress: int
    planned: int
    outstanding: int
    rule_types: list[str]


class AuditResponse(BaseModel):
    student_key: str
    program: ProgramSummary
    catalog_year: str
    declared: bool
    summary: AuditSummary
    root: AuditNode


TERM_PATTERN = r"^\d{4}(FA|SP|WI|MY|SU)$"
STUDENT_KEY_PATTERN = r"^[a-z0-9][a-z0-9_-]{1,31}$"
Standing = Literal["first_year", "sophomore", "junior", "senior"]


class StudentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    class_standing: Standing | None = None
    expected_graduation: str | None = Field(default=None, pattern=TERM_PATTERN)
    # null clears these two.
    start_term: str | None = Field(default=None, pattern=TERM_PATTERN)
    current_term: str | None = Field(default=None, pattern=TERM_PATTERN)
    programs: list[str] | None = None


class NewCourse(BaseModel):
    """A course not in the loaded catalog, entered from the student's own
    transcript. Stored as a stub, so it never appears on the graph."""

    title: str = Field(min_length=1, max_length=256)
    credits: float = Field(ge=0, le=2)
    # Foundations areas as printed: one, or two for "X-or-Y".
    areas: list[Literal["AH", "SM", "SS", "LA", "GL", "PPD"]] = []
    # Other catalog attributes: FYS, ES.
    attributes: list[Literal["FYS", "ES"]] = []
    competence_variants: list[Literal["W", "Q", "S"]] = []


class EnrollmentCreate(BaseModel):
    """A course taken or being taken. Future courses go through the planner
    (PUT /plan/{course}), which checks their prerequisites."""

    course_id: str = Field(examples=["REL-130"])
    term: str = Field(pattern=TERM_PATTERN, examples=["2024SP"])
    status: Literal["completed", "in_progress"] = "completed"
    grade: str | None = Field(default=None, max_length=4)
    competence: Literal["W", "Q", "S"] | None = None
    area_choice: Literal["AH", "SM", "SS", "LA", "GL", "PPD"] | None = None
    # Required when course_id is not in the catalog.
    new_course: NewCourse | None = None


class EnrollmentUpdate(BaseModel):
    term: str | None = Field(default=None, pattern=TERM_PATTERN)
    status: Literal["completed", "in_progress"] | None = None
    grade: str | None = Field(default=None, max_length=4)
    competence: Literal["W", "Q", "S"] | None = None
    area_choice: Literal["AH", "SM", "SS", "LA", "GL", "PPD"] | None = None


class SignupRequest(BaseModel):
    """A new student account and its (empty) record."""

    key: str = Field(pattern=STUDENT_KEY_PATTERN, examples=["alex"])
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    class_standing: Standing = "first_year"
    start_term: str | None = Field(default=None, pattern=TERM_PATTERN, examples=["2025FA"])
    expected_graduation: str = Field(pattern=TERM_PATTERN, examples=["2029SP"])
    programs: list[str] = []
    advisor: str | None = Field(default=None, description="An advisor account's key.")


class AdvisorOut(BaseModel):
    key: str
    name: str


class NeedOut(BaseModel):
    course_id: str | None  # None: a requirement no loaded course can meet
    label: str
    title: str
    credits: float
    # planned | required | chosen | prerequisite | unnamed
    kind: str
    # Which requirements it serves ("MAJOR-CSC: Three CSC courses ...") or
    # what it comes before.
    reasons: list[str]
    round: int  # earliest term it could be taken; 1 = next term


class SemesterEstimate(BaseModel):
    student_key: str
    programs: list[str]
    added: list[str]
    current_term: str | None
    expected_graduation: str
    terms_left: int
    chain_bound: int
    chain: list[str]
    remaining_credits: float
    credit_basis: str
    max_load: float
    credit_bound: int
    estimate: int
    # chain | credits | both | none
    binding: str
    feasible: bool
    # Terms beyond the expected graduation term, 0 if on time.
    extra_terms: int
    needs: list[NeedOut]
    assumed: list[str]
    note: str


class RequirementLine(BaseModel):
    label: str
    rule_type: str
    state: str
    applied: list[str]
    need: float
    have: float
    options: list[str]


class SharedCourse(BaseModel):
    course_id: str
    label: str
    # Declared programs it also counts toward.
    programs: list[str]


class ProgramImpact(BaseModel):
    program: ProgramSummary
    satisfied: list[RequirementLine]
    underway: list[RequirementLine]
    outstanding: list[RequirementLine]
    # On the record and already counting toward a declared program.
    shared_done: list[SharedCourse]
    # Still to take, and would count toward a declared program too.
    shared_needed: list[SharedCourse]
    new_courses: list[NeedOut]
    new_credits: float
    warnings: list[str]


class BoundsOut(BaseModel):
    estimate: int
    chain_bound: int
    chain: list[str]
    credit_bound: int
    remaining_credits: float
    credit_basis: str
    binding: str
    feasible: bool
    extra_terms: int


class ExploreResponse(BaseModel):
    student_key: str
    declared: list[str]
    added: list[str]
    current_term: str | None
    expected_graduation: str
    terms_left: int
    max_load: float
    baseline: BoundsOut
    combined: BoundsOut
    # combined.estimate - baseline.estimate
    additional_terms: int
    new_courses: list[NeedOut]
    new_credits: float
    # How much the total left to graduate grows; often less than new_credits,
    # because free electives absorb some of a new program.
    extra_credits_to_graduate: float
    programs: list[ProgramImpact]
    note: str


class CreditTotals(BaseModel):
    completed: float
    in_progress: float
    planned: float


class ProgramProgress(BaseModel):
    audit: AuditResponse
    # Credits of the courses the program's own rules have placed, by state.
    credits: CreditTotals
    # Course slots still open in the program's course requirements.
    courses_open: int


class ProgressResponse(BaseModel):
    student_key: str
    name: str
    catalog_year: str
    class_standing: str
    expected_graduation: str
    # Credits on the whole record, by state.
    credits: CreditTotals
    # The degree's credit minimum (31 for the B.A.).
    credits_required: float
    # Declared majors first, then minors, then the degree.
    programs: list[ProgramProgress]
    # Course -> every declared major or minor it counts toward, for courses in
    # two or more. The degree is left out: counting toward it is expected.
    shared: dict[str, list[str]]
