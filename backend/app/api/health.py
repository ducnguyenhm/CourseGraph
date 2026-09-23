from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.models.catalog import CatalogYear, CourseVersion
from app.schemas.course import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(session: Session = Depends(get_session)) -> HealthResponse:
    # Actually round-trip to Postgres. A 200 that never touched the database
    # would not demonstrate what this endpoint claims to demonstrate.
    session.execute(text("SELECT 1"))

    year = settings.default_catalog_year
    count = session.scalar(
        select(func.count(CourseVersion.id))
        .join(CatalogYear)
        .where(CatalogYear.label == year)
    )
    return HealthResponse(
        status="ok",
        database="connected",
        catalog_year=year,
        course_count=count or 0,
    )
