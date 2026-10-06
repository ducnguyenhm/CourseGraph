from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.queries import equivalence_map, versions_for
from app.config import settings
from app.db import get_session
from app.models.catalog import CourseVersion
from app.schemas.course import ChainCourse, ChainResponse
from app.schemas.prereq import normalize_id, parse
from app.services.projection import build_graph
from app.services.reachability import Reachability

router = APIRouter(prefix="/api/graph", tags=["graph"])


def _credits(v: CourseVersion) -> tuple[float | None, float | None]:
    lo = float(v.credits_min) if v.credits_min is not None else None
    hi = float(v.credits_max) if v.credits_max is not None else None
    return lo, hi


@router.get("")
def get_graph(
    subject: list[str] | None = Query(None, examples=[["CSC", "MATH"]]),
    include_stubs: bool = False,
    catalog_year: str = Query(default_factory=lambda: settings.default_catalog_year),
    session: Session = Depends(get_session),
) -> dict:
    # Depth is computed over the whole catalog year and only then filtered.
    # Loading just the filtered subjects would drop cross-department edges, so
    # CSC-380 would lose MATH-141 and slide into the wrong column under
    # "CSC only".
    versions = versions_for(session, catalog_year, include_stubs=True)
    courses = {
        v.course.course_id: (parse(v.prereq_expr), v.title, *_credits(v))
        for v in versions
    }
    subjects = {s.upper() for s in subject} if subject else None
    visible = {
        v.course.course_id
        for v in versions
        if (subjects is None or v.course.subject in subjects)
        and (include_stubs or not v.course.stub)
    }
    return build_graph(courses, equivalence_map(session), visible=visible)


@router.get("/chain/{course_id}", response_model=ChainResponse)
def get_chain(
    course_id: str,
    catalog_year: str = Query(default_factory=lambda: settings.default_catalog_year),
    session: Session = Depends(get_session),
) -> ChainResponse:
    """Everything that must come before a course, and everything it opens up,
    each marked required or alternative. Always over the full catalog year."""
    cid = normalize_id(course_id)
    versions = {v.course.course_id: v for v in versions_for(session, catalog_year, include_stubs=True)}
    if cid not in versions:
        raise HTTPException(404, f"{course_id} not found in catalog {catalog_year}")

    reach = Reachability(
        {k: parse(v.prereq_expr) for k, v in versions.items()}, equivalence_map(session)
    )

    def row(reached) -> ChainCourse:
        v = versions.get(reached.course_id)
        return ChainCourse(
            course_id=reached.course_id,
            label=reached.course_id.replace("-", " "),
            title=v.title if v else "",
            necessity=reached.necessity,
            stub=v.course.stub if v else True,
        )

    return ChainResponse(
        course_id=cid,
        catalog_year=catalog_year,
        upstream=[row(r) for r in reach.upstream(cid)],
        downstream=[row(r) for r in reach.downstream(cid)],
    )
