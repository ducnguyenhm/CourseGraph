"""Load curated catalog fixtures into PostgreSQL.

Reads the curated per-subject files as published, validates the union before
writing anything, and refuses a fixture set with unresolvable prerequisite
references or a cycle rather than half-loading it.

    python -m scripts.seed data/csc_catalog_2025_26.json data/math_catalog_2025_26.json
    python -m scripts.seed --if-empty
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.catalog import CatalogYear, Course, CourseEquivalence, CourseVersion
from app.schemas.prereq import normalize_id, parse
from app.services.validation import CatalogError, validate

DEFAULT_FIXTURES = ["data/csc_catalog_2025_26.json", "data/math_catalog_2025_26.json"]

# Verbatim prerequisite sentences from the catalog PDF, kept apart from the
# curated fixtures so the fixtures stay as published. Keyed by course id.
PREREQ_TEXT = Path("data/prereq_text_2025_26.json")

# Fields the schema models explicitly; everything else is preserved in `extra`.
MODELLED = {
    "id", "subject", "number", "title", "credits_min", "credits_max",
    "distribution", "competence_variants", "attributes", "prereq", "stub",
}


def read_fixtures(
    paths: list[Path],
) -> tuple[str, list[dict], dict[str, str], set[str]]:
    entries: list[dict] = []
    equivalences: dict[str, str] = {}
    retired: set[str] = set()
    years: dict[str, Path] = {}

    for path in paths:
        doc = json.loads(path.read_text())
        # The fixture declares its own catalog year. Taking it from settings
        # instead would silently file a 2025-26 catalog under whatever year the
        # server happened to default to — the exact error the versioned schema
        # exists to prevent.
        years[str(doc["catalog_year"])] = path
        for course in doc.get("courses", []):
            entries.append({**course, "stub": False})
        for stub in doc.get("stub_courses", []):
            entries.append({**stub, "stub": True})
        for eq in doc.get("equivalences", []):
            equivalences[normalize_id(eq["from"])] = normalize_id(eq["to"])
        for r in doc.get("retired_ids", []):
            retired.add(normalize_id(r["id"]))

    if len(years) != 1:
        listing = ", ".join(f"{p.name}={y}" for y, p in sorted(years.items()))
        raise CatalogError(f"fixtures disagree on catalog_year: {listing}")

    return next(iter(years)), entries, equivalences, retired


def read_prereq_text(catalog_year: str) -> dict[str, str]:
    if not PREREQ_TEXT.exists():
        return {}
    doc = json.loads(PREREQ_TEXT.read_text())
    if str(doc["catalog_year"]) != catalog_year:
        return {}
    return {normalize_id(k): v for k, v in doc["prereq_text"].items()}


def upsert(
    session: Session,
    catalog_year: str,
    entries: list[dict],
    equivalences: list[dict],
    retired: set[str],
) -> int:
    prereq_text = read_prereq_text(catalog_year)
    year = session.scalar(select(CatalogYear).where(CatalogYear.label == catalog_year))
    if year is None:
        year = CatalogYear(label=catalog_year)
        session.add(year)
        session.flush()

    def course_row(cid: str, *, stub: bool = False, is_retired: bool = False) -> Course:
        row = session.scalar(select(Course).where(Course.course_id == cid))
        if row is None:
            subject, number = cid.split("-")
            row = Course(course_id=cid, subject=subject, number=int(number))
            session.add(row)
            session.flush()
        row.stub = stub or row.stub
        row.retired = is_retired or row.retired
        return row

    for entry in entries:
        cid = normalize_id(entry["id"])
        course = course_row(cid, stub=entry.get("stub", False))

        version = session.scalar(
            select(CourseVersion).where(
                CourseVersion.course_id == course.id,
                CourseVersion.catalog_year_id == year.id,
            )
        )
        if version is None:
            version = CourseVersion(course_id=course.id, catalog_year_id=year.id)
            session.add(version)

        version.title = entry["title"]
        version.credits_min = entry.get("credits_min")
        version.credits_max = entry.get("credits_max")
        version.distribution = entry.get("distribution")
        version.competence_variants = entry.get("competence_variants", [])
        version.attributes = entry.get("attributes", [])
        version.prereq_expr = parse(entry.get("prereq")).model_dump(exclude_none=True)
        version.prereq_raw = prereq_text.get(cid, "")
        version.extra = {k: v for k, v in entry.items() if k not in MODELLED}

    # Retired courses keep an identity row so references to them resolve, but
    # get no version in a year whose catalog no longer lists them.
    for cid in retired:
        course_row(cid, is_retired=True)

    for eq in equivalences:
        f, t = normalize_id(eq["from"]), normalize_id(eq["to"])
        course_row(f)
        course_row(t)
        exists = session.scalar(
            select(CourseEquivalence).where(
                CourseEquivalence.from_id == f,
                CourseEquivalence.to_id == t,
                CourseEquivalence.relation == eq["relation"],
            )
        )
        if exists is None:
            session.add(
                CourseEquivalence(
                    from_id=f, to_id=t, relation=eq["relation"], note=eq.get("note", "")
                )
            )

    session.commit()
    return len(entries)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("fixtures", nargs="*", default=None)
    ap.add_argument("--if-empty", action="store_true")
    args = ap.parse_args()

    paths = [Path(p) for p in (args.fixtures or DEFAULT_FIXTURES)]
    missing = [p for p in paths if not p.exists()]
    if missing:
        print(f"fixture(s) not found: {', '.join(map(str, missing))}", file=sys.stderr)
        return 0 if args.if_empty else 1

    try:
        catalog_year, entries, eq_map, retired = read_fixtures(paths)
    except CatalogError as exc:
        print(exc, file=sys.stderr)
        return 1

    raw_eqs = [
        eq
        for p in paths
        for eq in json.loads(p.read_text()).get("equivalences", [])
    ]

    try:
        trees = {normalize_id(e["id"]): parse(e.get("prereq")) for e in entries}
    except Exception as exc:
        print(f"fixtures are malformed:\n{exc}", file=sys.stderr)
        return 1

    try:
        validate(trees, eq_map)
    except CatalogError as exc:
        print(f"refusing to load:\n{exc}", file=sys.stderr)
        return 1

    with SessionLocal() as session:
        if args.if_empty:
            existing = session.scalar(
                select(func.count(CourseVersion.id))
                .join(CatalogYear)
                .where(CatalogYear.label == catalog_year)
            )
            if existing:
                print(f"{catalog_year} already has {existing} courses — skipping")
                return 0
        n = upsert(session, catalog_year, entries, raw_eqs, retired)

    print(
        f"seeded {n} courses, {len(raw_eqs)} equivalences, "
        f"{len(retired)} retired ids into {catalog_year}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
