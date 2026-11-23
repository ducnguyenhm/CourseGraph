"""Ingestion-time validation.

Catches the two defect classes that are silent at write time and only surface
as wrong answers later: a prerequisite naming a course that does not exist, and
a cycle in the prerequisite graph.
"""

from __future__ import annotations

from app.schemas.prereq import PrereqNode, course_ids, required_ids


class CatalogError(Exception):
    """Raised when a catalog fixture is not fit to load."""


def resolve(course_id: str, equivalences: dict[str, str]) -> str:
    """Follow renumbering chains to the id in force this catalog year."""
    seen = {course_id}
    while (nxt := equivalences.get(course_id)) and nxt not in seen:
        course_id = nxt
        seen.add(nxt)
    return course_id


def find_dangling(
    trees: dict[str, PrereqNode], equivalences: dict[str, str] | None = None
) -> dict[str, set[str]]:
    """References naming a course absent from the catalog, after equivalences.

    MATH-323 cites CSC-233, which the 2026-27 catalog retired in favour of
    CSC-236. That is a resolvable reference, not a broken one.
    """
    eq = equivalences or {}
    known = set(trees)
    return {
        code: missing
        for code, tree in trees.items()
        if (
            missing := {
                ref
                for ref in course_ids(tree)
                if ref not in known and resolve(ref, eq) not in known
            }
        )
    }


def find_cycle(
    trees: dict[str, PrereqNode], equivalences: dict[str, str] | None = None
) -> list[str] | None:
    """One prerequisite cycle as a path, or None.

    Only strictly-required edges can form a real cycle — an alternative branch
    is always escapable by taking the other branch.
    """
    eq = equivalences or {}
    deps = {
        code: {r for ref in required_ids(tree) if (r := resolve(ref, eq)) in trees}
        for code, tree in trees.items()
    }

    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(deps, WHITE)
    stack: list[str] = []

    def visit(code: str) -> list[str] | None:
        colour[code] = GREY
        stack.append(code)
        for dep in sorted(deps[code]):
            if colour[dep] == GREY:
                return stack[stack.index(dep) :] + [dep]
            if colour[dep] == WHITE and (cycle := visit(dep)):
                return cycle
        stack.pop()
        colour[code] = BLACK
        return None

    for code in sorted(deps):
        if colour[code] == WHITE and (cycle := visit(code)):
            return cycle
    return None


def describe_cycle(
    cycle: list[str],
    trees: dict[str, PrereqNode],
    equivalences: dict[str, str] | None = None,
) -> str:
    """'A -> B (cited as C) -> A'.

    A hop that only exists after renumbering is labelled with the id the
    fixture actually wrote — otherwise the message names a course the corrupted
    file never mentions, which reads like the wrong answer.
    """
    eq = equivalences or {}
    parts = [cycle[0]]
    for course, dep in zip(cycle, cycle[1:]):
        refs = required_ids(trees[course])
        cited = None
        if dep not in refs:
            cited = next((r for r in sorted(refs) if resolve(r, eq) == dep), None)
        parts.append(f"{dep} (cited as {cited})" if cited else dep)
    return " -> ".join(parts)


def validate(
    trees: dict[str, PrereqNode], equivalences: dict[str, str] | None = None
) -> None:
    """Raise CatalogError listing every problem found, or return cleanly."""
    problems: list[str] = []

    for code, missing in sorted(find_dangling(trees, equivalences).items()):
        problems.append(
            f"{code} requires {', '.join(sorted(missing))} — not in this catalog "
            f"and not resolvable through an equivalence"
        )

    if cycle := find_cycle(trees, equivalences):
        problems.append(
            "prerequisite cycle: " + describe_cycle(cycle, trees, equivalences)
        )

    if problems:
        raise CatalogError(
            f"{len(problems)} problem(s) found:\n  " + "\n  ".join(problems)
        )
