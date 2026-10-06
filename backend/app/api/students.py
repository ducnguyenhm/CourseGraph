from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.queries import all_equivalences
from app.db import get_session
from app.models.catalog import CatalogYear, Course
from app.models.program import Program
from app.models.student import Student
from app.schemas.program import EnrollmentOut, PlanItemOut, StudentDetail

router = APIRouter(prefix="/api/students", tags=["students"])


@router.get("", response_model=list[str])
def list_students(session: Session = Depends(get_session)) -> list[str]:
    return list(session.scalars(select(Student.student_key).order_by(Student.student_key)))


@router.get("/{key}", response_model=StudentDetail)
def get_student(key: str, session: Session = Depends(get_session)) -> StudentDetail:
    student = session.scalar(select(Student).where(Student.student_key == key))
    if student is None:
        raise HTTPException(404, f"no student {key!r}")
    ids = {c.id: c.course_id for c in session.scalars(select(Course))}
    programs = {p.id: p.program_id for p in session.scalars(select(Program))}
    counts_as: dict[str, list[str]] = {}
    for f, t, _ in all_equivalences(session):
        counts_as.setdefault(f, []).append(t)

    return StudentDetail(
        student_key=student.student_key,
        name=student.name,
        catalog_year=session.get(CatalogYear, student.catalog_year_id).label,
        class_standing=student.class_standing,
        expected_graduation=student.expected_graduation,
        programs=sorted(programs[sp.program_id] for sp in student.programs),
        enrollments=[
            EnrollmentOut(
                course_id=ids[e.course_id],
                label=ids[e.course_id].replace("-", " "),
                term=e.term,
                status=e.status,
                grade=e.grade,
                counts_as=counts_as.get(ids[e.course_id], []),
            )
            for e in sorted(student.enrollments, key=lambda e: (e.term[:4], e.term[4:] == "FA", ids[e.course_id]))
        ],
        plan=[
            PlanItemOut(course_id=ids[p.course_id], label=ids[p.course_id].replace("-", " "), term=p.term)
            for p in sorted(student.plan_items, key=lambda p: (p.term[:4], p.term[4:] == "FA"))
        ],
    )
