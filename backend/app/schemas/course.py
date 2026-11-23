from pydantic import BaseModel


class CourseSummary(BaseModel):
    course_id: str
    label: str  # 'CSC 235' — display form of course_id
    title: str
    credits_min: float | None
    credits_max: float | None
    distribution: str | None
    competence_variants: list[str]
    attributes: list[str]
    stub: bool
    retired: bool


class CourseDetail(CourseSummary):
    catalog_year: str
    prereq_expr: dict
    # The catalog's prerequisite sentence, verbatim (typos kept), shown beside
    # the parsed tree. How an ambiguous sentence was read is in extra["notes"].
    prereq_raw: str
    extra: dict


class HealthResponse(BaseModel):
    status: str
    database: str
    catalog_year: str
    course_count: int


class ChainCourse(BaseModel):
    course_id: str
    label: str
    title: str
    # 'required': on every way to (or from) the selected course.
    # 'alternative': reached only through one branch of an 'or'.
    necessity: str
    stub: bool


class ChainResponse(BaseModel):
    course_id: str
    catalog_year: str
    upstream: list[ChainCourse]
    downstream: list[ChainCourse]
