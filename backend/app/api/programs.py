from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.queries import courses_of, equivalence_map, program_version, versions_for
from app.config import settings
from app.db import get_session
from app.models.program import Program, Requirement
from app.schemas.prereq import parse
from app.schemas.program import (
    OrderedCourse,
    ProgramDetail,
    ProgramOrderResponse,
    ProgramSummary,
    RequirementNode,
)
from app.services.ordering import Orderer

router = APIRouter(prefix="/api/programs", tags=["programs"])


def _summary(p: Program) -> ProgramSummary:
    return ProgramSummary(
        program_id=p.program_id, kind=p.kind, name=p.name, department=p.department
    )


@router.get("", response_model=list[ProgramSummary])
def list_programs(session: Session = Depends(get_session)) -> list[ProgramSummary]:
    return [
        _summary(p)
        for p in session.scalars(select(Program).order_by(Program.kind, Program.program_id))
    ]


def _tree(rows: list[Requirement]) -> RequirementNode:
    children: dict[int | None, list[Requirement]] = {}
    for r in rows:
        children.setdefault(r.parent_id, []).append(r)

    def build(r: Requirement) -> RequirementNode:
        return RequirementNode(
            label=r.label,
            rule_type=r.rule_type,
            spec=r.spec,
            notes=r.notes,
            children=[build(c) for c in sorted(children.get(r.id, []), key=lambda c: c.position)],
        )

    return build(children[None][0])


@router.get("/{program_id}", response_model=ProgramDetail)
def get_program(
    program_id: str,
    catalog_year: str = Query(default_factory=lambda: settings.default_catalog_year),
    session: Session = Depends(get_session),
) -> ProgramDetail:
    version = program_version(session, program_id, catalog_year)
    if version is None:
        raise HTTPException(404, f"{program_id} not found in catalog {catalog_year}")
    courses = courses_of(session, version, catalog_year)
    return ProgramDetail(
        **_summary(version.program).model_dump(),
        catalog_year=catalog_year,
        total_courses=version.total_courses,
        notes=version.notes,
        requirements=_tree(version.requirements),
        fixed_courses=sorted(courses.fixed),
        elective_courses=sorted(courses.chosen),
    )


@router.get("/{program_id}/order", response_model=ProgramOrderResponse)
def get_program_order(
    program_id: str,
    catalog_year: str = Query(default_factory=lambda: settings.default_catalog_year),
    session: Session = Depends(get_session),
) -> ProgramOrderResponse:
    """A topological order of the courses a program names outright, plus
    everything they need, grouped into rounds that can be taken together."""
    version = program_version(session, program_id, catalog_year)
    if version is None:
        raise HTTPException(404, f"{program_id} not found in catalog {catalog_year}")
    versions = {
        v.course.course_id: v for v in versions_for(session, catalog_year, include_stubs=True)
    }
    orderer = Orderer(
        {k: parse(v.prereq_expr) for k, v in versions.items()}, equivalence_map(session)
    )
    fixed = courses_of(session, version, catalog_year).fixed
    result = orderer.program_order(fixed)

    def out(cid: str) -> OrderedCourse:
        v = versions.get(cid)
        return OrderedCourse(
            course_id=cid,
            label=cid.replace("-", " "),
            title=v.title if v else "",
            in_program=cid in fixed,
        )

    return ProgramOrderResponse(
        program_id=version.program.program_id,
        catalog_year=catalog_year,
        rounds=[[out(c) for c in r] for r in result.rounds],
        order=result.order,
        assumed=result.assumed,
        note=(
            "Courses the program names outright, plus everything they need. "
            "Electives drawn from a set are not ordered. Where a prerequisite "
            "offers a choice, the fastest branch that does not rely on "
            "permission is assumed."
        ),
    )
