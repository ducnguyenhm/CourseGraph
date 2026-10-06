"""One test per leaf type, plus the combinations the demo student exercises."""

from app.schemas.prereq import parse
from app.services.evaluator import StudentFacts, Tri, evaluate, status

C = lambda c: {"type": "course", "course_id": c}  # noqa: E731
EQ = [
    ("CSC-122", "CSC-235", "renumber"),
    ("CSC-233", "CSC-236", "renumber"),
    ("MATH-136", "MATH-151", "satisfies"),
]


def facts(completed=(), in_progress=(), planned=(), standing="sophomore", programs=()):
    return StudentFacts.build(completed, in_progress, planned, standing, programs, EQ)


def ev(tree, f):
    return evaluate(parse(tree), f)


def test_no_prerequisite_is_satisfied():
    assert ev(None, facts()).value == Tri.TRUE


def test_course_leaf():
    assert ev(C("CSC-121"), facts(["CSC-121"])).value == Tri.TRUE
    r = ev(C("CSC-121"), facts())
    assert (r.value, r.unmet) == (Tri.FALSE, ["CSC 121"])


def test_in_progress_counts_as_satisfied():
    assert ev(C("CSC-236"), facts(in_progress=["CSC-236"])).value == Tri.TRUE


def test_renumbered_transcript_entry_satisfies_the_new_number():
    """Took CSC 122 before the renumbering; CSC 235 is what it is now."""
    assert ev(C("CSC-235"), facts(["CSC-122"])).value == Tri.TRUE


def test_reference_to_a_retired_number_is_satisfied_by_its_successor():
    """MATH-323 cites CSC-233; a student holding CSC-236 meets it."""
    assert ev(C("CSC-233"), facts(["CSC-236"])).value == Tri.TRUE


def test_satisfies_is_additive():
    """MATH-136 counts as MATH-151 and still counts as itself."""
    f = facts(["MATH-136"])
    assert ev(C("MATH-151"), f).value == Tri.TRUE
    assert ev(C("MATH-136"), f).value == Tri.TRUE


def test_consent_is_unknown_never_false():
    r = ev({"type": "consent", "by": "instructor"}, facts())
    assert (r.value, r.unmet) == (Tri.UNKNOWN, ["consent of the instructor"])


def test_course_or_consent_is_unknown_when_the_course_is_missing():
    """ECON-360 shape: 'ECON 350 or permission of instructor'."""
    tree = {"type": "or", "children": [C("ECON-350"), {"type": "consent", "by": "instructor"}]}
    assert ev(tree, facts()).value == Tri.UNKNOWN
    assert ev(tree, facts(["ECON-350"])).value == Tri.TRUE


def test_coreq_missing_is_unknown():
    r = ev({"type": "coreq", "course_id": "MATH-441"}, facts())
    assert r.value == Tri.UNKNOWN


def test_standing_lower_and_upper_bounds():
    senior_only = {"type": "standing", "min_level": "senior"}
    first_years_only = {"type": "standing", "max_level": "first_year"}
    assert ev(senior_only, facts(standing="junior")).value == Tri.FALSE
    assert ev(senior_only, facts(standing="senior")).value == Tri.TRUE
    assert ev(first_years_only, facts(standing="first_year")).value == Tri.TRUE
    assert ev(first_years_only, facts(standing="sophomore")).value == Tri.FALSE


def test_course_level_counts_current_numbers_once():
    tree = {"type": "course_level", "subject": "CSC", "min_number": 300, "count": 1}
    assert ev(tree, facts(["CSC-231"])).value == Tri.FALSE
    assert ev(tree, facts(["CSC-340"])).value == Tri.TRUE


def test_program_node():
    tree = {"type": "program", "program_id": "MAJOR-MATH"}
    assert ev(tree, facts(programs=["MAJOR-MATH"])).value == Tri.TRUE
    assert ev(tree, facts(programs=["MAJOR-CSC"])).value == Tri.FALSE


def test_placement_is_unknown():
    assert ev({"type": "placement", "test": "MATH"}, facts()).value == Tri.UNKNOWN


def test_and_is_min_and_names_every_unmet_part():
    tree = {"type": "and", "children": [C("CSC-231"), C("CSC-235"), C("CSC-121")]}
    r = ev(tree, facts(["CSC-121"]))
    assert (r.value, r.unmet) == (Tri.FALSE, ["CSC 231", "CSC 235"])


def test_or_is_max_and_offers_the_open_choices():
    tree = {"type": "or", "children": [C("CSC-231"), C("CSC-235")]}
    r = ev(tree, facts())
    assert (r.value, r.unmet) == (Tri.FALSE, ["one of: CSC 231 / CSC 235"])


def test_csc_498_for_a_junior():
    """Senior standing is the blocker even with every course in hand."""
    tree = {
        "type": "and",
        "children": [
            C("CSC-231"),
            C("CSC-235"),
            C("CSC-236"),
            {"type": "standing", "min_level": "senior"},
            {"type": "course_level", "subject": "CSC", "min_number": 300, "count": 1},
        ],
    }
    r = ev(tree, facts(["CSC-231", "CSC-122", "CSC-236"], standing="junior"))
    assert r.value == Tri.FALSE
    assert r.unmet == ["senior standing", "1 more CSC course(s) numbered 300+"]


def test_status_precedence():
    f = facts(["CSC-121"], in_progress=["CSC-125"], planned=["CSC-231"])
    assert status("CSC-121", parse(None), f)[0] == "completed"
    assert status("CSC-125", parse(C("CSC-121")), f)[0] == "planned"
    assert status("CSC-231", parse(C("CSC-125")), f)[0] == "planned"
    assert status("CSC-235", parse(C("CSC-125")), f)[0] == "eligible"
    assert status("CSC-322", parse(C("CSC-999")), f)[0] == "locked"


def test_consent_only_course_is_eligible_not_locked():
    tree = parse({"type": "or", "children": [C("ECON-350"), {"type": "consent", "by": "instructor"}]})
    name, result = status("ECON-360", tree, facts())
    assert name == "eligible" and result.value == Tri.UNKNOWN
