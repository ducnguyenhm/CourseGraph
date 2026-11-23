import pytest

from app.schemas.prereq import parse
from app.services.projection import build_graph, project_course
from app.services.validation import CatalogError, find_cycle, find_dangling, resolve, validate

C = lambda c: {"type": "course", "course_id": c}  # noqa: E731


def test_or_edges_are_grouped_and_marked_alternative():
    tree = parse({"type": "or", "children": [C("CSC-231"), C("CSC-235")]})
    edges, badges = project_course("CSC-340", tree)

    assert {e.kind for e in edges} == {"alternative"}
    assert len({e.group for e in edges}) == 1, "or-siblings share one group"
    assert badges == []


def test_and_edges_are_required_and_ungrouped():
    tree = parse({"type": "and", "children": [C("CSC-231"), C("CSC-235")]})
    edges, _ = project_course("CSC-322", tree)

    assert {e.kind for e in edges} == {"required"}
    assert {e.group for e in edges} == {None}


def test_separate_or_groups_do_not_merge():
    """MATH-336 has three independent clauses; they must not share a group."""
    tree = parse(
        {
            "type": "and",
            "children": [
                {"type": "or", "children": [C("MATH-136"), C("MATH-151")]},
                {"type": "or", "children": [C("MATH-141"), C("ECON-350")]},
            ],
        }
    )
    edges, _ = project_course("MATH-336", tree)
    assert len({e.group for e in edges}) == 2


def test_non_course_leaves_become_badges():
    tree = parse(
        {
            "type": "and",
            "children": [
                {"type": "consent", "by": "chair"},
                {"type": "standing", "min_level": "senior"},
                {"type": "course_level", "subject": "CSC", "min_number": 300, "count": 1},
            ],
        }
    )
    edges, badges = project_course("CSC-498", tree)
    assert edges == []
    assert badges == ["consent:chair", "standing:min senior", "level:1x CSC 300+"]


def test_retired_reference_is_redirected_to_its_successor():
    """MATH-323 cites CSC-233, retired in favour of CSC-236."""
    tree = parse(C("CSC-233"))
    edges, _ = project_course("MATH-323", tree, {"CSC-233": "CSC-236"})
    assert [(e.source, e.via) for e in edges] == [("CSC-236", "CSC-233")]


def test_graph_drops_edges_to_uncurated_courses():
    courses = {"CSC-231": (parse(C("CSC-125")), "Computer Systems", 1.0, 1.0)}
    g = build_graph(courses)
    assert [n["id"] for n in g["nodes"]] == ["CSC-231"]
    assert g["edges"] == []


def test_equivalence_chains_resolve():
    assert resolve("A-100", {"A-100": "B-200", "B-200": "C-300"}) == "C-300"


def test_resolve_survives_a_cyclic_equivalence():
    assert resolve("A-100", {"A-100": "B-200", "B-200": "A-100"}) in {"A-100", "B-200"}


def test_dangling_references_are_reported():
    trees = {"CSC-231": parse(C("CSC-125"))}
    assert find_dangling(trees) == {"CSC-231": {"CSC-125"}}
    with pytest.raises(CatalogError, match="CSC-125"):
        validate(trees)


def test_reference_resolvable_by_equivalence_is_not_dangling():
    trees = {"MATH-323": parse(C("CSC-233")), "CSC-236": parse(None)}
    assert find_dangling(trees, {"CSC-233": "CSC-236"}) == {}


def test_cycle_is_detected():
    trees = {
        "CSC-101": parse(C("CSC-102")),
        "CSC-102": parse(C("CSC-103")),
        "CSC-103": parse(C("CSC-101")),
    }
    cycle = find_cycle(trees)
    assert cycle is not None and cycle[0] == cycle[-1]


def test_alternative_branch_is_not_a_cycle():
    """Taking the other branch always escapes, so this is satisfiable."""
    trees = {
        "CSC-101": parse({"type": "or", "children": [C("CSC-102"), C("CSC-103")]}),
        "CSC-102": parse(None),
        "CSC-103": parse(C("CSC-101")),
    }
    assert find_cycle(trees) is None


def test_coreq_pair_is_not_a_cycle():
    """MATH-332/441-style: a corequisite may be taken in the same term."""
    trees = {
        "MATH-331": parse({"type": "coreq", "course_id": "MATH-332"}),
        "MATH-332": parse({"type": "coreq", "course_id": "MATH-331"}),
    }
    assert find_cycle(trees) is None


def test_layers_place_prerequisites_before_dependents():
    courses = {
        "CSC-121": (parse(None), "CS I", 1.0, 1.0),
        "CSC-125": (parse(C("CSC-121")), "Software Dev", 1.0, 1.0),
        "CSC-235": (parse(C("CSC-125")), "Data Structures", 1.0, 1.0),
    }
    layers = {n["id"]: n["layer"] for n in build_graph(courses)["nodes"]}
    assert layers == {"CSC-121": 0, "CSC-125": 1, "CSC-235": 2}


def test_layer_takes_the_longest_path_not_the_shortest():
    """CSC-380 sits after CSC-236 even though MATH-141 is a layer-0 prereq."""
    courses = {
        "MATH-141": (parse(None), "Stats", 1.0, 1.0),
        "CSC-235": (parse(None), "Data Structures", 1.0, 1.0),
        "CSC-236": (parse(C("CSC-235")), "Algorithms", 1.0, 1.0),
        "CSC-380": (
            parse({"type": "and", "children": [C("CSC-236"), C("MATH-141")]}),
            "ML", 1.0, 1.0,
        ),
    }
    layers = {n["id"]: n["layer"] for n in build_graph(courses)["nodes"]}
    assert layers["CSC-380"] == 2


def test_coreq_does_not_push_a_course_into_a_later_layer():
    courses = {
        "MATH-441": (parse(None), "Probability", 1.0, 1.0),
        "MATH-442": (parse({"type": "coreq", "course_id": "MATH-441"}), "Seminar", 0.5, 0.5),
    }
    layers = {n["id"]: n["layer"] for n in build_graph(courses)["nodes"]}
    assert layers["MATH-442"] == 0


def test_depth_survives_filtering_and_hidden_prereqs_become_external():
    """Under 'CSC only', CSC-380 must stay after CSC-236's column and keep its
    MATH-141 edge, marked external rather than dropped."""
    courses = {
        "MATH-141": (parse(None), "Stats", 1.0, 1.0),
        "MATH-151": (parse(None), "Calc I", 1.0, 1.0),
        "MATH-152": (parse(C("MATH-151")), "Calc II", 1.0, 1.0),
        "CSC-380": (
            parse({"type": "and", "children": [C("MATH-152"), C("MATH-141")]}),
            "ML", 1.0, 1.0,
        ),
    }
    g = build_graph(courses, visible={"CSC-380"})

    assert [n["id"] for n in g["nodes"]] == ["CSC-380"]
    assert g["nodes"][0]["layer"] == 2, "depth from the full catalog, not the filtered view"
    assert {(e["source"], e["external"]) for e in g["edges"]} == {
        ("MATH-141", True),
        ("MATH-152", True),
    }


def test_edges_between_hidden_courses_are_not_returned():
    courses = {
        "MATH-151": (parse(None), "Calc I", 1.0, 1.0),
        "MATH-152": (parse(C("MATH-151")), "Calc II", 1.0, 1.0),
        "CSC-121": (parse(None), "CS I", 1.0, 1.0),
    }
    g = build_graph(courses, visible={"CSC-121"})
    assert g["edges"] == []
