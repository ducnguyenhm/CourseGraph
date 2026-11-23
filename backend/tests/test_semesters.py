"""The minimum-semester estimate: both bounds, which one binds, and how the
remaining work is read off the audits."""

import json
from datetime import date
from pathlib import Path

import pytest

from app.schemas.prereq import parse
from app.services.fixtures import check, parse_trees
from app.services.ordering import Orderer
from app.services.programs import to_rows
from app.services.requirements import CourseInfo, Engine, Record
from app.services.semesters import (
    academic_year,
    calendar_term,
    current_term,
    estimate,
    next_primary,
    past_terms,
    starting_term,
    terms_between,
    terms_elapsed,
    terms_from,
)

DATA = Path(__file__).resolve().parent.parent / "data"
C = lambda c: {"type": "course", "course_id": c}  # noqa: E731


def course(cid, **kw):
    return {"rule": "specific_course", "course_id": cid, **kw}


def all_of(*children):
    return {"rule": "all_of", "label": "", "children": list(children)}


def run(
    prereqs: dict[str, dict | None],
    tree: dict,
    *,
    done=(),
    planned=(),
    credits=None,
    extra_programs=(),
    elapsed=4,
    current="2025FA",
    graduation="2027SP",
    max_load=4.5,
    removed=(),
):
    """prereqs: course id -> prerequisite tree (None = no prerequisite)."""
    credits = credits or {}
    catalog = {
        cid: CourseInfo(cid.split("-")[0], int(cid.split("-")[1]), credits.get(cid, 1.0))
        for cid in prereqs
    }
    taken = [(c, "completed", None) for c in done] + [(c, "planned", None) for c in planned]
    engine = Engine(Record.build(taken, catalog), catalog)
    orderer = Orderer(
        {c: parse(t) for c, t in prereqs.items()}, done=set(done), terms_elapsed=elapsed
    )
    audits = [engine.audit("P", to_rows(tree))] + [
        engine.audit(f"P{i}", to_rows(t)) for i, t in enumerate(extra_programs, 2)
    ]
    return estimate(
        engine, orderer, audits, current_term=current, graduation=graduation, max_load=max_load,
        removed=removed,
    )


# -- terms -------------------------------------------------------------------


def test_term_arithmetic():
    assert next_primary("2025FA") == "2026SP"
    assert next_primary("2026SP") == "2026FA"
    assert next_primary("2026WI") == "2026SP"
    assert next_primary("2026MY") == "2026FA"
    # 2026SP, 2026FA, 2027SP
    assert terms_between("2025FA", "2027SP") == 3
    assert terms_between("2027SP", "2027SP") == 0
    assert terms_between(None, "2027SP") == 0


def test_academic_year_runs_from_fall_through_summer():
    assert academic_year("2025FA") == 2025
    assert [academic_year(t) for t in ("2026WI", "2026SP", "2026MY", "2026SU")] == [2025] * 4
    assert academic_year("2026FA") == 2026


def test_past_terms_fill_every_academic_year_since_the_start():
    # The planner shows the whole degree: from the fall the student's first
    # year began, every planner term through the current one.
    assert past_terms("2025FA", "2026SP", []) == ["2025FA", "2026WI", "2026SP"]
    # Starting in a spring still shows that year's fall, so rows line up.
    assert past_terms("2026SP", "2026SP", []) == ["2025FA", "2026WI", "2026SP"]
    # A summer on the record gets its own column; with no start term the
    # earliest course decides.
    assert past_terms(None, "2026FA", ["2026SU", "2025FA"]) == [
        "2025FA", "2026WI", "2026SP", "2026MY", "2026SU", "2026FA"
    ]
    assert past_terms(None, "2026FA", []) == []


def test_current_term_is_the_one_in_progress():
    assert current_term([("2024FA", "completed"), ("2025SP", "in_progress")]) == "2025SP"
    assert current_term([("2024FA", "completed"), ("2025WI", "completed")]) == "2025WI"
    assert current_term([]) is None


def test_calendar_term_follows_the_academic_year():
    assert calendar_term(date(2026, 11, 18)) == "2026FA"
    assert calendar_term(date(2027, 2, 1)) == "2027SP"
    # Summer leads into fall, so the next term to plan is that fall.
    assert calendar_term(date(2026, 6, 15)) == "2026SU"
    assert next_primary(calendar_term(date(2026, 6, 15))) == "2026FA"


def test_a_record_with_no_courses_starts_from_today_or_its_first_term():
    # A new account with nothing entered yet: where its plan begins.
    today = date(2026, 11, 18)
    assert starting_term("2025FA", today) == "2026FA"
    assert starting_term(None, today) == "2026FA"
    # Not started yet: the plan's first term is the start term itself.
    assert next_primary(starting_term("2027FA", today)) == "2027FA"
    assert next_primary(starting_term("2027SP", today)) == "2027SP"


def test_terms_elapsed_counts_fall_and_spring_but_trusts_standing():
    assert terms_elapsed(["2024FA", "2025WI", "2025SP", "2025SP"], "sophomore") == 2
    # A junior whose record starts late still has four terms behind them.
    assert terms_elapsed(["2025FA"], "junior") == 4


def test_terms_elapsed_from_a_start_term_replaces_standing():
    # Fall 2023 through fall 2026: seven fall/spring terms, whatever was taken.
    assert terms_elapsed(["2026FA"], "first_year", start="2023FA", current="2026FA") == 7
    # A start term says less than standing would: start wins.
    assert terms_elapsed([], "senior", start="2025FA", current="2026SP") == 2
    # Without a current term the start term cannot be used.
    assert terms_elapsed([], "junior", start="2023FA") == 4


def test_terms_from_rounds_short_terms_to_fall_and_spring():
    assert terms_from("2024SP", "2024SP") == 1
    assert terms_from("2024WI", "2024FA") == 2  # spring, fall
    assert terms_from("2024SU", "2025WI") == 1  # fall 2024 only
    assert terms_from("2025FA", "2025SP") == 0


# -- the two bounds ----------------------------------------------------------


CHAIN = {"CSC-121": None, "CSC-125": C("CSC-121"), "CSC-231": C("CSC-125"), "CSC-235": C("CSC-231")}


def test_chain_binds_when_courses_must_follow_one_another():
    """Three courses, few credits, but each needs the one before: three terms."""
    r = run(CHAIN, course("CSC-235"), done=["CSC-121"])
    assert r.chain == ["CSC-125", "CSC-231", "CSC-235"]
    assert (r.chain_bound, r.credit_bound, r.estimate, r.binding) == (3, 1, 3, "chain")
    assert [n.kind for n in r.needs] == ["prerequisite", "prerequisite", "required"]


def test_credits_bind_when_there_is_simply_a_lot_left():
    """Ten independent courses: one round deep, but 10 / 4.5 -> 3 terms."""
    many = {f"HIST-1{i:02d}": None for i in range(10)}
    r = run(many, all_of(*(course(c) for c in many)))
    assert (r.chain_bound, r.credit_bound, r.estimate, r.binding) == (1, 3, 3, "credits")
    assert run(many, all_of(*(course(c) for c in many)), max_load=5).credit_bound == 2


def test_both_bounds_equal():
    r = run(CHAIN, course("CSC-235"), done=["CSC-121"], max_load=1)
    assert (r.chain_bound, r.credit_bound, r.binding) == (3, 3, "both")


def test_nothing_left():
    r = run(CHAIN, course("CSC-121"), done=["CSC-121"])
    assert (r.estimate, r.binding, r.feasible, r.needs) == (0, "none", True, [])


def test_feasibility_against_terms_left():
    r = run(CHAIN, course("CSC-235"), done=["CSC-121"], current="2026SP", graduation="2027SP")
    assert r.terms_left == 2 and not r.feasible


def test_a_semester_taken_out_of_the_plan_is_not_a_term_left():
    # A fall away from campus leaves one semester before graduation, not two;
    # a May Term skipped changes nothing, since the estimate counts semesters.
    r = run(CHAIN, course("CSC-235"), done=["CSC-121"], current="2026SP", removed=["2026FA", "2027MY"])
    assert r.terms_left == 1
    r = run(CHAIN, course("CSC-235"), done=["CSC-121"], current="2026SP", removed=["2026MY", "2025FA"])
    assert r.terms_left == 2


def test_degree_credit_floor_raises_the_credit_bound():
    """Only one course is named, but 31 credits are required overall and 20
    are done, so 11 remain: 3 terms at 4.5."""
    filler = {f"ENG-1{i:02d}": None for i in range(20)}
    prereqs = {**filler, "CSC-121": None}
    tree = all_of(course("CSC-121"), {"rule": "credit_minimum", "credits": 31})
    r = run(prereqs, tree, done=list(filler))
    assert r.remaining_credits == 11 and r.credit_bound == 3
    assert "degree minimum" in r.credit_basis


# -- what counts as remaining ------------------------------------------------


def test_done_courses_cost_nothing_and_planned_ones_do():
    r = run(CHAIN, all_of(course("CSC-121"), course("CSC-125")), done=["CSC-121"], planned=["CSC-125"])
    assert [(n.course_id, n.kind, n.round) for n in r.needs] == [("CSC-125", "planned", 1)]


def test_a_coreq_already_done_does_not_place_a_course_before_next_term():
    prereqs = {"CSC-236": None, "CSC-330": {"type": "coreq", "course_id": "CSC-236"}}
    r = run(prereqs, course("CSC-330"), done=["CSC-236"])
    assert r.needs[0].round == 1


def test_standing_waits_count_from_where_the_student_is():
    prereqs = {"CSC-498": {"type": "standing", "min_level": "senior"}}
    # Five terms behind (a junior finishing fall): senior standing after one more.
    assert run(prereqs, course("CSC-498"), elapsed=5).needs[0].round == 2
    assert run(prereqs, course("CSC-498"), elapsed=6).needs[0].round == 1
    # From scratch, the CP2 program order's answer: semester seven.
    assert run(prereqs, course("CSC-498"), elapsed=0).needs[0].round == 7


def test_a_choice_prefers_a_course_already_needed_elsewhere():
    """Program P needs MATH-341; P2 needs one of MATH-247 / MATH-341. P2 takes
    341, which counts twice, rather than adding 247."""
    prereqs = {"MATH-247": None, "MATH-341": None}
    r = run(
        prereqs,
        course("MATH-341"),
        extra_programs=[{"rule": "n_from_set", "n": 1, "courses": ["MATH-247", "MATH-341"]}],
    )
    assert [n.course_id for n in r.needs] == ["MATH-341"]
    assert len(r.needs[0].reasons) == 2


def test_a_choice_prefers_fewer_extra_prerequisites():
    prereqs = {"MATH-331": None, "MATH-332": C("MATH-331"), "MATH-336": None}
    tree = {"rule": "n_from_set", "n": 1, "courses": ["MATH-332", "MATH-336"]}
    assert [n.course_id for n in run(prereqs, tree).needs] == ["MATH-336"]


def test_choices_avoid_consent_only_courses():
    prereqs = {"CSC-396": {"type": "consent", "by": "instructor"}, "CSC-399": C("CSC-121"), "CSC-121": None}
    tree = {"rule": "n_from_set", "n": 1, "courses": ["CSC-396", "CSC-399"]}
    r = run(prereqs, tree, done=["CSC-121"])
    assert [n.course_id for n in r.needs] == ["CSC-399"]


def test_a_requirement_nothing_in_the_catalog_meets_still_costs_a_course():
    r = run(CHAIN, {"rule": "n_from_set", "n": 1, "courses": [], "label": "One allied course"})
    assert [(n.course_id, n.kind, n.credits) for n in r.needs] == [(None, "unnamed", 1.0)]
    assert r.estimate == 1


def test_program_scoped_count_is_met_by_what_was_chosen():
    """'Two 300-level courses' over the program: the elective just chosen
    counts, so nothing extra is added."""
    prereqs = {"CSC-322": None, "CSC-340": None, "CSC-350": None}
    tree = all_of(
        course("CSC-322"),
        {"rule": "n_from_set", "n": 1, "courses": ["CSC-340", "CSC-350"]},
        {"rule": "credit_minimum", "credits": 2, "min_number": 300, "scope": "program"},
    )
    assert len(run(prereqs, tree).needs) == 2


# -- the demo student --------------------------------------------------------


@pytest.fixture(scope="module")
def demo():
    fx = check([DATA / f"{n}_2025_26.json" for n in ("csc_catalog", "math_catalog", "econ_catalog", "other_stubs")])
    catalog = {}
    for c in fx.entries:
        tags = set(c.get("attributes") or []) | ({c["distribution"]} if c.get("distribution") else set())
        catalog[c["id"]] = CourseInfo(c["subject"], c["number"], (1.0 if c.get("credits_max") is None else c["credits_max"]), frozenset(tags))
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
        p["id"]: to_rows(p["requirements"])
        for p in json.loads((DATA / "programs_2025_26.json").read_text())["programs"]
    }

    def go(ids, max_load=4.5):
        return estimate(
            engine,
            orderer,
            [engine.audit(i, programs[i]) for i in ids],
            current_term=current_term((e["term"], e["status"]) for e in student["enrollments"]),
            graduation=student["expected_graduation"],
            max_load=max_load,
        )

    return go


DECLARED = ["MAJOR-CSC", "MINOR-MATH", "DEGREE-BA"]


def test_demo_student_is_credit_bound_and_just_on_time(demo):
    r = demo(DECLARED)
    assert (r.current_term, r.terms_left) == ("2025FA", 3)
    # CSC 498 waits for senior standing: next term is the junior spring.
    assert r.chain_bound == 2 and r.chain[-1] == "CSC-498"
    # 31 - 17.5 done or in progress = 13.5 credits, 3 terms at 4.5.
    assert (r.remaining_credits, r.credit_bound) == (13.5, 3)
    assert (r.estimate, r.binding, r.feasible) == (3, "credits", True)


def test_demo_student_at_the_normal_load_runs_late(demo):
    r = demo(DECLARED, max_load=4.0)
    assert (r.credit_bound, r.feasible) == (4, False)


def test_adding_programs_eventually_outgrows_the_degree_minimum(demo):
    """The Math major alone fits in the 13.5 credits the degree needs anyway;
    with the Data Science minor too, the named courses pass it."""
    assert demo(DECLARED + ["MAJOR-MATH"]).estimate == 3
    r = demo(DECLARED + ["MAJOR-MATH", "MINOR-DATA"])
    assert (r.remaining_credits, r.estimate, r.feasible) == (16.5, 4, False)
    assert "still need" in r.credit_basis
