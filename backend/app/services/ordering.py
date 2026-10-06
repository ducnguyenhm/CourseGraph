"""A topological order for a program, grouped into rounds.

Each round holds courses that can be taken together; every course sits in a
later round than everything it needs. The number of rounds is the length of
the longest prerequisite chain — Checkpoint 3's chain-based lower bound on
semesters.

Ordering on required edges alone puts courses too early: CSC-340 needs
"CSC 231 or CSC 235", so neither is individually required, yet one of them must
come first. So each course is placed one round after its prerequisite tree is
done, where `and` waits for its slowest child and `or` takes its fastest branch
— the optimistic choice the proposal specifies — and the branch assumed is
reported, so the order is not presented as more certain than it is.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.prereq import (
    AndReq,
    ConsentReq,
    CoreqReq,
    CourseLevelReq,
    CourseReq,
    OrReq,
    PlacementReq,
    PrereqNode,
    StandingReq,
)
from app.services.validation import resolve

UNREACHABLE = 10**6


# Semesters that must pass before a standing is reached. A capstone such as
# MATH-495 has no course prerequisite, only senior standing; without this it
# would sort into round one.
STANDING_ROUNDS = {"first_year": 0, "sophomore": 2, "junior": 4, "senior": 6}


@dataclass(frozen=True)
class Placement:
    round: int  # 1-based
    needs: frozenset[str]  # every course on the assumed path, transitively
    assumed: tuple[str, ...]  # human-readable notes on the branches chosen
    # The assumed path relies on someone's permission. A plan should not count
    # on consent, so such a path is only taken when there is no other.
    via_consent: bool = False


@dataclass
class ProgramOrder:
    rounds: list[list[str]]
    assumed: list[str] = field(default_factory=list)

    @property
    def order(self) -> list[str]:
        return [c for r in self.rounds for c in r]


def _name(cid: str) -> str:
    return cid.replace("-", " ")


class Orderer:
    def __init__(
        self, trees: dict[str, PrereqNode], equivalences: dict[str, str] | None = None
    ):
        self.trees = trees
        self.eq = equivalences or {}
        self._memo: dict[str, Placement] = {}
        self._in_progress: set[str] = set()

    def place(self, course_id: str) -> Placement:
        if course_id in self._memo:
            return self._memo[course_id]
        if course_id in self._in_progress:
            # Only reachable through an `or` loop; that branch is never the
            # fastest, so make it lose.
            return Placement(UNREACHABLE, frozenset(), ())
        self._in_progress.add(course_id)
        tree = self.trees.get(course_id)
        done = self._finish(tree, course_id) if tree else Placement(0, frozenset(), ())
        self._in_progress.discard(course_id)
        placement = Placement(done.round + 1, done.needs, done.assumed, done.via_consent)
        self._memo[course_id] = placement
        return placement

    def _finish(self, node: PrereqNode, owner: str) -> Placement:
        """When the tree can be satisfied (round = the last round it waits
        for), which courses that uses, and what was assumed along the way."""
        if isinstance(node, (CourseReq, CoreqReq)):
            cid = resolve(node.course_id, self.eq)
            p = self.place(cid)
            # A coreq may share the course's term, so it delays nothing itself.
            r = p.round - 1 if isinstance(node, CoreqReq) else p.round
            return Placement(r, p.needs | {cid}, p.assumed, p.via_consent)
        if isinstance(node, (ConsentReq, PlacementReq)):
            return Placement(0, frozenset(), (), via_consent=True)
        if isinstance(node, StandingReq):
            if node.min_level and STANDING_ROUNDS[node.min_level]:
                r = STANDING_ROUNDS[node.min_level]
                note = f"{_name(owner)}: {node.min_level} standing, so not before semester {r + 1}"
                return Placement(r, frozenset(), (note,))
            return Placement(0, frozenset(), ())
        if isinstance(node, CourseLevelReq):
            # Optimistic: the earliest qualifying courses, taken in parallel —
            # skipping ones open only by permission (CSC-396 Topics, CSC-398
            # Independent Study), which would "satisfy" CSC-498 in round one.
            candidates = sorted(
                (self.place(cid).via_consent, self.place(cid).round, cid)
                for cid in self.trees
                if cid != owner
                and cid.split("-")[0] == node.subject
                and int(cid.split("-")[1]) >= node.min_number
            )[: node.count]
            if len(candidates) < node.count:
                return Placement(UNREACHABLE, frozenset(), ())
            picked = [cid for _, _, cid in candidates]
            needs = frozenset(picked).union(*(self.place(c).needs for c in picked))
            note = (
                f"{_name(owner)}: assumes {', '.join(map(_name, picked))} for "
                f"'{node.count} {node.subject} course(s) numbered {node.min_number}+'"
            )
            return Placement(
                max(r for _, r, _ in candidates),
                needs,
                (note,),
                any(v for v, _, _ in candidates),
            )
        if isinstance(node, AndReq):
            parts = [self._finish(c, owner) for c in node.children]
            return Placement(
                max(p.round for p in parts),
                frozenset().union(*(p.needs for p in parts)),
                tuple(a for p in parts for a in p.assumed),
                any(p.via_consent for p in parts),
            )
        if isinstance(node, OrReq):
            parts = [self._finish(c, owner) for c in node.children]
            # Fastest branch that does not depend on permission; ties go to
            # the branch needing the fewest courses, then the first written.
            best = min(parts, key=lambda p: (p.via_consent, p.round, len(p.needs)))
            assumed = best.assumed
            if len(parts) > 1 and best.needs:
                chosen = sorted(map(_name, best.needs - _shared(parts)))
                if chosen:
                    assumed += (f"{_name(owner)}: assumes {', '.join(chosen)}",)
            return Placement(best.round, best.needs, assumed, best.via_consent)
        # none, program: no course to wait for.
        return Placement(0, frozenset(), ())

    def program_order(self, course_ids: set[str]) -> ProgramOrder:
        """Rounds for `course_ids` plus every course on their assumed paths."""
        needed = set(course_ids)
        assumed: list[str] = []
        for cid in sorted(course_ids):
            p = self.place(cid)
            needed |= p.needs
            assumed.extend(a for a in p.assumed if a not in assumed)
        by_round: dict[int, list[str]] = {}
        for cid in needed:
            by_round.setdefault(self.place(cid).round, []).append(cid)
        # Empty rounds are kept, so round n always means "the nth term": a
        # senior-standing capstone sits in round 7 even if 5 and 6 are empty.
        last = max((r for r in by_round if r < UNREACHABLE), default=0)
        rounds = [sorted(by_round.get(r, [])) for r in range(1, last + 1)]
        return ProgramOrder(rounds=rounds, assumed=assumed)


def _shared(parts: list[Placement]) -> frozenset[str]:
    """Courses every branch of an `or` needs anyway — not part of the choice."""
    sets = [p.needs for p in parts]
    return frozenset.intersection(*sets) if sets else frozenset()
