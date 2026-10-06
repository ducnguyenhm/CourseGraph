"""Evaluate a prerequisite tree against one student.

Three-valued (Kleene) logic, because the catalog's own conventions make
instructor consent UNKNOWN — it needs a human to confirm — rather than false:

    FALSE < UNKNOWN < TRUE      and = min      or = max

Every result carries the specific conditions that are not yet met, so the UI
can say *why* a course is locked ("needs CSC 231"), and the Checkpoint 4
planner can name the unmet prerequisite in its rejection message.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import IntEnum

from app.schemas.prereq import (
    AndReq,
    ConsentReq,
    CoreqReq,
    CourseLevelReq,
    CourseReq,
    NoPrereq,
    OrReq,
    PlacementReq,
    PrereqNode,
    ProgramReq,
    StandingReq,
)
from app.services.validation import resolve


class Tri(IntEnum):
    FALSE = 0
    UNKNOWN = 1
    TRUE = 2


LEVELS = ["first_year", "sophomore", "junior", "senior"]


def label(course_id: str) -> str:
    return course_id.replace("-", " ")


@dataclass
class StudentFacts:
    """What a student has done, with every id already resolved.

    `completed` and `in_progress` include what each course *counts as*: CSC-122
    on the transcript also puts CSC-235 here (renumbered), and MATH-136 also
    puts MATH-151 (satisfies). `taken` is the de-duplicated transcript in
    current numbers, for counting courses without double-counting either.
    """

    completed: set[str]
    in_progress: set[str]
    planned: set[str]
    taken: set[str]
    standing: str
    programs: set[str]
    renumbering: dict[str, str] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        completed: Iterable[str],
        in_progress: Iterable[str],
        planned: Iterable[str],
        standing: str,
        programs: Iterable[str],
        equivalences: Iterable[tuple[str, str, str]],
    ) -> "StudentFacts":
        """equivalences: (from_id, to_id, relation) rows, every relation."""
        counts_as: dict[str, set[str]] = {}
        renumbering: dict[str, str] = {}
        for f, t, relation in equivalences:
            counts_as.setdefault(f, set()).add(t)
            if relation == "renumber":
                renumbering[f] = t

        def expand(ids: Iterable[str]) -> set[str]:
            out, stack = set(), list(ids)
            while stack:
                cid = stack.pop()
                if cid not in out:
                    out.add(cid)
                    stack.extend(counts_as.get(cid, ()))
            return out

        completed, in_progress = list(completed), list(in_progress)
        return cls(
            completed=expand(completed),
            in_progress=expand(in_progress),
            planned=set(planned),
            taken={resolve(c, renumbering) for c in completed + in_progress},
            standing=standing,
            programs=set(programs),
            renumbering=renumbering,
        )

    @property
    def satisfied(self) -> set[str]:
        # In-progress counts: a student registers for next term's course while
        # finishing its prerequisite.
        return self.completed | self.in_progress


@dataclass
class Result:
    value: Tri
    unmet: list[str] = field(default_factory=list)


def evaluate(node: PrereqNode, facts: StudentFacts) -> Result:
    sat = facts.satisfied

    def has(ref: str) -> bool:
        return ref in sat or resolve(ref, facts.renumbering) in sat

    if isinstance(node, NoPrereq):
        return Result(Tri.TRUE)
    if isinstance(node, CourseReq):
        if has(node.course_id):
            return Result(Tri.TRUE)
        return Result(Tri.FALSE, [label(resolve(node.course_id, facts.renumbering))])
    if isinstance(node, CoreqReq):
        if has(node.course_id):
            return Result(Tri.TRUE)
        return Result(Tri.UNKNOWN, [f"{label(node.course_id)} in the same term"])
    if isinstance(node, ConsentReq):
        return Result(Tri.UNKNOWN, [f"consent of the {node.by}"])
    if isinstance(node, PlacementReq):
        return Result(Tri.UNKNOWN, [f"{node.test} placement"])
    if isinstance(node, StandingReq):
        level = LEVELS.index(facts.standing)
        if node.min_level and level < LEVELS.index(node.min_level):
            return Result(Tri.FALSE, [f"{node.min_level.replace('_', '-')} standing"])
        if node.max_level and level > LEVELS.index(node.max_level):
            limit = node.max_level.replace("_", "-")
            return Result(Tri.FALSE, [f"{limit} students only" if node.max_level == "first_year" else f"{limit} standing or below"])
        return Result(Tri.TRUE)
    if isinstance(node, CourseLevelReq):
        have = sum(
            1
            for cid in facts.taken
            if cid.split("-")[0] == node.subject and int(cid.split("-")[1]) >= node.min_number
        )
        if have >= node.count:
            return Result(Tri.TRUE)
        return Result(
            Tri.FALSE, [f"{node.count - have} more {node.subject} course(s) numbered {node.min_number}+"]
        )
    if isinstance(node, ProgramReq):
        if node.program_id in facts.programs:
            return Result(Tri.TRUE)
        return Result(Tri.FALSE, [f"declared {node.program_id}"])
    if isinstance(node, AndReq):
        results = [evaluate(c, facts) for c in node.children]
        return Result(
            min(r.value for r in results),
            [u for r in results if r.value < Tri.TRUE for u in r.unmet],
        )
    if isinstance(node, OrReq):
        results = [evaluate(c, facts) for c in node.children]
        best = max(r.value for r in results)
        if best == Tri.TRUE:
            return Result(Tri.TRUE)
        # Report only the branches at the best level: for UNKNOWN, what would
        # confirm it; for FALSE, the choices still open.
        options = [" and ".join(r.unmet) for r in results if r.value == best]
        return Result(best, options if len(options) == 1 else ["one of: " + " / ".join(options)])
    raise TypeError(f"unhandled prerequisite node {type(node).__name__}")


def status(course_id: str, tree: PrereqNode, facts: StudentFacts) -> tuple[str, Result]:
    """completed > planned (in progress or in the plan) > eligible > locked.

    UNKNOWN is eligible: a course needing only consent is flagged for
    confirmation, not shown as blocked.
    """
    result = evaluate(tree, facts)
    if course_id in facts.completed:
        return "completed", result
    if course_id in facts.in_progress or course_id in facts.planned:
        return "planned", result
    return ("eligible" if result.value >= Tri.UNKNOWN else "locked"), result
