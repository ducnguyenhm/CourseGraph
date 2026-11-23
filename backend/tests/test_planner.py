"""Checkpoint 4: the semester planner, `app/services/planner.py`.

Written before the code, as its contract. Pure Python with no database,
like the evaluator:

    Planner(trees, facts, *, current_term, terms_elapsed, credits=None, max_load=MAX_LOAD)
        trees    course id -> parsed prerequisite tree
        facts    StudentFacts: completed / in progress (planned is ignored;
                 the plan passed to each call is what counts)
        credits  course id -> credits, 1.0 when missing

    planner.terms(graduation) -> ["2026WI", "2026SP", "2026MY", "2026FA", ...]
        the planner's columns: every term after the current one, through
        graduation: Winter Term after each fall, May Term after each spring
        (since 2026-11-18; before that, fall and spring only). Standing still
        advances only with fall and spring. Winter and May Term are short
        terms: Extended Studies courses only (`extended`), at most 0.5 credit.

    planner.check(plan, course_id, term) -> Check
        would placing (or moving) the course there be valid?
    planner.place(plan, course_id, term, *, override=None) -> new plan
        raises Rejected(check) when the check fails and there is no override;
        an override is a justification note and only covers prerequisites
    planner.remove(plan, course_id) -> new plan
    planner.drop_term(plan, term)
        may `term` be taken out of the plan (`removed=`, since 2026-11-18)?
        ValueError unless it is a future planner term holding no courses.
        A removed term is not a column and takes no course until added back.
    planner.review(plan) -> Review
        every placement re-checked, after a move or a removal

    Placement(course_id, term, override=None)       a plan is a list of these
    Check: course_id, term, ok, unmet, confirm, message, load, overloaded, override
    Review: checks (course id -> Check), loads (term -> credits),
            overloaded (terms, in order), problems (not ok and not overridden)

A prerequisite counts when it is completed, in progress now, or placed in an
*earlier* term; a corequisite also counts in the same term. Standing follows
the program order's rule: the k-th term from now (1 = the next term) meets
`min_level` when k > STANDING_ROUNDS[min_level] - terms_elapsed. Consent and
placement tests are UNKNOWN, as in the evaluator: accepted, listed in
`confirm`. A term over `max_load` is a warning, never a rejection.
"""

import json
from pathlib import Path

import pytest

from app.schemas.prereq import parse
from app.services.evaluator import StudentFacts
from app.services.fixtures import check as check_fixtures
from app.services.fixtures import parse_trees
from app.services.semesters import current_term, terms_elapsed

from app.services.planner import MAX_LOAD, Placement, Planner, Rejected

pytestmark = pytest.mark.cp4

DATA = Path(__file__).resolve().parent.parent / "data"
FIXTURES = ("csc_catalog", "math_catalog", "econ_catalog", "other_stubs")
C = lambda c: {"type": "course", "course_id": c}  # noqa: E731


def make(
    prereqs: dict[str, dict | None],
    *,
    done=(),
    doing=(),
    credits=None,
    elapsed=4,
    current="2025FA",
    standing="junior",
    max_load=None,
    extended=(),
    removed=(),
):
    """prereqs: course id -> prerequisite tree (None = no prerequisite).
    extended: the Extended Studies courses, the only ones a short term takes."""
    facts = StudentFacts.build(done, doing, (), standing, (), [("CSC-122", "CSC-235", "renumber")])
    kw = {} if max_load is None else {"max_load": max_load}
    return Planner(
        {c: parse(t) for c, t in prereqs.items()},
        facts,
        current_term=current,
        terms_elapsed=elapsed,
        credits=credits,
        extended=extended,
        removed=removed,
        **kw,
    )


def P(*pairs):
    """P(("CSC-231", "2026SP"), ...) -> a plan."""
    return [Placement(c, t) for c, t in pairs]


def terms_of(plan):
    return {p.course_id: p.term for p in plan}


# -- columns ------------------------------------------------------------------


def test_columns_are_the_remaining_terms_with_winter_and_may_term():
    pl = make({})
    assert pl.terms("2027SP") == ["2026WI", "2026SP", "2026MY", "2026FA", "2027WI", "2027SP"]
    assert make({}, current="2026SP").terms("2027SP") == ["2026MY", "2026FA", "2027WI", "2027SP"]
    # During May Term or a summer, the next term is the fall.
    assert make({}, current="2026MY").terms("2027SP") == ["2026FA", "2027WI", "2027SP"]
    assert make({}, current="2026SU").terms("2027SP") == ["2026FA", "2027WI", "2027SP"]


ES = {"CSC-184": C("CSC-121"), "MATH-184": None, "CSC-121": None, "CSC-231": C("CSC-184")}


def test_short_terms_take_courses_in_order():
    pl = make(ES, extended=["CSC-184", "MATH-184"], credits={"CSC-184": 0.5, "MATH-184": 0.5})
    # Fall comes before the next Winter Term, and a May Term before the fall.
    assert pl.check(P(("CSC-121", "2026FA")), "CSC-184", "2027WI").ok
    assert not pl.check(P(("CSC-121", "2027SP")), "CSC-184", "2027WI").ok
    assert pl.check(P(("CSC-184", "2026MY")), "CSC-231", "2026FA").ok
    assert not pl.check(P(("CSC-184", "2026MY")), "CSC-231", "2026SP").ok


def test_short_terms_take_extended_studies_courses_only():
    # Catalog p. 23: Extended Studies courses are Winter or May Term courses.
    pl = make(ES, extended=["CSC-184", "MATH-184"])
    for term in ("2026WI", "2026MY"):
        c = pl.check([], "CSC-121", term)
        assert not c.ok and not c.overridable and "Extended Studies" in c.message
        with pytest.raises(Rejected):
            pl.place([], "CSC-121", term, override="offered this once")
    # Extended Studies courses still go in a fall or spring (a semester away).
    assert pl.check([], "MATH-184", "2026SP").ok


def test_short_terms_hold_half_a_credit():
    pl = make(ES, extended=["CSC-184", "MATH-184"], credits={"CSC-184": 0.5, "MATH-184": 0.5})
    assert pl.check(P(("CSC-121", "2026SP")), "MATH-184", "2026MY").load == 0.5
    c = pl.check(P(("CSC-121", "2026FA"), ("MATH-184", "2027WI")), "CSC-184", "2027WI")
    assert not c.ok and not c.overridable and c.load == 1.0 and "0.5" in c.message
    # A zero-credit project fits beside one.
    pl0 = make(ES, extended=["CSC-184", "MATH-184"], credits={"CSC-184": 0.5, "MATH-184": 0.0})
    assert pl0.check(P(("CSC-184", "2026MY")), "MATH-184", "2026MY").ok


def test_removed_terms_leave_the_columns_and_take_no_courses():
    # A semester off, an internship, a May Term skipped: the student says so.
    pl = make({"ART-100": None}, removed=["2026SP", "2026MY"])
    assert pl.terms("2026FA") == ["2026WI", "2026FA"]
    c = pl.check([], "ART-100", "2026SP")
    assert not c.ok and not c.overridable and "removed" in c.message
    assert pl.check([], "ART-100", "2026FA").ok


def test_a_term_is_dropped_only_when_empty_and_ahead():
    pl = make({"ART-100": None})
    pl.drop_term([], "2026MY")
    with pytest.raises(ValueError, match="ART 100"):
        pl.drop_term(P(("ART-100", "2026SP")), "2026SP")
    for term in ("2025FA", "2025SP", "2026SU", "2026XX"):
        with pytest.raises(ValueError):
            pl.drop_term([], term)


def test_summer_is_not_a_planner_column():
    c = make({"ART-100": None}).check([], "ART-100", "2026SU")
    assert not c.ok and not c.overridable


# -- prerequisite validation ---------------------------------------------------


def test_completed_prerequisite_accepts():
    pl = make({"ART-200": C("ART-100")}, done=["ART-100"])
    c = pl.check([], "ART-200", "2026SP")
    assert c.ok and c.unmet == [] and c.message is None


def test_in_progress_prerequisite_accepts_next_term():
    # Registration for spring happens while the fall prerequisite is under way.
    pl = make({"ART-200": C("ART-100")}, doing=["ART-100"])
    assert pl.check([], "ART-200", "2026SP").ok


def test_missing_prerequisite_rejects_naming_it():
    pl = make({"CSC-322": C("CSC-231")})
    c = pl.check([], "CSC-322", "2026SP")
    assert not c.ok
    assert c.unmet == ["CSC 231"]
    assert "CSC 231" in c.message and "CSC 322" in c.message


def test_prerequisite_placed_in_an_earlier_term_accepts():
    pl = make({"CSC-231": None, "CSC-322": C("CSC-231")})
    assert pl.check(P(("CSC-231", "2026SP")), "CSC-322", "2026FA").ok


def test_prerequisite_in_the_same_term_rejects():
    pl = make({"CSC-231": None, "CSC-322": C("CSC-231")})
    c = pl.check(P(("CSC-231", "2026FA")), "CSC-322", "2026FA")
    assert not c.ok and c.unmet == ["CSC 231"]


def test_prerequisite_in_a_later_term_rejects():
    pl = make({"CSC-231": None, "CSC-322": C("CSC-231")})
    assert not pl.check(P(("CSC-231", "2027SP")), "CSC-322", "2026FA").ok


def test_and_names_only_the_missing_part():
    pl = make({"CSC-322": {"type": "and", "children": [C("CSC-231"), C("CSC-235")]}}, done=["CSC-231"])
    c = pl.check([], "CSC-322", "2026SP")
    assert c.unmet == ["CSC 235"]


def test_or_accepts_either_branch_and_lists_choices_when_neither():
    tree = {"type": "or", "children": [C("CSC-231"), C("CSC-235")]}
    assert make({"CSC-340": tree}, done=["CSC-235"]).check([], "CSC-340", "2026SP").ok
    pl = make({"CSC-231": None, "CSC-340": tree})
    assert pl.check(P(("CSC-231", "2026SP")), "CSC-340", "2026FA").ok
    c = pl.check([], "CSC-340", "2026SP")
    assert not c.ok
    assert "CSC 231" in c.message and "CSC 235" in c.message


def test_renumbered_prerequisite_counts():
    # CSC 122 on the record is CSC 235 now.
    pl = make({"CSC-322": C("CSC-235")}, done=["CSC-122"])
    assert pl.check([], "CSC-322", "2026SP").ok


def test_corequisite_counts_in_the_same_term_but_not_a_later_one():
    pl = make({"PHYS-120": None, "PHYS-121": {"type": "coreq", "course_id": "PHYS-120"}})
    assert pl.check(P(("PHYS-120", "2026SP")), "PHYS-121", "2026SP").ok
    assert pl.check(P(("PHYS-120", "2026SP")), "PHYS-121", "2026FA").ok
    late = pl.check(P(("PHYS-120", "2026FA")), "PHYS-121", "2026SP")
    assert not late.ok and "PHYS 120" in late.message
    assert not pl.check([], "PHYS-121", "2026SP").ok


def test_consent_is_accepted_but_flagged_for_confirmation():
    pl = make({"CSC-399": {"type": "consent", "by": "instructor"}})
    c = pl.check([], "CSC-399", "2026SP")
    assert c.ok
    assert c.confirm == ["consent of the instructor"]


def test_standing_is_projected_to_the_target_term():
    # Four terms behind; senior needs six, so not before the third term from now.
    pl = make({"CSC-498": {"type": "standing", "min_level": "senior"}}, elapsed=4, extended=["CSC-498"], credits={"CSC-498": 0.5})
    assert not pl.check([], "CSC-498", "2026SP").ok
    no = pl.check([], "CSC-498", "2026FA")
    assert not no.ok and "senior" in no.message
    assert pl.check([], "CSC-498", "2027SP").ok
    # A May Term is not a semester: it does not move standing on.
    assert not pl.check([], "CSC-498", "2026MY").ok
    # The Winter Term after the second fall from now has six semesters behind it.
    assert pl.check([], "CSC-498", "2027WI").ok


def test_course_level_counts_earlier_placements_but_not_the_course_itself():
    level = {"type": "course_level", "subject": "CSC", "min_number": 300, "count": 1}
    pl = make({"CSC-322": None, "CSC-498": level})
    assert not pl.check([], "CSC-498", "2026SP").ok
    assert not pl.check(P(("CSC-322", "2026FA")), "CSC-498", "2026FA").ok
    assert pl.check(P(("CSC-322", "2026SP")), "CSC-498", "2026FA").ok
    # CSC 498 is itself 400-level; being placed must not satisfy its own rule.
    assert not pl.check(P(("CSC-498", "2026SP")), "CSC-498", "2026FA").ok


# -- plan integrity -------------------------------------------------------------


@pytest.mark.parametrize("term", ["2025FA", "2025SP", "2025MY"])
def test_only_future_terms_accept(term):
    pl = make({"ART-100": None})
    c = pl.check([], "ART-100", term)
    assert not c.ok and term in c.message


def test_completed_or_in_progress_course_rejects():
    pl = make({"ART-100": None, "ART-101": None}, done=["ART-100"], doing=["ART-101"])
    assert not pl.check([], "ART-100", "2026SP").ok
    assert not pl.check([], "ART-101", "2026SP").ok


def test_place_returns_a_new_plan_and_leaves_the_old_one():
    pl = make({"ART-100": None})
    before = []
    after = pl.place(before, "ART-100", "2026SP")
    assert before == []
    assert after == P(("ART-100", "2026SP"))


def test_placing_a_planned_course_again_moves_it():
    pl = make({"ART-100": None})
    plan = pl.place(P(("ART-100", "2026SP")), "ART-100", "2027SP")
    assert plan == P(("ART-100", "2027SP"))


def test_place_raises_rejected_with_the_check():
    pl = make({"CSC-322": C("CSC-231")})
    with pytest.raises(Rejected) as err:
        pl.place([], "CSC-322", "2026SP")
    assert err.value.check.unmet == ["CSC 231"]
    assert "CSC 231" in str(err.value)


def test_moving_a_prerequisite_late_breaks_its_dependent():
    pl = make({"CSC-231": None, "CSC-322": C("CSC-231")})
    plan = P(("CSC-231", "2026SP"), ("CSC-322", "2026FA"))
    assert pl.review(plan).problems == []
    # The move itself is fine; the course that needed it is not.
    moved = pl.place(plan, "CSC-231", "2027SP")
    r = pl.review(moved)
    assert [c.course_id for c in r.problems] == ["CSC-322"]
    assert r.checks["CSC-322"].unmet == ["CSC 231"]


def test_removing_a_prerequisite_breaks_its_dependent():
    pl = make({"CSC-231": None, "CSC-322": C("CSC-231")})
    plan = pl.remove(P(("CSC-231", "2026SP"), ("CSC-322", "2026FA")), "CSC-231")
    assert terms_of(plan) == {"CSC-322": "2026FA"}
    assert [c.course_id for c in pl.review(plan).problems] == ["CSC-322"]


# -- credit overload ------------------------------------------------------------


def test_default_threshold_is_the_catalog_maximum():
    assert MAX_LOAD == 4.5


def test_loads_sum_credits_per_term_including_fractions():
    pl = make({"ART-101": None, "ART-102": None, "ART-103": None}, credits={"ART-102": 0.5})
    r = pl.review(P(("ART-101", "2026SP"), ("ART-102", "2026SP"), ("ART-103", "2026FA")))
    assert r.loads == {"2026SP": 1.5, "2026FA": 1.0}


def test_at_the_threshold_is_not_an_overload():
    courses = {f"ART-10{i}": None for i in range(5)}
    pl = make(courses, credits={"ART-104": 0.5})
    plan = P(*[(c, "2026SP") for c in courses])  # 4.5
    r = pl.review(plan)
    assert r.loads["2026SP"] == 4.5 and r.overloaded == []


def test_overload_warns_but_still_places():
    courses = {f"ART-10{i}": None for i in range(5)}
    pl = make(courses)
    plan = P(*[(f"ART-10{i}", "2026SP") for i in range(4)])
    c = pl.check(plan, "ART-104", "2026SP")
    assert c.ok and c.overloaded and c.load == 5.0
    plan = pl.place(plan, "ART-104", "2026SP")
    assert pl.review(plan).overloaded == ["2026SP"]


def test_threshold_is_configurable():
    courses = {f"ART-10{i}": None for i in range(5)}
    plan = P(*[(c, "2026SP") for c in courses])
    assert make(courses).review(plan).overloaded == ["2026SP"]
    assert make(courses, max_load=5.0).review(plan).overloaded == []


def test_overloaded_terms_come_in_term_order():
    courses = {f"ART-10{i}": None for i in range(10)}
    plan = P(*[(f"ART-10{i}", "2027SP") for i in range(5)], *[(f"ART-10{i}", "2026FA") for i in range(5, 10)])
    assert make(courses).review(plan).overloaded == ["2026FA", "2027SP"]


# -- override -------------------------------------------------------------------


def test_override_records_a_rejected_placement_with_its_note():
    pl = make({"CSC-322": C("CSC-231")})
    plan = pl.place([], "CSC-322", "2026SP", override="Instructor waived CSC 231")
    assert plan == [Placement("CSC-322", "2026SP", "Instructor waived CSC 231")]
    c = pl.review(plan).checks["CSC-322"]
    # Still unmet, and says so, but recorded on purpose: not a problem.
    assert not c.ok and c.unmet == ["CSC 231"]
    assert c.override == "Instructor waived CSC 231"
    assert pl.review(plan).problems == []


@pytest.mark.parametrize("note", ["", "   "])
def test_override_needs_a_justification(note):
    pl = make({"CSC-322": C("CSC-231")})
    with pytest.raises(ValueError):
        pl.place([], "CSC-322", "2026SP", override=note)


def test_override_covers_standing_too():
    pl = make({"CSC-498": {"type": "standing", "min_level": "senior"}}, elapsed=4)
    plan = pl.place([], "CSC-498", "2026SP", override="Dean approved early capstone")
    assert pl.review(plan).problems == []


def test_override_does_not_cover_plan_integrity():
    pl = make({"ART-100": None}, done=["ART-100"])
    with pytest.raises(Rejected):
        pl.place([], "ART-100", "2026SP", override="retake")
    with pytest.raises(Rejected):
        make({"ART-100": None}).place([], "ART-100", "2025FA", override="late add")


def test_overridden_placement_satisfies_later_courses():
    pl = make({"CSC-322": C("CSC-231"), "CSC-440": C("CSC-322")})
    plan = pl.place([], "CSC-322", "2026SP", override="consent")
    assert pl.check(plan, "CSC-440", "2026FA").ok


def test_moving_an_overridden_placement_drops_the_override():
    pl = make({"CSC-231": None, "CSC-322": C("CSC-231")})
    plan = P(("CSC-231", "2026SP"))
    plan = pl.place(plan, "CSC-322", "2026SP", override="consent")
    plan = pl.place(plan, "CSC-322", "2026FA")  # now valid on its own
    assert terms_of(plan)["CSC-322"] == "2026FA"
    assert next(p for p in plan if p.course_id == "CSC-322").override is None


# -- the demo student over the real fixtures ------------------------------------


@pytest.fixture(scope="module")
def demo():
    fx = check_fixtures([DATA / f"{n}_2025_26.json" for n in FIXTURES])
    student = json.loads((DATA / "demo_student.json").read_text())["students"][0]
    rows = student["enrollments"]
    facts = StudentFacts.build(
        [e["course_id"] for e in rows if e["status"] == "completed"],
        [e["course_id"] for e in rows if e["status"] == "in_progress"],
        (),
        student["class_standing"],
        student["programs"],
        [(e["from"], e["to"], e["relation"]) for e in fx.equivalences],
    )
    credits = {e["id"]: e["credits_max"] for e in fx.entries if e.get("credits_max") is not None}
    planner = Planner(
        parse_trees(fx),
        facts,
        current_term=current_term((e["term"], e["status"]) for e in rows),
        terms_elapsed=terms_elapsed([e["term"] for e in rows], student["class_standing"]),
        credits=credits,
    )
    plan = [Placement(p["course_id"], p["term"]) for p in student["plan"]]
    return planner, plan, student


def test_demo_columns_run_to_graduation(demo):
    planner, _, student = demo
    assert planner.terms(student["expected_graduation"]) == [
        "2026WI", "2026SP", "2026MY", "2026FA", "2027WI", "2027SP"
    ]


def test_demo_plan_is_clean(demo):
    # The walkthrough starts from this plan; it must not open on an error.
    planner, plan, _ = demo
    r = planner.review(plan)
    assert r.problems == [] and r.overloaded == []


def test_demo_rejection_then_acceptance(demo):
    """The presentation's first beat: CSC 498 too early, then in a valid term."""
    planner, plan, _ = demo
    plan = planner.remove(plan, "CSC-498")
    early = planner.check(plan, "CSC-498", "2026SP")
    assert not early.ok and "senior" in early.message
    assert planner.check(plan, "CSC-498", "2026FA").ok


def test_demo_unmet_course_prerequisite_is_named(demo):
    # ECON 280 needs ECON 220, which the demo student has not taken.
    planner, plan, _ = demo
    c = planner.check(plan, "ECON-280", "2026SP")
    assert not c.ok and c.unmet == ["ECON 220"] and "ECON 220" in c.message
    plan = planner.place(plan, "ECON-220", "2026SP")  # ECON 100 done
    assert not planner.check(plan, "ECON-280", "2026SP").ok
    assert planner.check(plan, "ECON-280", "2026FA").ok


def test_demo_in_progress_and_renumbered_prerequisites(demo):
    planner, plan, _ = demo
    assert planner.check(plan, "CSC-440", "2026SP").ok  # CSC 236 in progress
    assert planner.check(plan, "CSC-428", "2026SP").ok  # CSC 122 counts as CSC 235
