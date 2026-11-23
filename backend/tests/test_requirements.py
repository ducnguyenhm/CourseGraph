"""The requirement engine: one test per rule type, the allocation cases that
make it a matching problem, alternative groups, and overlap between programs."""

import json
from pathlib import Path

import pytest

from app.services.programs import RequirementRow, to_rows
from app.services.requirements import CourseInfo, Engine, Record, overlaps

DATA = Path(__file__).resolve().parent.parent / "data"
EQ = [
    ("CSC-122", "CSC-235", "renumber"),
    ("CSC-232", "CSC-125", "renumber"),
    ("MATH-136", "MATH-151", "satisfies"),
]


def info(cid, credits=1.0, tags=()):
    subject, number = cid.split("-")
    return CourseInfo(subject, int(number), credits, frozenset(tags))


CATALOG = {
    c: info(c)
    for c in [
        "CSC-121", "CSC-125", "CSC-231", "CSC-235", "CSC-236", "CSC-322", "CSC-340",
        "CSC-380", "CSC-398", "CSC-498", "MATH-123", "MATH-151", "MATH-223", "MATH-251",
        "MATH-341", "ECON-100", "ECON-350",
    ]
}
CATALOG["ECON-100"] = info("ECON-100", tags={"SS"})
CATALOG["MATH-151"] = info("MATH-151", tags={"SM"})
CATALOG["CSC-121"] = info("CSC-121", tags={"SM"})
CATALOG["CSC-184"] = info("CSC-184", credits=0.5, tags={"ES"})
CATALOG["ECON-184"] = info("ECON-184", credits=0.5, tags={"ES"})


def rows(node: dict) -> RequirementRow:
    return to_rows(node)


def course(cid, **kw):
    return {"rule": "specific_course", "course_id": cid, **kw}


def all_of(*children, label=""):
    return {"rule": "all_of", "label": label, "children": list(children)}


def any_of(*children, label=""):
    return {"rule": "any_of", "label": label, "children": list(children)}


def audit(tree, completed=(), in_progress=(), planned=(), competence=None, program="P", pinned=None):
    competence, pinned = competence or {}, pinned or {}
    taken = (
        [(c, "completed", competence.get(c), pinned.get(c)) for c in completed]
        + [(c, "in_progress", competence.get(c)) for c in in_progress]
        + [(c, "planned", None) for c in planned]
    )
    engine = Engine(Record.build(taken, CATALOG, EQ), CATALOG)
    return engine.audit(program, rows(tree))


# -- specific_course ---------------------------------------------------------


def test_specific_course_met_and_unmet():
    a = audit(all_of(course("CSC-121"), course("CSC-125")), completed=["CSC-121"])
    met, unmet = a.root.children
    assert (met.state, met.applied) == ("complete", ["CSC-121"])
    assert (unmet.state, unmet.options) == ("outstanding", ["CSC-125"])
    assert a.root.state == "outstanding"
    assert (a.root.have, a.root.need) == (1, 2)


def test_course_under_a_retired_number_meets_the_requirement():
    """CSC 122 taken before the renumbering is CSC 235 now."""
    a = audit(course("CSC-235"), completed=["CSC-122"])
    assert (a.root.state, a.root.applied) == ("complete", ["CSC-235"])


def test_satisfies_equivalence_meets_the_requirement():
    a = audit(course("MATH-151"), completed=["MATH-136"])
    assert a.root.state == "complete"


def test_in_progress_and_planned_states():
    tree = all_of(course("CSC-121"), course("CSC-125"), course("CSC-231"))
    a = audit(tree, completed=["CSC-121"], in_progress=["CSC-125"], planned=["CSC-231"])
    assert [c.state for c in a.root.children] == ["complete", "in_progress", "planned"]
    # A group is only as far along as its least-finished part.
    assert a.root.state == "planned"


# -- n_from_set --------------------------------------------------------------


def test_n_from_enumerated_set():
    tree = {"rule": "n_from_set", "n": 2, "courses": ["CSC-231", "CSC-235", "CSC-236"]}
    a = audit(tree, completed=["CSC-231"])
    assert (a.root.state, a.root.have, a.root.need) == ("outstanding", 1, 2)
    assert a.root.options == ["CSC-235", "CSC-236"]
    assert audit(tree, completed=["CSC-231", "CSC-236"]).root.state == "complete"


def test_n_from_subject_filter_honours_exclude():
    tree = {
        "rule": "n_from_set", "n": 2, "subject": "CSC", "min_number": 300,
        "exclude": ["CSC-398", "CSC-498"],
    }
    a = audit(tree, completed=["CSC-322", "CSC-498"])
    assert (a.root.applied, a.root.have) == (["CSC-322"], 1)
    assert "CSC-498" not in a.root.options and "CSC-398" not in a.root.options


def test_a_course_fills_one_requirement_per_program():
    """CSC 498 is core; it cannot also be a 300-level elective, even when the
    elective set does not exclude it."""
    tree = all_of(
        course("CSC-498"),
        {"rule": "n_from_set", "n": 1, "subject": "CSC", "min_number": 300},
    )
    a = audit(tree, completed=["CSC-498"])
    core, elective = a.root.children
    assert core.state == "complete"
    assert elective.state == "outstanding"


def test_allocation_is_a_matching_not_greedy():
    """Greedy would give MATH 223 to "123 or 223" (listed first) and leave
    "one of 223, 251" empty. A matching puts 123 there and 223 here."""
    tree = all_of(
        {"rule": "n_from_set", "n": 1, "courses": ["MATH-223", "MATH-123"], "label": "123 or 223"},
        {"rule": "n_from_set", "n": 1, "courses": ["MATH-223", "MATH-251"], "label": "223 or 251"},
    )
    a = audit(tree, completed=["MATH-223", "MATH-123"])
    assert a.root.state == "complete"
    assert [c.applied for c in a.root.children] == [["MATH-123"], ["MATH-223"]]


def test_completed_course_preferred_over_in_progress():
    tree = {"rule": "n_from_set", "n": 1, "courses": ["CSC-322", "CSC-340"]}
    a = audit(tree, completed=["CSC-340"], in_progress=["CSC-322"])
    assert (a.root.state, a.root.applied) == ("complete", ["CSC-340"])


# -- credit_minimum ----------------------------------------------------------


def test_credit_minimum_over_the_whole_record():
    tree = {"rule": "credit_minimum", "credits": 3}
    a = audit(tree, completed=["CSC-121", "CSC-184"], in_progress=["ECON-100"])
    assert (a.root.have, a.root.remaining, a.root.state) == (2.5, 0.5, "outstanding")
    a = audit(tree, completed=["CSC-121", "CSC-184", "ECON-184", "MATH-151"], in_progress=["ECON-100"])
    # Three credits are already complete; the in-progress course is extra.
    assert (a.root.have, a.root.state) == (4.0, "complete")


def test_credit_minimum_scoped_to_the_program_counts_what_it_placed():
    """'Number 300 & 400 level courses: four including CSC 498' — counts
    courses the other rules placed, without taking them from those rules.
    CSC 380 is on the record but not applied to this program."""
    tree = all_of(
        course("CSC-498"),
        {"rule": "n_from_set", "n": 2, "courses": ["CSC-322", "CSC-340"]},
        {"rule": "credit_minimum", "credits": 4, "min_number": 300, "scope": "program"},
    )
    a = audit(tree, completed=["CSC-498", "CSC-322", "CSC-340", "CSC-380"])
    core, electives, level = a.root.children
    assert core.state == electives.state == "complete"
    assert (level.have, level.state) == (3, "outstanding")
    assert sorted(level.applied) == ["CSC-322", "CSC-340", "CSC-498"]
    # Counting rules stay out of the group's course totals.
    assert (a.root.have, a.root.need) == (3, 3)


# -- attribute_count ---------------------------------------------------------


def test_attribute_from_the_catalog():
    """Extended Studies: two experiences, from course attributes."""
    tree = {"rule": "attribute_count", "n": 2, "attribute": "ES"}
    a = audit(tree, completed=["CSC-184"])
    assert (a.root.have, a.root.state) == (1, "outstanding")
    assert a.root.options == ["ECON-184"]


def test_competence_comes_from_the_section_not_the_course():
    """Q is earned per section: MATH 151 counts only where the transcript
    records it."""
    tree = {"rule": "attribute_count", "n": 1, "attribute": "Q"}
    assert audit(tree, completed=["MATH-151"]).root.state == "outstanding"
    assert audit(tree, completed=["MATH-151"], competence={"MATH-151": "Q"}).root.state == "complete"


def test_distinct_subjects():
    """Exploratory Foundations: two SM credits must be different subjects."""
    tree = {"rule": "attribute_count", "n": 2, "attribute": "SM", "distinct_subjects": True}
    assert audit(tree, completed=["CSC-121", "MATH-151"]).root.state == "complete"
    CATALOG["CSC-125"] = info("CSC-125", tags={"SM"})
    try:
        assert audit(tree, completed=["CSC-121", "CSC-125"]).root.have == 1
    finally:
        CATALOG["CSC-125"] = info("CSC-125")


# -- any_of: alternative groups ----------------------------------------------


DATA_SCIENCE_LIKE = all_of(
    any_of(
        course("MATH-123"),
        course("MATH-223", notes="with advisor approval"),
        label="MATH 123 (or 223)",
    ),
    any_of(
        all_of(course("CSC-231"), course("CSC-235")),
        course("CSC-340"),
        label="231 and 235, or 340",
    ),
)


def test_any_of_takes_the_branch_that_is_met():
    a = audit(DATA_SCIENCE_LIKE, completed=["MATH-223", "CSC-340"])
    math, cs = a.root.children
    assert math.state == "complete" and math.applied == ["MATH-223"]
    assert [b.chosen for b in math.children] == [False, True]
    assert cs.applied == ["CSC-340"]
    assert a.root.state == "complete"


def test_any_of_prefers_the_branch_leaving_least_work():
    """With CSC 231 done, both branches are one course short; the tie goes to
    the branch that uses the completed course. With nothing done, the
    one-course branch beats the two-course one."""
    _, cs = audit(DATA_SCIENCE_LIKE, completed=["CSC-231"]).root.children
    assert [b.chosen for b in cs.children] == [True, False]
    assert cs.remaining == 1
    _, cs = audit(DATA_SCIENCE_LIKE).root.children
    assert [b.chosen for b in cs.children] == [False, True]
    assert (cs.have, cs.need) == (0, 1)


def test_unchosen_branch_courses_are_free_for_other_requirements():
    """MATH 223 can't serve both the any_of and the set below; the engine
    takes 123 for the any_of so 223 stays free."""
    tree = all_of(
        any_of(course("MATH-123"), course("MATH-223")),
        {"rule": "n_from_set", "n": 1, "courses": ["MATH-223"]},
    )
    a = audit(tree, completed=["MATH-123", "MATH-223"])
    assert a.root.state == "complete"


# -- exclusive attribute rules (Exploratory Foundations) ------------------------


def area(attr, n=1, **kw):
    return {"rule": "attribute_count", "n": n, "attribute": attr, "exclusive": True, **kw}


def with_courses(extra: dict):
    """Run with extra made-up courses in the catalog, then put it back."""
    class Ctx:
        def __enter__(self):
            CATALOG.update(extra)

        def __exit__(self, *exc):
            for k in extra:
                CATALOG.pop(k, None)

    return Ctx()


def test_an_either_or_course_fills_one_area_not_both():
    """REL 130 is 'Arts and Humanities-or-Global Learning'. Counted, it would
    meet both; exclusive, it meets one and the other stays outstanding."""
    with with_courses({"REL-130": info("REL-130", tags={"AH", "GL"})}):
        counted = audit(
            all_of({"rule": "attribute_count", "n": 1, "attribute": "AH"},
                   {"rule": "attribute_count", "n": 1, "attribute": "GL"}),
            completed=["REL-130"],
        )
        assert counted.root.state == "complete"
        a = audit(all_of(area("AH"), area("GL")), completed=["REL-130"])
        assert sorted(c.state for c in a.root.children) == ["complete", "outstanding"]
        assert a.root.have == 1 and a.root.need == 2


def test_the_engine_chooses_the_area_that_leaves_least_outstanding():
    """REL 130 (AH or GL) and ARTH 132 (AH only): REL 130 must go to GL."""
    with with_courses({
        "REL-130": info("REL-130", tags={"AH", "GL"}),
        "ARTH-132": info("ARTH-132", tags={"AH"}),
    }):
        a = audit(all_of(area("AH"), area("GL")), completed=["REL-130", "ARTH-132"])
        ah, gl = a.root.children
        assert (ah.applied, gl.applied) == (["ARTH-132"], ["REL-130"])
        assert a.root.state == "complete"


def test_student_can_pin_an_either_or_course_to_one_area():
    """Left alone, REL 130 goes to AH (it is listed first and the tie is
    even); pinned to GL, it fills GL and AH is the one left open."""
    tree = all_of(area("AH", label="AH"), area("GL", label="GL"))
    with with_courses({"REL-130": info("REL-130", tags={"AH", "GL"})}):
        auto = audit(tree, completed=["REL-130"])
        assert [c.applied for c in auto.root.children] == [["REL-130"], []]
        pinned = audit(tree, completed=["REL-130"], pinned={"REL-130": "GL"})
        assert [c.applied for c in pinned.root.children] == [[], ["REL-130"]]
        assert auto.root.children[0].options == []


def test_pinning_leaves_other_tags_alone():
    """Pinning picks among Foundations areas only; ES and competence still count."""
    tree = all_of(area("GL"), {"rule": "attribute_count", "n": 1, "attribute": "ES"})
    with with_courses({"REL-185": info("REL-185", tags={"AH", "GL", "ES"})}):
        a = audit(tree, completed=["REL-185"], pinned={"REL-185": "GL"})
        assert a.root.state == "complete"


def test_distinct_group_spans_rules():
    """'Each of the six AH/SM/SS credits from a different subject': two PHIL
    courses can't cover AH and SS between them; SOC 100 must take SS."""
    tree = all_of(
        area("AH", distinct_group="foundations"),
        area("SS", distinct_group="foundations"),
    )
    extra = {
        "PHIL-101": info("PHIL-101", tags={"AH"}),
        "PHIL-102": info("PHIL-102", tags={"SS"}),
        "SOC-100": info("SOC-100", tags={"SS"}),
    }
    with with_courses(extra):
        a = audit(tree, completed=["PHIL-101", "PHIL-102", "SOC-100"])
        assert [c.applied for c in a.root.children] == [["PHIL-101"], ["SOC-100"]]
        a = audit(tree, completed=["PHIL-101", "PHIL-102"])
        assert [c.have for c in a.root.children] == [1, 0]


def test_distinct_group_and_other_rules_share_the_record():
    """A course taken by a distinct-group area is not also free for another
    exclusive rule, and the search still fills the most slots overall."""
    tree = all_of(
        area("SS", 2, distinct_group="foundations"),
        area("PPD"),
    )
    extra = {
        "SOC-237": info("SOC-237", tags={"SS", "PPD"}),
        "POLS-110": info("POLS-110", tags={"SS"}),
    }
    with with_courses(extra):
        a = audit(tree, completed=["SOC-237", "POLS-110", "ECON-100"])
        ss, ppd = a.root.children
        # ECON 100 + POLS 110 cover SS, so SOC 237 is free for PPD.
        assert sorted(ss.applied) == ["ECON-100", "POLS-110"]
        assert ppd.applied == ["SOC-237"]


def test_group_of_counts_reports_no_course_totals():
    tree = all_of(
        course("CSC-121"),
        all_of({"rule": "attribute_count", "n": 1, "attribute": "Q"}, label="Competencies"),
    )
    a = audit(tree, completed=["CSC-121", "MATH-151"], competence={"MATH-151": "Q"})
    comp = a.root.children[1]
    assert comp.state == "complete" and not comp.in_courses
    assert (a.root.have, a.root.need) == (1, 1)


@pytest.mark.parametrize(
    "node, message",
    [
        ({"rule": "specific_course"}, "needs course_id"),
        ({"rule": "n_from_set", "n": 2}, "'courses' or 'subject'"),
        ({"rule": "credit_minimum"}, "needs credits"),
        ({"rule": "attribute_count", "n": 1}, "needs attribute"),
        ({"rule": "attribute_count", "n": 1, "attribute": "AH", "distinct_group": "g"}, "exclusive"),
        ({"rule": "credit_minimum", "credits": 3, "scope": "major"}, "unknown scope"),
        ({"rule": "all_of", "children": []}, "no children"),
    ],
)
def test_malformed_requirements_are_rejected(node, message):
    with pytest.raises(ValueError, match=message):
        to_rows(node)


# -- more than one program ---------------------------------------------------


def test_course_counts_toward_two_programs():
    major = all_of(course("CSC-121"), course("CSC-125"), course("MATH-123"))
    minor = all_of(
        course("CSC-121"),
        {"rule": "n_from_set", "n": 1, "courses": ["MATH-123", "MATH-151"]},
    )
    done = ["CSC-121", "CSC-125", "MATH-123", "MATH-151"]
    a, b = audit(major, done, program="MAJOR"), audit(minor, done, program="MINOR")
    assert a.root.state == b.root.state == "complete"
    # The minor's set could use 151 instead; evaluated on its own it takes
    # whichever it finds, and MATH 123 is reported if it lands in both.
    shared = overlaps([a, b])
    assert shared["CSC-121"] == ["MAJOR", "MINOR"]
    assert set(shared) <= {"CSC-121", "MATH-123"}


# -- the real fixtures -------------------------------------------------------


FIXTURES = ["csc_catalog", "math_catalog", "econ_catalog", "other_stubs"]


@pytest.fixture(scope="module")
def real():
    catalog = {}
    for name in FIXTURES:
        doc = json.loads((DATA / f"{name}_2025_26.json").read_text())
        for c in doc["courses"] + doc.get("stub_courses", []):
            tags = set(c.get("attributes") or [])
            if c.get("distribution"):
                tags.add(c["distribution"])
            catalog[c["id"]] = CourseInfo(c["subject"], c["number"], (1.0 if c.get("credits_max") is None else c["credits_max"]), frozenset(tags))
    programs = {
        p["id"]: to_rows(p["requirements"])
        for p in json.loads((DATA / "programs_2025_26.json").read_text())["programs"]
    }
    student = json.loads((DATA / "demo_student.json").read_text())["students"][0]
    taken = [(e["course_id"], e["status"], e.get("competence")) for e in student["enrollments"]]
    taken += [(p["course_id"], "planned", None) for p in student["plan"]]
    eq = [("CSC-122", "CSC-235", "renumber"), ("CSC-232", "CSC-125", "renumber"),
          ("CSC-233", "CSC-236", "renumber")]
    return Engine(Record.build(taken, catalog, eq), catalog), programs


def test_demo_student_against_the_cs_major(real):
    engine, programs = real
    a = engine.audit("MAJOR-CSC", programs["MAJOR-CSC"])
    core, electives, level, math, allied = a.root.children
    by_label = {c.label: c.state for c in core.children}
    assert by_label["CSC 121"] == by_label["CSC 125"] == by_label["CSC 235"] == "complete"
    assert by_label["CSC 236"] == "in_progress"
    assert by_label["CSC 498"] == "planned"
    assert sorted(electives.applied) == ["CSC-322", "CSC-340"]
    assert electives.remaining == 1
    # "Four 300/400-level including CSC 498": 322, 340, 498 so far.
    assert (level.have, level.need, level.state) == (3, 4, "outstanding")
    assert math.state == "complete"
    # The allied list is not printed in the catalog, so nothing can meet it.
    assert (allied.state, allied.options) == ("outstanding", [])


def test_demo_student_major_and_minor_share_nothing(real):
    engine, programs = real
    a = engine.audit("MAJOR-CSC", programs["MAJOR-CSC"])
    b = engine.audit("MINOR-MATH", programs["MINOR-MATH"])
    assert overlaps([a, b]) == {}
    assert {c.label: c.state for c in b.root.children[0].children} == {
        "MATH 151": "complete", "MATH 152": "complete",
        "MATH 223": "complete", "MATH 270": "in_progress",
    }


def test_demo_student_against_the_degree(real):
    engine, programs = real
    a = engine.audit("DEGREE-BA", programs["DEGREE-BA"])
    credits, fys, foundations, competencies, es = a.root.children
    assert credits.state == "outstanding" and credits.need == 31
    assert fys.applied == ["ARTH-197"]
    states = {c.label: c.state for c in foundations.children}
    assert states["Arts and Humanities"] == "complete"
    assert states["Intercultural Engagement Through Language"] == "complete"
    # SOC 237 (SS or PPD) and REL 130 (AH or GL) each fill one area: with
    # ECON 100 the only other SS course, SOC 237 is needed for SS.
    assert states["Social Science"] == "complete"
    assert states["Power, Privilege and Diversity"] == "outstanding"
    assert states["Global Learning"] == "outstanding"
    # Six different subjects across AH/SM/SS.
    six = [c for c in foundations.children[:3] for c in c.applied]
    assert len({c.split("-")[0] for c in six}) == 6
    assert {c.label: c.state for c in competencies.children} == {
        "Expository writing (W)": "in_progress",
        "Quantitative reasoning (Q)": "complete",
        "Oral communication (S)": "planned",
    }
    assert (es.have, es.need) == (1, 2)


def test_cs_major_and_degree_cover_every_rule_type(real):
    """Checkpoint 3: 'at least one requirement of each implemented rule type'."""
    _, programs = real
    from app.services.programs import RULE_TYPES, walk

    used = {r.rule_type for p in ("MAJOR-CSC", "DEGREE-BA") for r in walk(programs[p])}
    assert used == RULE_TYPES - {"any_of"}
    assert {"specific_course", "n_from_set", "credit_minimum"} <= {
        r.rule_type for r in walk(programs["MAJOR-CSC"])
    }
