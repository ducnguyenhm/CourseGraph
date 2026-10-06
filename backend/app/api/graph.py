from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.queries import (
    courses_of,
    equivalence_map,
    program_version,
    student_facts,
    versions_for,
)
from app.config import settings
from app.db import get_session
from app.models.catalog import CourseVersion
from app.schemas.course import ChainCourse, ChainResponse
from app.schemas.prereq import normalize_id, parse
from app.services.evaluator import Tri, status
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
    program: str | None = Query(
        None,
        examples=["MAJOR-CSC"],
        description="Only this program's courses and everything leading to them.",
    ),
    student: str | None = Query(
        None, examples=["demo"], description="Add each course's status for this student."
    ),
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
    eq = equivalence_map(session)
    subjects = {s.upper() for s in subject} if subject else None
    visible = {
        v.course.course_id
        for v in versions
        if (subjects is None or v.course.subject in subjects)
        and (include_stubs or not v.course.stub)
    }

    in_program: dict[str, str] = {}
    if program:
        version = program_version(session, program, catalog_year)
        if version is None:
            raise HTTPException(404, f"{program} not found in catalog {catalog_year}")
        named = courses_of(session, version, catalog_year)
        in_program = {c: "elective" for c in named.chosen} | {c: "required" for c in named.fixed}
        reach = Reachability({k: t for k, (t, *_) in courses.items()}, eq)
        leads_in = {r.course_id for c in in_program for r in reach.upstream(c)}
        visible &= set(in_program) | leads_in

    facts = None
    if student:
        found = student_facts(session, student)
        if found is None:
            raise HTTPException(404, f"no student {student!r}")
        facts = found[1]

    graph = build_graph(courses, eq, visible=visible)
    for node in graph["nodes"]:
        node["in_program"] = in_program.get(node["id"])
        if facts is not None:
            name, result = status(node["id"], courses[node["id"]][0], facts)
            node["status"] = name
            # Eligible only if someone confirms (consent, a same-term coreq).
            node["conditional"] = name == "eligible" and result.value == Tri.UNKNOWN
            node["unmet"] = result.unmet
    return graph


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
