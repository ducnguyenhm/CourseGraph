"""Reading curated catalog fixtures from disk.

Deliberately free of any database import, so a fixture set can be checked —
including the corrupted ones under `data/corrupt/` — without a connection, and
so the checks are testable on a machine with no Postgres driver installed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.schemas.prereq import PrereqNode, normalize_id, parse
from app.services.programs import referenced_ids, to_rows, walk
from app.services.validation import CatalogError, validate


@dataclass
class FixtureSet:
    catalog_year: str
    entries: list[dict] = field(default_factory=list)
    # As written in the fixtures, for the course_equivalence table.
    equivalences: list[dict] = field(default_factory=list)
    retired: set[str] = field(default_factory=set)

    @property
    def renumbering(self) -> dict[str, str]:
        """Retired id -> its successor, for resolving references.

        Only 'renumber' rows: MATH-136 'satisfies' MATH-151 but is still a
        course in its own right, so a reference to it must not be rewritten.
        This matches what the graph API resolves.
        """
        return {
            normalize_id(eq["from"]): normalize_id(eq["to"])
            for eq in self.equivalences
            if eq.get("relation") == "renumber"
        }


def read_fixtures(paths: list[Path]) -> FixtureSet:
    entries: list[dict] = []
    equivalences: list[dict] = []
    retired: set[str] = set()
    years: dict[str, Path] = {}
    defined_in: dict[str, Path] = {}
    duplicates: list[str] = []

    for path in paths:
        doc = json.loads(path.read_text())
        # The fixture declares its own catalog year. Taking it from settings
        # instead would silently file a 2025-26 catalog under whatever year the
        # server happened to default to — the exact error the versioned schema
        # exists to prevent.
        years[str(doc["catalog_year"])] = path
        listed = [{**c, "stub": False} for c in doc.get("courses", [])] + [
            {**s, "stub": True} for s in doc.get("stub_courses", [])
        ]
        for entry in listed:
            cid = normalize_id(entry["id"])
            # Without this the last file to define a course silently wins, so a
            # second fixture could overwrite curated data unnoticed.
            if cid in defined_in:
                duplicates.append(f"{cid} is defined in both {defined_in[cid].name} and {path.name}")
            else:
                defined_in[cid] = path
            entries.append(entry)
        equivalences.extend(doc.get("equivalences", []))
        for r in doc.get("retired_ids", []):
            retired.add(normalize_id(r["id"]))

    if len(years) != 1:
        listing = ", ".join(f"{p.name}={y}" for y, p in sorted(years.items()))
        raise CatalogError(f"fixtures disagree on catalog_year: {listing}")
    if duplicates:
        raise CatalogError(
            f"{len(duplicates)} duplicate course id(s):\n  " + "\n  ".join(duplicates)
        )

    return FixtureSet(next(iter(years)), entries, equivalences, retired)


def parse_trees(fixtures: FixtureSet) -> dict[str, PrereqNode]:
    return {normalize_id(e["id"]): parse(e.get("prereq")) for e in fixtures.entries}


def check(paths: list[Path]) -> FixtureSet:
    """Read, parse and validate a fixture set; raise CatalogError on any defect.

    This is everything seeding does before it writes, and nothing after.
    """
    fixtures = read_fixtures(paths)
    try:
        trees = parse_trees(fixtures)
    except ValueError as exc:  # pydantic's ValidationError is a ValueError
        raise CatalogError(f"fixtures are malformed:\n{exc}") from exc
    validate(trees, fixtures.renumbering)
    return fixtures


# --- programs and students ----------------------------------------------------


def _known_ids(fixtures: FixtureSet) -> set[str]:
    return {normalize_id(e["id"]) for e in fixtures.entries}


def _same_year(doc: dict, path: Path, fixtures: FixtureSet) -> None:
    if str(doc["catalog_year"]) != fixtures.catalog_year:
        raise CatalogError(
            f"{path.name} is for {doc['catalog_year']}, the catalog is {fixtures.catalog_year}"
        )


def read_programs(path: Path, fixtures: FixtureSet) -> list[dict]:
    """Programs with their requirement trees as rows. Every course a
    requirement names must exist in this catalog year."""
    doc = json.loads(path.read_text())
    _same_year(doc, path, fixtures)
    known = _known_ids(fixtures)
    programs, problems = [], []
    for p in doc["programs"]:
        try:
            root = to_rows(p["requirements"])
        except (KeyError, ValueError) as exc:
            problems.append(f"{p.get('id')}: malformed requirements ({exc})")
            continue
        missing = referenced_ids((r.rule_type, r.spec) for r in walk(root)) - known
        if missing:
            problems.append(f"{p['id']} names {', '.join(sorted(missing))} — not in this catalog")
        programs.append({**p, "root": root})
    if problems:
        raise CatalogError(f"{len(problems)} problem(s) in {path.name}:\n  " + "\n  ".join(problems))
    return programs


def read_students(
    path: Path, fixtures: FixtureSet, program_ids: set[str]
) -> list[dict]:
    """Students may hold courses under retired numbers (CSC-122) — that is the
    point of keeping retired ids — but never a course that does not exist."""
    doc = json.loads(path.read_text())
    _same_year(doc, path, fixtures)
    known = _known_ids(fixtures) | fixtures.retired
    # Competence a course can carry: a section variant, or always (CSC 498 is S).
    offers = {
        normalize_id(e["id"]): set(e.get("competence_variants") or []) | set(e.get("attributes") or [])
        for e in fixtures.entries
    }
    problems = []
    for s in doc["students"]:
        for p in s.get("programs", []):
            if p not in program_ids:
                problems.append(f"student {s['id']} declares unknown program {p}")
        for e in s.get("enrollments", []) + s.get("plan", []):
            if normalize_id(e["course_id"]) not in known:
                problems.append(f"student {s['id']} lists unknown course {e['course_id']}")
        for e in s.get("enrollments", []):
            if e.get("status", "completed") not in ("completed", "in_progress"):
                problems.append(f"student {s['id']}: bad status {e['status']!r}")
            comp = e.get("competence")
            if comp is not None:
                cid = normalize_id(e["course_id"])
                if comp not in ("W", "Q", "S"):
                    problems.append(f"student {s['id']}: bad competence {comp!r} on {cid}")
                elif cid in offers and comp not in offers[cid]:
                    problems.append(f"student {s['id']}: {cid} is not offered with {comp} competence")
    if problems:
        raise CatalogError(f"{len(problems)} problem(s) in {path.name}:\n  " + "\n  ".join(problems))
    return doc["students"]
