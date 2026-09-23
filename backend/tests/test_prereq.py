import pytest

from app.schemas.prereq import course_ids, normalize_id, parse, required_ids

C = lambda c: {"type": "course", "course_id": c}  # noqa: E731


def test_and_and_or_are_not_interchangeable():
    """The defect that motivated expression trees: a flat edge list renders
    'A and B' and 'A or B' identical."""
    conj = parse({"type": "and", "children": [C("CSC-231"), C("CSC-235")]})
    disj = parse({"type": "or", "children": [C("CSC-231"), C("CSC-235")]})

    assert course_ids(conj) == course_ids(disj) == {"CSC-231", "CSC-235"}
    assert required_ids(conj) == {"CSC-231", "CSC-235"}
    assert required_ids(disj) == set()


def test_or_contributes_only_its_shared_courses():
    """MATH-348 shape: (141|350|375) AND (151 | (135 AND 136))."""
    tree = parse(
        {
            "type": "or",
            "children": [
                {"type": "and", "children": [C("CSC-231"), C("CSC-235")]},
                {"type": "and", "children": [C("CSC-231"), C("CSC-236")]},
            ],
        }
    )
    assert required_ids(tree) == {"CSC-231"}


def test_consent_is_a_leaf_not_a_course():
    tree = parse(
        {"type": "or", "children": [C("MATH-152"), {"type": "consent", "by": "instructor"}]}
    )
    assert course_ids(tree) == {"MATH-152"}
    assert required_ids(tree) == set()


def test_coreq_does_not_constrain_ordering():
    """CSC-330 is 'pre- or co-requisite: CSC 236'."""
    tree = parse({"type": "coreq", "course_id": "CSC-236"})
    assert course_ids(tree) == {"CSC-236"}
    assert required_ids(tree) == set()


def test_null_prereq_becomes_none_node():
    assert parse(None).type == "none"


def test_standing_accepts_an_upper_bound():
    """CSC-197 is first-years only — a max, not a min."""
    node = parse({"type": "standing", "max_level": "first_year"})
    assert node.max_level == "first_year" and node.min_level is None


def test_standing_needs_some_bound():
    with pytest.raises(Exception):
        parse({"type": "standing"})


def test_course_level_and_program_nodes():
    """CSC-498 requires a 300+ CSC course; MATH-495 a declared major."""
    lvl = parse({"type": "course_level", "subject": "CSC", "min_number": 300, "count": 1})
    assert (lvl.subject, lvl.min_number, lvl.count) == ("CSC", 300, 1)
    assert parse({"type": "program", "program_id": "MAJOR-MATH"}).program_id == "MAJOR-MATH"


@pytest.mark.parametrize("raw", ["csc 235", "CSC-235", "CSC235", "csc235Q"])
def test_id_normalization_strips_competence_suffix(raw):
    assert normalize_id(raw) == "CSC-235"


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "course", "course_id": "nonsense"},
        {"type": "and", "children": [C("CSC-231")]},
        {"type": "bogus"},
        {"type": "consent", "by": "provost"},
    ],
)
def test_malformed_trees_are_rejected(bad):
    with pytest.raises(Exception):
        parse(bad)
