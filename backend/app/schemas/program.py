from pydantic import BaseModel


class ProgramSummary(BaseModel):
    program_id: str
    kind: str
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
    course_id: str
    label: str
    term: str
    status: str
    grade: str | None
    # What this entry is credited as now: CSC-122 -> ["CSC-235"].
    counts_as: list[str]


class PlanItemOut(BaseModel):
    course_id: str
    label: str
    term: str


class StudentDetail(BaseModel):
    student_key: str
    name: str
    catalog_year: str
    class_standing: str
    expected_graduation: str
    programs: list[str]
    enrollments: list[EnrollmentOut]
    plan: list[PlanItemOut]
