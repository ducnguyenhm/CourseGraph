"""Which courses a program mentions.

Checkpoint 2 needs requirements only for this: the program filter shows a
program's courses, and the topological order is computed over them. Deciding
whether a student *satisfies* a requirement is Checkpoint 3.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.schemas.prereq import normalize_id

RULE_TYPES = {
    "all_of",
    "any_of",
    "specific_course",
    "n_from_set",
    "credit_minimum",
    "attribute_count",
}
# Keys of a requirement node that are structure, not part of its spec.
STRUCTURAL = {"label", "rule", "children", "notes"}


@dataclass
class RequirementRow:
    label: str
    rule_type: str
    spec: dict
    notes: str = ""
    children: list["RequirementRow"] = field(default_factory=list)


def to_rows(node: dict) -> RequirementRow:
    """A fixture requirement node -> a row tree, ids normalised."""
    rule = node["rule"]
    if rule not in RULE_TYPES:
        raise ValueError(f"unknown requirement rule {rule!r}")
    spec = {k: v for k, v in node.items() if k not in STRUCTURAL}
    if "course_id" in spec:
        spec["course_id"] = normalize_id(spec["course_id"])
    for key in ("courses", "exclude"):
        if key in spec:
            spec[key] = [normalize_id(c) for c in spec[key]]
    return RequirementRow(
        label=node.get("label", ""),
        rule_type=rule,
        spec=spec,
        notes=node.get("notes", ""),
        children=[to_rows(c) for c in node.get("children", [])],
    )


def referenced_ids(rows: Iterable[tuple[str, dict]]) -> set[str]:
    """Every course id a requirement names explicitly (for validation)."""
    out: set[str] = set()
    for _, spec in rows:
        if "course_id" in spec:
            out.add(spec["course_id"])
        out.update(spec.get("courses", []))
        out.update(spec.get("exclude", []))
    return out


@dataclass
class ProgramCourses:
    fixed: set[str]  # named outright: every student takes these
    chosen: set[str]  # drawn from a set: a student takes some of these


def program_courses(
    rows: Iterable[tuple[str, dict]], catalog: dict[str, tuple[str, int]]
) -> ProgramCourses:
    """rows: (rule_type, spec) for every requirement of one program version.
    catalog: course id -> (subject, number), for filter-style sets."""
    fixed: set[str] = set()
    chosen: set[str] = set()
    for rule_type, spec in rows:
        if rule_type == "specific_course":
            fixed.add(spec["course_id"])
        elif rule_type == "n_from_set":
            chosen.update(spec.get("courses", []))
            if "subject" in spec:
                excluded = set(spec.get("exclude", []))
                chosen.update(
                    cid
                    for cid, (subject, number) in catalog.items()
                    if subject == spec["subject"]
                    and number >= spec.get("min_number", 0)
                    and cid not in excluded
                )
    return ProgramCourses(fixed=fixed, chosen=chosen - fixed)


def walk(row: RequirementRow) -> Iterable[RequirementRow]:
    yield row
    for c in row.children:
        yield from walk(c)
