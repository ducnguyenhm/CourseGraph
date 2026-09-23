from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.catalog import CatalogYear, Course, CourseEquivalence, CourseVersion
from app.schemas.prereq import normalize_id


def versions_for(
    session: Session,
    catalog_year: str,
    subject: str | None = None,
    include_stubs: bool = False,
) -> list[CourseVersion]:
    stmt = (
        select(CourseVersion)
        .join(Course)
        .join(CatalogYear)
        .where(CatalogYear.label == catalog_year)
        .options(joinedload(CourseVersion.course))
        .order_by(Course.subject, Course.number)
    )
    if subject:
        stmt = stmt.where(Course.subject == subject.upper())
    if not include_stubs:
        stmt = stmt.where(Course.stub.is_(False))
    return list(session.scalars(stmt))


def version_by_id(
    session: Session, course_id: str, catalog_year: str
) -> CourseVersion | None:
    stmt = (
        select(CourseVersion)
        .join(Course)
        .join(CatalogYear)
        .where(
            Course.course_id == normalize_id(course_id),
            CatalogYear.label == catalog_year,
        )
        .options(joinedload(CourseVersion.course))
    )
    return session.scalars(stmt).first()


def equivalence_map(session: Session) -> dict[str, str]:
    """from_id -> to_id, for resolving retired course references."""
    return {
        e.from_id: e.to_id
        for e in session.scalars(
            select(CourseEquivalence).where(CourseEquivalence.relation == "renumber")
        )
    }
