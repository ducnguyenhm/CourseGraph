from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.queries import equivalence_map, versions_for
from app.config import settings
from app.db import get_session
from app.schemas.prereq import parse
from app.services.projection import build_graph

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("")
def get_graph(
    subject: str | None = Query(None, examples=["CSC"]),
    include_stubs: bool = False,
    catalog_year: str = Query(default_factory=lambda: settings.default_catalog_year),
    session: Session = Depends(get_session),
) -> dict:
    versions = versions_for(session, catalog_year, subject, include_stubs)
    courses = {
        v.course.course_id: (
            parse(v.prereq_expr),
            v.title,
            float(v.credits_min) if v.credits_min is not None else None,
            float(v.credits_max) if v.credits_max is not None else None,
        )
        for v in versions
    }
    return build_graph(courses, equivalence_map(session))
