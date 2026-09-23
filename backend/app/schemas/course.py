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
    # Curator's notes on how the catalog sentence was read — shown beside the
    # parsed tree, since several entries record a judgement call.
    prereq_raw: str
    extra: dict


class HealthResponse(BaseModel):
    status: str
    database: str
    catalog_year: str
    course_count: int
