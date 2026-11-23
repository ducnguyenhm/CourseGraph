"""The semester planner: is this course allowed in this term of this plan?

A plan is a list of placements, one per course, each in a future term: fall,
Winter Term, spring or May Term (Winter and May Term since 2026-11-18).
Placing a course checks its prerequisite tree with the evaluator against the
record *as it will stand by that term*:

- completed and in-progress courses count, as they do on the graph;
- so does every course placed in an **earlier** term (an overridden one
  too: the student means to take it there);
- a corequisite also counts beside a course placed in the **same** term;
- standing is projected: a term meets `min_level` once the semesters (fall
  and spring; a Winter Term or summer is not one) finished before it reach
  STANDING_ROUNDS[min_level] - terms_elapsed, the same rule the program
  order and the semester estimate use.

A student may take any future term out of the plan (a semester away, an
internship, a May Term skipped): it is no longer a column and takes no course
until put back. Standing and the semester estimate still count it.

Winter and May Term are short terms: they take Extended Studies courses only,
at most SHORT_MAX_LOAD credits. Both are refusals no note can excuse, like a
past term: a regular course is simply not taught then.

Consent and placement tests stay UNKNOWN, as in the evaluator: accepted,
listed under `confirm`. A term over `max_load` credits is a warning, never a
rejection. An override is a justification note recording a placement the
prerequisites would reject (instructor consent, a waiver); it does not cover
the plan's own rules: past terms, courses already on the record.

Pure Python with no database, like the evaluator. Plans are never changed in
place, so a demo session can hand out copies safely.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace

from app.schemas.prereq import PrereqNode
from app.services.evaluator import LEVELS, StudentFacts, Tri, evaluate, label
from app.services.ordering import STANDING_ROUNDS
from app.services.semesters import (
    MAX_LOAD,
    PLAN_KINDS,
    SHORT_KINDS,
    SHORT_MAX_LOAD,
    next_plan_term,
    semesters_between,
    term_order,
)
from app.services.validation import resolve

__all__ = ["MAX_LOAD", "Check", "Placement", "Planner", "Rejected", "Review"]


@dataclass(frozen=True)
class Placement:
    course_id: str
    term: str  # '2026SP'
    # Why a placement the prerequisites reject was recorded anyway.
    override: str | None = None


@dataclass
class Check:
    course_id: str
    term: str
    ok: bool
    # What is still missing by that term, in the evaluator's words ("CSC 231").
    unmet: list[str] = field(default_factory=list)
    # Accepted, but someone has to confirm it ("consent of the instructor").
    confirm: list[str] = field(default_factory=list)
    message: str | None = None
    load: float = 0.0  # the term's credits with this course in it
    overloaded: bool = False
    # False when the problem is the plan itself, which no note can excuse.
    overridable: bool = True
    override: str | None = None


@dataclass
class Review:
    checks: dict[str, Check]
    loads: dict[str, float]
    overloaded: list[str]
    # Placements that fail and were not recorded on purpose.
    problems: list[Check]


class Rejected(Exception):
    def __init__(self, check: Check):
        super().__init__(check.message)
        self.check = check


class Planner:
    def __init__(
        self,
        trees: dict[str, PrereqNode],
        facts: StudentFacts,
        *,
        current_term: str,
        terms_elapsed: int,
        credits: dict[str, float] | None = None,
        max_load: float = MAX_LOAD,
        equivalences: Iterable[tuple[str, str, str]] = (),
        extended: Iterable[str] = (),
        removed: Iterable[str] = (),
    ):
        """facts: the record; its `planned` is ignored, the plan passed to
        each call is what counts. equivalences: (from, to, relation) rows, so
        a planned MATH-136 also counts as MATH-151, as on the record.
        extended: the Extended Studies courses (catalog attribute ES), the
        only ones Winter and May Term take. removed: terms the student took
        out of the plan."""
        self.trees = trees
        self.facts = facts
        self.current_term = current_term
        self.terms_elapsed = terms_elapsed
        self.credits = credits or {}
        self.max_load = max_load
        self.extended = frozenset(extended)
        self.removed = frozenset(removed)
        self.first = next_plan_term(current_term)
        self.counts_as: dict[str, set[str]] = {}
        for f, t, _ in equivalences:
            self.counts_as.setdefault(f, set()).add(t)

    # -- columns ---------------------------------------------------------------

    def terms(self, graduation: str) -> list[str]:
        """Every term after the current one, through graduation, less the
        ones the student took out."""
        out, term = [], self.first
        while term_order(term) <= term_order(graduation):
            if term not in self.removed:
                out.append(term)
            term = next_plan_term(term)
        return out

    # -- checking ----------------------------------------------------------------

    def limit(self, term: str) -> float:
        """The term's credit limit: past it, a semester warns and a short term refuses."""
        return SHORT_MAX_LOAD if term[4:] in SHORT_KINDS else self.max_load

    def _credits(self, course_id: str) -> float:
        return self.credits.get(course_id, 1.0)

    def _expand(self, ids: Iterable[str]) -> set[str]:
        out, stack = set(), list(ids)
        while stack:
            cid = stack.pop()
            if cid not in out:
                out.add(cid)
                stack.extend(self.counts_as.get(cid, ()))
        return out

    def _standing(self, term: str) -> str:
        """Standing by `term`: what the record says now, or what the
        semesters finished by then reach, whichever is higher."""
        ahead = semesters_between(self.first, term)  # semesters finished before it, from now
        reached = [lvl for lvl in LEVELS if STANDING_ROUNDS[lvl] <= self.terms_elapsed + ahead]
        return max([self.facts.standing, *reached], key=LEVELS.index)

    def check(self, plan: list[Placement], course_id: str, term: str) -> Check:
        """Would placing (or moving) `course_id` into `term` be valid?"""
        others = [p for p in plan if p.course_id != course_id]
        load = self._credits(course_id) + sum(self._credits(p.course_id) for p in others if p.term == term)
        short = term[4:] in SHORT_KINDS
        base = {"course_id": course_id, "term": term, "load": load, "overloaded": not short and load > self.max_load}
        name = label(course_id)

        def refuse(message: str) -> Check:
            return Check(ok=False, message=message, overridable=False, **base)

        if term[4:] not in PLAN_KINDS:
            return refuse(f"{term} is not a fall, Winter Term, spring or May Term.")
        if term_order(term) < term_order(self.first):
            return refuse(f"{term} is not a future term; the plan starts at {self.first}.")
        if term in self.removed:
            return refuse(f"{term} is removed from the plan; add it back to place courses there.")
        if course_id in self.facts.completed:
            return refuse(f"{name} is already completed.")
        if course_id in self.facts.in_progress:
            return refuse(f"{name} is already in progress.")
        if course_id not in self.trees:
            return refuse(f"{name} is not in the catalog.")
        if short and course_id not in self.extended:
            return refuse(f"{name} is not an Extended Studies course; {term} takes only those.")
        if short and load > SHORT_MAX_LOAD:
            unit = "credit" if load == 1 else "credits"
            return refuse(f"{term} would hold {load:g} {unit}; a short term holds at most {SHORT_MAX_LOAD:g}.")

        earlier = self._expand(p.course_id for p in others if term_order(p.term) < term_order(term))
        alongside = self._expand(p.course_id for p in others if p.term == term)
        by_then = replace(
            self.facts,
            completed=self.facts.completed | earlier,
            taken=self.facts.taken | {resolve(c, self.facts.renumbering) for c in earlier},
            planned=set(),
            standing=self._standing(term),
        )
        result = evaluate(self.trees[course_id], by_then, alongside=alongside)
        if result.value == Tri.TRUE:
            return Check(ok=True, **base)
        if result.value == Tri.UNKNOWN:
            return Check(ok=True, confirm=result.unmet, **base)
        return Check(
            ok=False,
            unmet=result.unmet,
            message=f"{name} can't go in {term}. Still unmet by then: {'; '.join(result.unmet)}.",
            **base,
        )

    # -- editing -------------------------------------------------------------------

    def place(
        self, plan: list[Placement], course_id: str, term: str, *, override: str | None = None
    ) -> list[Placement]:
        """The plan with `course_id` in `term` (moved there if already planned).

        Raises Rejected when the check fails, unless an override note is given
        and the failure is one a note can excuse. A placement that passes on
        its own keeps no override, so moving one clears a stale note."""
        if override is not None and not override.strip():
            raise ValueError("an override needs a justification note")
        check = self.check(plan, course_id, term)
        if not check.ok and (override is None or not check.overridable):
            raise Rejected(check)
        note = None if check.ok else override.strip()
        return [p for p in plan if p.course_id != course_id] + [Placement(course_id, term, note)]

    def drop_term(self, plan: list[Placement], term: str) -> None:
        """May `term` be taken out of the plan? Raises ValueError if not: only
        a future planner term, and only once its courses have gone, so that
        removing a term never silently drops a placement."""
        if term[4:] not in PLAN_KINDS or not term[:4].isdigit():
            raise ValueError(f"{term} is not a fall, Winter Term, spring or May Term.")
        if term_order(term) < term_order(self.first):
            raise ValueError(f"{term} is not a future term; the record holds it.")
        held = sorted(label(p.course_id) for p in plan if p.term == term)
        if held:
            raise ValueError(f"{term} still holds {', '.join(held)}; move or remove them first.")

    def remove(self, plan: list[Placement], course_id: str) -> list[Placement]:
        return [p for p in plan if p.course_id != course_id]

    def review(self, plan: list[Placement]) -> Review:
        """Every placement re-checked: after a move or a removal, a course
        that relied on the one moved shows up in `problems`."""
        checks = {}
        for p in plan:
            check = self.check(plan, p.course_id, p.term)
            check.override = p.override
            checks[p.course_id] = check
        loads: dict[str, float] = {}
        for p in sorted(plan, key=lambda p: term_order(p.term)):
            loads[p.term] = loads.get(p.term, 0.0) + self._credits(p.course_id)
        return Review(
            checks=checks,
            loads=loads,
            overloaded=[t for t, load in loads.items() if t[4:] not in SHORT_KINDS and load > self.max_load],
            problems=[c for c in checks.values() if not c.ok and not (c.override and c.overridable)],
        )
