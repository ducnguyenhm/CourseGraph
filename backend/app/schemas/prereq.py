"""Prerequisite expression trees.

The node vocabulary follows the curated catalog fixtures, whose `conventions`
block is the reference: course ids are SUBJECT-NUMBER with any competence suffix
stripped (CSC 235Q -> CSC-235), and `null` means no prerequisite.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

Level = Literal["first_year", "sophomore", "junior", "senior"]


def normalize_id(v: str) -> str:
    """'csc 235' / 'CSC235Q' / 'CSC-235' -> 'CSC-235'."""
    m = re.fullmatch(r"([A-Za-z]{2,5})[\s\-]*(\d{3})([A-Za-z]?)", v.strip())
    if not m:
        raise ValueError(f"course id must look like 'CSC-235', got {v!r}")
    return f"{m.group(1).upper()}-{m.group(2)}"


def display(course_id: str) -> str:
    return course_id.replace("-", " ")


class NoPrereq(BaseModel):
    type: Literal["none"] = "none"


class CourseReq(BaseModel):
    """Must be completed in an EARLIER term."""

    type: Literal["course"] = "course"
    course_id: str
    min_grade: str | None = None

    _norm = field_validator("course_id")(normalize_id)


class CoreqReq(BaseModel):
    """Completed earlier OR taken in the same term."""

    type: Literal["coreq"] = "coreq"
    course_id: str

    _norm = field_validator("course_id")(normalize_id)


class ConsentReq(BaseModel):
    """Never evaluates true or false on its own — it resolves to UNKNOWN and
    needs manual confirmation, so a plan containing one is flagged, not
    rejected."""

    type: Literal["consent"] = "consent"
    by: Literal["instructor", "chair", "department"] = "instructor"


class StandingReq(BaseModel):
    """CSC 197 is first-years ONLY, so this bounds in both directions."""

    type: Literal["standing"] = "standing"
    min_level: Level | None = None
    max_level: Level | None = None

    @model_validator(mode="after")
    def at_least_one_bound(self):
        if self.min_level is None and self.max_level is None:
            raise ValueError("standing needs min_level or max_level")
        return self


class CourseLevelReq(BaseModel):
    """`count` completed courses in `subject` numbered >= `min_number`."""

    type: Literal["course_level"] = "course_level"
    subject: str
    min_number: int
    count: int = 1


class ProgramReq(BaseModel):
    """A declared-program check, e.g. senior Mathematics majors only."""

    type: Literal["program"] = "program"
    program_id: str


class PlacementReq(BaseModel):
    type: Literal["placement"] = "placement"
    test: str
    min_score: float | None = None


class AndReq(BaseModel):
    type: Literal["and"] = "and"
    children: list[PrereqNode] = Field(min_length=2)


class OrReq(BaseModel):
    type: Literal["or"] = "or"
    children: list[PrereqNode] = Field(min_length=2)


PrereqNode = Annotated[
    Union[
        NoPrereq,
        CourseReq,
        CoreqReq,
        ConsentReq,
        StandingReq,
        CourseLevelReq,
        ProgramReq,
        PlacementReq,
        AndReq,
        OrReq,
    ],
    Field(discriminator="type"),
]

AndReq.model_rebuild()
OrReq.model_rebuild()

NONE: dict = {"type": "none"}


class _Root(BaseModel):
    node: PrereqNode


def parse(raw: dict | None) -> PrereqNode:
    """Validate a tree. `None` (the fixtures' 'no prerequisite') becomes NoPrereq."""
    return _Root(node=raw if raw else NONE).node


def course_ids(node: PrereqNode) -> set[str]:
    """Every course/coreq id anywhere in the tree."""
    if isinstance(node, (CourseReq, CoreqReq)):
        return {node.course_id}
    if isinstance(node, (AndReq, OrReq)):
        return set().union(*(course_ids(c) for c in node.children))
    return set()


def required_ids(node: PrereqNode) -> set[str]:
    """Ids on every satisfying path — the only edges that constrain ordering.

    An `or` contributes just what all branches share, and a coreq contributes
    nothing because it may be taken in the same term.
    """
    if isinstance(node, CourseReq):
        return {node.course_id}
    if isinstance(node, AndReq):
        return set().union(*(required_ids(c) for c in node.children))
    if isinstance(node, OrReq):
        sets = [required_ids(c) for c in node.children]
        return set.intersection(*sets) if sets else set()
    return set()
