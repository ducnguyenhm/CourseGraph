from pathlib import Path

import pytest

from app.schemas.prereq import parse
from app.services.fixtures import check, parse_trees
from app.services.reachability import ALTERNATIVE, REQUIRED, Reachability

DATA = Path(__file__).resolve().parent.parent / "data"
C = lambda c: {"type": "course", "course_id": c}  # noqa: E731


def split(reached):
    return (
        {r.course_id for r in reached if r.necessity == REQUIRED},
        {r.course_id for r in reached if r.necessity == ALTERNATIVE},
    )


@pytest.fixture(scope="module")
def catalog() -> Reachability:
    fixtures = check([DATA / "csc_catalog_2025_26.json", DATA / "math_catalog_2025_26.json"])
    return Reachability(parse_trees(fixtures), fixtures.renumbering)


def test_csc_340_is_the_hand_check(catalog):
    """'Either CSC 231 or CSC 235.' Both branches pass through CSC-125, which
    needs CSC-121 — so those two are required and only the pair is a choice.
    This is the result verified against the catalog during the presentation."""
    required, alternative = split(catalog.upstream("CSC-340"))
    assert required == {"CSC-121", "CSC-125"}
    assert alternative == {"CSC-231", "CSC-235"}


def test_and_makes_everything_required(catalog):
    required, alternative = split(catalog.upstream("CSC-322"))  # CSC 231 and CSC 235
    assert {"CSC-231", "CSC-235", "CSC-125", "CSC-121"} <= required
    assert alternative == set()


def test_chain_crosses_departments(catalog):
    """The filter bug: under 'CSC only', CSC-380 used to lose MATH-141."""
    required, _ = split(catalog.upstream("CSC-380"))
    assert "MATH-141" in required


def test_retired_citation_resolves_to_its_successor(catalog):
    """MATH-323 cites CSC-233; the chain must show CSC-236, never the retired id."""
    upstream = {r.course_id for r in catalog.upstream("MATH-323")}
    assert "CSC-236" in upstream
    assert "CSC-233" not in upstream


def test_downstream_marks_one_way_in_as_alternative(catalog):
    downstream = {r.course_id: r.necessity for r in catalog.downstream("CSC-231")}
    assert downstream["CSC-322"] == REQUIRED  # 231 and 235
    assert downstream["CSC-340"] == ALTERNATIVE  # 231 or 235


def test_downstream_of_the_first_course_reaches_far(catalog):
    downstream = {r.course_id: r.necessity for r in catalog.downstream("CSC-121")}
    assert downstream["CSC-125"] == REQUIRED
    assert downstream["CSC-340"] == REQUIRED  # every way in passes through 121


def test_a_course_is_never_its_own_prerequisite(catalog):
    for cid in ("CSC-121", "CSC-340", "MATH-323"):
        assert cid not in {r.course_id for r in catalog.upstream(cid)}
        assert cid not in {r.course_id for r in catalog.downstream(cid)}


def test_coreq_is_not_upstream():
    reach = Reachability(
        {"MATH-441": parse(None), "MATH-442": parse({"type": "coreq", "course_id": "MATH-441"})}
    )
    assert reach.upstream("MATH-442") == []


def test_nested_or_keeps_only_what_every_branch_shares():
    """(A and B) or (A and C): A is required, B and C are alternatives."""
    trees = {
        "CSC-101": parse(None),
        "CSC-102": parse(None),
        "CSC-103": parse(None),
        "CSC-200": parse(
            {
                "type": "or",
                "children": [
                    {"type": "and", "children": [C("CSC-101"), C("CSC-102")]},
                    {"type": "and", "children": [C("CSC-101"), C("CSC-103")]},
                ],
            }
        ),
    }
    required, alternative = split(Reachability(trees).upstream("CSC-200"))
    assert required == {"CSC-101"}
    assert alternative == {"CSC-102", "CSC-103"}


def test_loop_through_an_alternative_terminates():
    """Only termination is guaranteed here. Strictly, CSC-121 is required for
    CSC-235 (CSC-125 cannot use CSC-235 as its way in), but the guard reports it
    as an alternative. Ingestion accepts such loops; none exist in the catalog."""
    trees = {
        "CSC-121": parse(None),
        "CSC-125": parse({"type": "or", "children": [C("CSC-121"), C("CSC-235")]}),
        "CSC-235": parse(C("CSC-125")),
    }
    required, alternative = split(Reachability(trees).upstream("CSC-235"))
    assert "CSC-125" in required
    assert required | alternative == {"CSC-121", "CSC-125"}
