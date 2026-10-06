"""Project prerequisite expression trees onto the displayed graph.

A tree is not a set of edges. `A and B` and `A or B` contain the same courses
but mean different things, so each emitted edge records whether it sits under a
disjunction and, if so, which one — letting the UI draw alternatives
differently from strict requirements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count

from app.schemas.prereq import (
    AndReq,
    ConsentReq,
    CoreqReq,
    CourseLevelReq,
    CourseReq,
    OrReq,
    PlacementReq,
    PrereqNode,
    ProgramReq,
    StandingReq,
)
from app.services.validation import resolve


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    kind: str  # "required" | "alternative" | "coreq"
    group: str | None = None  # shared by siblings of the same `or`
    via: str | None = None  # original id when an equivalence was followed


@dataclass
class Node:
    course_id: str
    title: str = ""
    credits_min: float | None = None
    credits_max: float | None = None
    badges: list[str] = field(default_factory=list)


def project_course(
    course_id: str, tree: PrereqNode, equivalences: dict[str, str] | None = None
) -> tuple[list[Edge], list[str]]:
    """Return (edges into `course_id`, non-course badges for `course_id`)."""
    eq = equivalences or {}
    edges: list[Edge] = []
    badges: list[str] = []
    groups = count(1)

    def emit(ref: str, kind: str, group: str | None) -> None:
        target = resolve(ref, eq)
        edges.append(
            Edge(
                source=target,
                target=course_id,
                kind=kind,
                group=group,
                via=ref if target != ref else None,
            )
        )

    def walk(node: PrereqNode, group: str | None) -> None:
        if isinstance(node, CourseReq):
            emit(node.course_id, "alternative" if group else "required", group)
        elif isinstance(node, CoreqReq):
            # A corequisite may be taken in the same term, so it never
            # constrains ordering the way a prerequisite does.
            emit(node.course_id, "coreq", group)
        elif isinstance(node, ConsentReq):
            badges.append(f"consent:{node.by}")
        elif isinstance(node, StandingReq):
            bound = (
                f"min {node.min_level}" if node.min_level else f"max {node.max_level}"
            )
            badges.append(f"standing:{bound}")
        elif isinstance(node, CourseLevelReq):
            badges.append(
                f"level:{node.count}x {node.subject} {node.min_number}+"
            )
        elif isinstance(node, ProgramReq):
            badges.append(f"program:{node.program_id}")
        elif isinstance(node, PlacementReq):
            badges.append(f"placement:{node.test}")
        elif isinstance(node, AndReq):
            for child in node.children:
                walk(child, group)
        elif isinstance(node, OrReq):
            gid = f"{course_id}#or{next(groups)}"
            for child in node.children:
                walk(child, gid)

    walk(tree, None)
    return edges, badges


def compute_layers(node_ids: set[str], edges: list[Edge]) -> dict[str, int]:
    """Longest-path depth, so every course sits to the right of its prerequisites.

    Corequisites are excluded — they may be taken in the same term, so they
    must not push a course into a later layer. Validation guarantees the
    required edges are acyclic, but an `or` branch can still close a loop in
    the *displayed* graph, so the walk guards against re-entry.
    """
    incoming: dict[str, list[str]] = {n: [] for n in node_ids}
    for e in edges:
        if e.kind != "coreq" and e.source in node_ids and e.target in node_ids:
            incoming[e.target].append(e.source)

    depth: dict[str, int] = {}
    in_progress: set[str] = set()

    def walk(n: str) -> int:
        if n in depth:
            return depth[n]
        if n in in_progress:
            return 0  # back-edge through an alternative branch
        in_progress.add(n)
        d = max((walk(p) + 1 for p in incoming[n]), default=0)
        in_progress.discard(n)
        depth[n] = d
        return d

    for n in sorted(node_ids):
        walk(n)
    return depth


def build_graph(
    courses: dict[str, tuple[PrereqNode, str, float | None, float | None]],
    equivalences: dict[str, str] | None = None,
    visible: set[str] | None = None,
) -> dict:
    """courses: id -> (tree, title, credits_min, credits_max).

    `courses` should be the whole catalog year, so depth reflects every
    prerequisite; `visible` (default: all) is what is returned. An edge from a
    hidden course into a visible one is kept and marked `external`, so a
    filtered view can point at the missing prerequisite instead of silently
    losing it.
    """
    nodes = {
        cid: Node(course_id=cid, title=t, credits_min=lo, credits_max=hi)
        for cid, (_, t, lo, hi) in courses.items()
    }
    edges: list[Edge] = []

    for cid, (tree, _, _, _) in courses.items():
        course_edges, badges = project_course(cid, tree, equivalences)
        nodes[cid].badges = badges
        # Drop edges from courses outside the rendered subset, or the canvas
        # sprouts phantom nodes for prerequisites that were never loaded.
        edges.extend(e for e in course_edges if e.source in nodes)

    layers = compute_layers(set(nodes), edges)
    shown = set(nodes) if visible is None else visible & set(nodes)

    return {
        "nodes": [
            {
                "id": n.course_id,
                "course_id": n.course_id,
                "label": n.course_id.replace("-", " "),
                "title": n.title,
                "credits_min": float(n.credits_min) if n.credits_min is not None else None,
                "credits_max": float(n.credits_max) if n.credits_max is not None else None,
                "badges": n.badges,
                "layer": layers[n.course_id],
            }
            for n in sorted(nodes.values(), key=lambda n: n.course_id)
            if n.course_id in shown
        ],
        "edges": [
            {
                "id": f"{e.source}->{e.target}#{i}",
                "source": e.source,
                "target": e.target,
                "kind": e.kind,
                "group": e.group,
                "via": e.via,
                "external": e.source not in shown,
            }
            for i, e in enumerate(edges)
            if e.target in shown
        ],
    }
