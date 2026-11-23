from pathlib import Path

import pytest

from app.schemas.prereq import parse
from app.services.fixtures import check, parse_trees
from app.services.ordering import Orderer

DATA = Path(__file__).resolve().parent.parent / "data"
C = lambda c: {"type": "course", "course_id": c}  # noqa: E731


@pytest.fixture(scope="module")
def catalog() -> Orderer:
    fixtures = check([DATA / f"{s}_catalog_2025_26.json" for s in ("csc", "math", "econ")])
    return Orderer(parse_trees(fixtures), fixtures.renumbering)


def round_of(order, cid):
    return next(i for i, r in enumerate(order.rounds, 1) if cid in r)


def test_every_course_comes_after_everything_it_needs(catalog):
    order = catalog.program_order({"CSC-498", "CSC-340", "MATH-323", "ECON-450"})
    for cid in order.order:
        for need in catalog.place(cid).needs:
            assert round_of(order, need) < round_of(order, cid), (need, cid)


def test_or_is_not_ignored(catalog):
    """CSC-340 needs 231 or 235 — both in round 3 — so it lands in round 4,
    not round 3 as required-edges-only ordering would put it."""
    order = catalog.program_order({"CSC-340"})
    assert order.rounds[:3] == [["CSC-121"], ["CSC-125"], ["CSC-231"]]
    assert round_of(order, "CSC-340") == 4
    assert any("CSC 340: assumes CSC 231" in a for a in order.assumed)


def test_cs_major_core(catalog):
    order = catalog.program_order(
        {"CSC-121", "CSC-125", "CSC-231", "CSC-235", "CSC-236", "CSC-498", "MATH-123"}
    )
    assert order.rounds[0] == ["CSC-121", "MATH-123"]
    assert order.rounds[1] == ["CSC-125"]
    assert {"CSC-231", "CSC-235"} <= set(order.rounds[2])
    # CSC-498 needs senior standing and a 300-level CSC course; both are
    # reported as assumptions rather than hidden, and the empty rounds before
    # it are kept so round 7 still means the seventh term.
    assert order.rounds[-1] == ["CSC-498"]
    assert len(order.rounds) == 7 and order.rounds[4:6] == [[], []]
    assert any("CSC 498: senior standing" in a for a in order.assumed)
    assert any("CSC 498: assumes" in a for a in order.assumed)


def test_consent_is_never_the_assumed_way_in(catalog):
    """MATH-270 is 'MATH 152 or permission': a plan must not count on the
    permission, and CSC-498's 300-level course must not be Topics or
    Independent Study, which are open only by consent."""
    order = catalog.program_order({"MATH-270", "CSC-498"})
    assert round_of(order, "MATH-270") > round_of(order, "MATH-152")
    assert not {"CSC-396", "CSC-398", "CSC-496"} & set(order.order)


def test_retired_reference_orders_by_its_successor(catalog):
    order = catalog.program_order({"MATH-323"})
    assert "CSC-233" not in order.order
    if "CSC-236" in order.order:  # unless MATH-323's other branch was assumed
        assert round_of(order, "MATH-323") > round_of(order, "CSC-236")


def test_coreq_may_share_a_round():
    trees = {
        "MATH-441": parse(None),
        "MATH-442": parse({"type": "coreq", "course_id": "MATH-441"}),
    }
    order = Orderer(trees).program_order({"MATH-442"})
    assert order.rounds == [["MATH-441", "MATH-442"]]


def test_or_loop_terminates_and_takes_the_escape():
    trees = {
        "CSC-121": parse(None),
        "CSC-125": parse({"type": "or", "children": [C("CSC-121"), C("CSC-235")]}),
        "CSC-235": parse(C("CSC-125")),
    }
    order = Orderer(trees).program_order({"CSC-235"})
    assert order.rounds == [["CSC-121"], ["CSC-125"], ["CSC-235"]]
