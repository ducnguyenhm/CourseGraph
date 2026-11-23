"""The demo student over the real fixtures, shared by the tests that check
the requirement engine, the semester estimate and the explorer end to end."""

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.services.fixtures import check, parse_trees
from app.services.ordering import Orderer
from app.services.programs import RequirementRow, to_rows
from app.services.requirements import CourseInfo, Engine, Record
from app.services.semesters import current_term, terms_elapsed

DATA = Path(__file__).resolve().parent.parent / "data"
FIXTURES = ("csc_catalog", "math_catalog", "econ_catalog", "other_stubs")


@dataclass
class Demo:
    engine: Engine
    orderer: Orderer
    programs: dict[str, tuple[str, RequirementRow]]  # id -> (kind, tree)
    declared: list[str]
    current_term: str | None
    graduation: str


@pytest.fixture(scope="session")
def demo_student() -> Demo:
    fx = check([DATA / f"{n}_2025_26.json" for n in FIXTURES])
    catalog = {}
    for c in fx.entries:
        tags = set(c.get("attributes") or []) | ({c["distribution"]} if c.get("distribution") else set())
        catalog[c["id"]] = CourseInfo(
            c["subject"], c["number"], (1.0 if c.get("credits_max") is None else c["credits_max"]), frozenset(tags), stub=c["stub"]
        )
    student = json.loads((DATA / "demo_student.json").read_text())["students"][0]
    taken = [(e["course_id"], e["status"], e.get("competence")) for e in student["enrollments"]]
    taken += [(p["course_id"], "planned", None) for p in student["plan"]]
    eq = [(e["from"], e["to"], e["relation"]) for e in fx.equivalences]
    engine = Engine(Record.build(taken, catalog, eq), catalog)
    done = set().union(*(e.counts_as for e in engine.record.entries if e.state != "planned"))
    orderer = Orderer(
        parse_trees(fx),
        fx.renumbering,
        done=done,
        terms_elapsed=terms_elapsed([e["term"] for e in student["enrollments"]], student["class_standing"]),
    )
    programs = {
        p["id"]: (p["kind"], to_rows(p["requirements"]))
        for p in json.loads((DATA / "programs_2025_26.json").read_text())["programs"]
    }
    return Demo(
        engine,
        orderer,
        programs,
        student["programs"] + ["DEGREE-BA"],
        current_term((e["term"], e["status"]) for e in student["enrollments"]),
        student["expected_graduation"],
    )
