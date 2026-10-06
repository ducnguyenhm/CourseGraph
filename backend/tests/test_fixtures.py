"""Fixture loading and the corrupted-catalog demo.

None of this touches a database, so it runs anywhere — and every corrupted
fixture the checkpoint demo loads is asserted here, so the demo cannot rot.
"""

import json
from pathlib import Path

import pytest

from app.schemas.prereq import parse
from app.services.fixtures import check, read_fixtures
from app.services.validation import CatalogError, describe_cycle, find_cycle

DATA = Path(__file__).resolve().parent.parent / "data"
CSC = DATA / "csc_catalog_2025_26.json"
MATH = DATA / "math_catalog_2025_26.json"
CORRUPT = DATA / "corrupt"

C = lambda c: {"type": "course", "course_id": c}  # noqa: E731


def write(path: Path, doc: dict) -> Path:
    path.write_text(json.dumps(doc))
    return path


def test_fixtures_declare_their_own_catalog_year(tmp_path):
    """The year must come from the file, not from server settings — otherwise a
    2025-26 catalog silently files under whatever year the server defaults to."""
    f = write(
        tmp_path / "x.json",
        {"catalog_year": "2025-2026", "courses": [{"id": "CSC-121", "title": "CS I", "prereq": None}]},
    )
    fixtures = read_fixtures([f])
    assert fixtures.catalog_year == "2025-2026"
    assert fixtures.entries[0]["id"] == "CSC-121"


def test_mixed_catalog_years_are_refused(tmp_path):
    a = write(tmp_path / "a.json", {"catalog_year": "2025-2026", "courses": []})
    b = write(tmp_path / "b.json", {"catalog_year": "2026-2027", "courses": []})
    with pytest.raises(CatalogError, match="disagree on catalog_year"):
        read_fixtures([a, b])


def test_the_real_catalog_passes():
    fixtures = check([CSC, MATH])
    assert fixtures.catalog_year == "2025-2026"
    assert len(fixtures.entries) == 29 + 35 + 10


def test_duplicate_course_across_files_is_refused(tmp_path):
    """The last file used to win silently, letting a second fixture overwrite
    curated data without anyone noticing."""
    a = write(tmp_path / "a.json", {"catalog_year": "2025-2026", "courses": [{"id": "CSC-121", "title": "CS I"}]})
    b = write(tmp_path / "b.json", {"catalog_year": "2025-2026", "courses": [{"id": "CSC 121", "title": "Other"}]})
    with pytest.raises(CatalogError, match="CSC-121 is defined in both a.json and b.json"):
        read_fixtures([a, b])


def test_curated_course_cannot_shadow_a_stub(tmp_path):
    """A new department must remove the stubs it replaces, not overlay them."""
    a = write(tmp_path / "a.json", {"catalog_year": "2025-2026", "stub_courses": [{"id": "ECON-100", "title": "Intro"}]})
    b = write(tmp_path / "b.json", {"catalog_year": "2025-2026", "courses": [{"id": "ECON-100", "title": "Intro"}]})
    with pytest.raises(CatalogError, match="ECON-100"):
        read_fixtures([a, b])


def test_only_renumberings_redirect_references():
    """MATH-136 'satisfies' MATH-151 but is still a course: references to it
    must not be rewritten."""
    renumbering = read_fixtures([CSC, MATH]).renumbering
    assert renumbering["CSC-233"] == "CSC-236"
    assert "MATH-136" not in renumbering


# --- the checkpoint demo ---------------------------------------------------


def refusal(*paths: Path) -> str:
    with pytest.raises(CatalogError) as exc:
        check(list(paths))
    return str(exc.value)


def test_direct_cycle_is_refused_and_named():
    msg = refusal(CORRUPT / "csc_cycle_direct.json", MATH)
    assert "1 problem(s) found" in msg
    assert "prerequisite cycle: CSC-121 -> CSC-231 -> CSC-125 -> CSC-121" in msg


def test_cycle_through_a_renumbering_names_the_cited_id():
    msg = refusal(CORRUPT / "csc_cycle_via_renumber.json", MATH)
    assert "prerequisite cycle: CSC-235 -> CSC-236 (cited as CSC-233) -> CSC-235" in msg


def test_loop_through_an_alternative_is_accepted():
    """Taking CSC-121 escapes the loop, so the catalog is still satisfiable."""
    check([CORRUPT / "csc_or_loop.json", MATH])


def test_every_corrupted_fixture_says_what_was_changed():
    for path in CORRUPT.glob("*.json"):
        assert json.loads(path.read_text()).get("corruption"), path.name


def test_describe_cycle_leaves_direct_hops_unlabelled():
    trees = {"CSC-101": parse(C("CSC-102")), "CSC-102": parse(C("CSC-101"))}
    cycle = find_cycle(trees)
    assert describe_cycle(cycle, trees) == " -> ".join(cycle)
    assert "cited" not in describe_cycle(cycle, trees)
