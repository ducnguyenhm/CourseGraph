"""What must come before a course, and what it opens up.

Computed over a whole catalog year, never a filtered view: CSC-380 needs
MATH-141 whether or not MATH is on screen.

Upstream courses are split by *necessity*. CSC-340 is "CSC 231 or CSC 235", so
neither is required — but both branches pass through CSC-125 and CSC-121, so
those are. A plain transitive closure gets this wrong in both directions: it
calls 231 and 235 required, and the closure of `required_ids()` misses 121 and
125 entirely, because 231 and 235 share no direct prerequisite id.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from app.schemas.prereq import AndReq, CourseReq, OrReq, PrereqNode
from app.services.validation import resolve

REQUIRED = "required"
ALTERNATIVE = "alternative"


def prerequisite_refs(node: PrereqNode) -> set[str]:
    """Course leaves on any branch. Coreqs are excluded: they constrain the
    same term, not 'before'."""
    if isinstance(node, CourseReq):
        return {node.course_id}
    if isinstance(node, (AndReq, OrReq)):
        return set().union(*(prerequisite_refs(c) for c in node.children))
    return set()


@dataclass(frozen=True)
class Reached:
    course_id: str
    necessity: str  # REQUIRED | ALTERNATIVE


class Reachability:
    def __init__(
        self, trees: dict[str, PrereqNode], equivalences: dict[str, str] | None = None
    ):
        self.trees = trees
        self.eq = equivalences or {}
        self.prereqs = {
            cid: {resolve(r, self.eq) for r in prerequisite_refs(tree)}
            for cid, tree in trees.items()
        }
        self.dependents: dict[str, set[str]] = {cid: set() for cid in trees}
        for cid, refs in self.prereqs.items():
            for r in refs:
                self.dependents.setdefault(r, set()).add(cid)
        self._necessary: dict[str, frozenset[str]] = {}
        self._in_progress: set[str] = set()

    def necessary(self, course_id: str) -> frozenset[str]:
        """Courses on every satisfying path to `course_id`, transitively."""
        if course_id in self._necessary:
            return self._necessary[course_id]
        if course_id in self._in_progress or course_id not in self.trees:
            # Re-entry can only happen through an `or` branch (ingestion
            # rejects required cycles), and that branch is escapable.
            return frozenset()
        self._in_progress.add(course_id)
        result = frozenset(self._required_by(self.trees[course_id]))
        self._in_progress.discard(course_id)
        self._necessary[course_id] = result
        return result

    def _required_by(self, node: PrereqNode) -> set[str]:
        # A course contributes itself plus everything IT requires; `and` needs
        # every child, `or` only what all of its branches have in common.
        if isinstance(node, CourseReq):
            cid = resolve(node.course_id, self.eq)
            return {cid} | self.necessary(cid)
        if isinstance(node, AndReq):
            return set().union(*(self._required_by(c) for c in node.children))
        if isinstance(node, OrReq):
            return set.intersection(*(self._required_by(c) for c in node.children))
        return set()

    def upstream(self, course_id: str) -> list[Reached]:
        required = self.necessary(course_id)
        reached = _walk(course_id, self.prereqs)
        return sorted(
            (Reached(c, REQUIRED if c in required else ALTERNATIVE) for c in reached),
            key=lambda r: (r.necessity != REQUIRED, r.course_id),
        )

    def downstream(self, course_id: str) -> list[Reached]:
        """`required`: the dependent cannot be taken without `course_id`.
        `alternative`: `course_id` is one way in."""
        reached = _walk(course_id, self.dependents)
        return sorted(
            (
                Reached(c, REQUIRED if course_id in self.necessary(c) else ALTERNATIVE)
                for c in reached
            ),
            key=lambda r: (r.necessity != REQUIRED, r.course_id),
        )


def _walk(start: str, adjacency: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    queue = deque(adjacency.get(start, ()))
    while queue:
        cid = queue.popleft()
        if cid in seen or cid == start:
            continue
        seen.add(cid)
        queue.extend(adjacency.get(cid, ()))
    return seen
