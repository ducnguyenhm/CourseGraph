from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.queries import version_by_id, versions_for
from app.config import settings
from app.db import get_session
from app.models.catalog import CourseVersion
from app.schemas.course import CourseDetail, CourseSummary

router = APIRouter(prefix="/api/courses", tags=["courses"])


def _summary(v: CourseVersion) -> CourseSummary:
    return CourseSummary(
        course_id=v.course.course_id,
        label=v.course.course_id.replace("-", " "),
        title=v.title,
        credits_min=float(v.credits_min) if v.credits_min is not None else None,
        credits_max=float(v.credits_max) if v.credits_max is not None else None,
        distribution=v.distribution,
        competence_variants=v.competence_variants,
        attributes=v.attributes,
        stub=v.course.stub,
        retired=v.course.retired,
    )


@router.get("", response_model=list[CourseSummary])
def list_courses(
    subject: str | None = Query(None, examples=["CSC"]),
    include_stubs: bool = False,
    catalog_year: str = Query(default_factory=lambda: settings.default_catalog_year),
    session: Session = Depends(get_session),
) -> list[CourseSummary]:
    return [
        _summary(v) for v in versions_for(session, catalog_year, subject, include_stubs)
    ]


@router.get("/{course_id}", response_model=CourseDetail)
def get_course(
    course_id: str,
    catalog_year: str = Query(default_factory=lambda: settings.default_catalog_year),
    session: Session = Depends(get_session),
) -> CourseDetail:
    v = version_by_id(session, course_id, catalog_year)
    if v is None:
        raise HTTPException(404, f"{course_id} not found in catalog {catalog_year}")
    return CourseDetail(
        **_summary(v).model_dump(),
        catalog_year=catalog_year,
        prereq_expr=v.prereq_expr,
        prereq_raw=v.prereq_raw,
        extra=v.extra,
    )
