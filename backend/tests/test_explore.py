"""The explorer on the demo student (CS major + Math minor, junior, graduating
Spring 2027): what adding a program would cost."""

import pytest

from app.services.explore import explore


def run(demo, *added, max_load=4.5):
    spec = lambda pid: (pid, *demo.programs[pid])  # noqa: E731
    return explore(
        demo.engine,
        demo.orderer,
        [spec(p) for p in demo.declared],
        [spec(p) for p in added],
        current_term=demo.current_term,
        graduation=demo.graduation,
        max_load=max_load,
    )


def test_data_science_minor_fits_without_another_term(demo_student):
    x = run(demo_student, "MINOR-DATA")
    (data,) = x.impacts
    # CSC 121 and 125 are done and already count toward the CS major.
    assert [o.label for o in data.satisfied] == ["CSC 121", "CSC 125"]
    assert data.shared_done == {"CSC-121": ["MAJOR-CSC"], "CSC-125": ["MAJOR-CSC"]}
    assert len(data.outstanding) == 3
    # Three new courses: ECON 350 fills Statistics and is the prerequisite
    # for ECON 385, so one course does both jobs.
    assert sorted(n.course_id for n in data.new_courses) == ["CSC-370", "ECON-350", "ECON-385"]
    assert data.new_credits == 3
    # The degree's 31 credits already leave room for them.
    assert x.extra_credits_to_graduate == 0
    assert (x.baseline.estimate, x.combined.estimate, x.additional_terms) == (3, 3, 0)
    assert x.combined.feasible
    assert data.warnings == []


def test_math_major_fits_in_the_electives_the_degree_requires(demo_student):
    """Five more MATH courses, but the student needs 13.5 credits for the
    degree anyway, and they fit inside it."""
    x = run(demo_student, "MAJOR-MATH")
    (math,) = x.impacts
    assert {"MATH-151", "MATH-152", "MATH-223"} <= set(math.shared_done)
    # The minor's 300-level course is picked so it counts for the major too.
    assert math.shared_needed == {"MATH-332": ["MINOR-MATH"]}
    assert {"MATH-251", "MATH-495"} <= {n.course_id for n in math.new_courses}
    assert x.extra_credits_to_graduate == 0
    assert (x.additional_terms, x.combined.feasible) == (0, True)


def test_math_major_and_data_science_minor_together_run_late(demo_student):
    """Either fits on its own; both need 16.5 credits, which is 4 terms."""
    x = run(demo_student, "MAJOR-MATH", "MINOR-DATA")
    assert x.combined.remaining_credits == 16.5 and x.extra_credits_to_graduate == 3
    assert (x.additional_terms, x.combined.feasible) == (1, False)


def test_minor_inside_the_major_is_flagged(demo_student):
    """The CS minor is entirely CS major courses: the catalog requires three
    minor courses outside the major."""
    (csc,) = run(demo_student, "MINOR-CSC").impacts
    assert any("at least three" in w for w in csc.warnings)
    assert csc.new_courses == []


def test_double_minor_overlap_is_flagged(demo_student):
    x = run(demo_student, "MINOR-DATA", "MINOR-CSC")
    by = {i.program_id: i for i in x.impacts}
    assert any("double minors" in w for w in by["MINOR-DATA"].warnings)


def test_several_programs_at_once(demo_student):
    """Comparing 'a second major' with 'two minors' is two calls; one call
    can also carry both programs together."""
    both = run(demo_student, "MAJOR-MATH", "MINOR-DATA")
    assert [i.program_id for i in both.impacts] == ["MAJOR-MATH", "MINOR-DATA"]
    assert both.new_credits >= run(demo_student, "MAJOR-MATH").new_credits


def test_normal_load_changes_the_answer(demo_student):
    x = run(demo_student, "MINOR-DATA", max_load=4.0)
    assert x.baseline.estimate == 4 and not x.combined.feasible


@pytest.mark.parametrize("pid", ["MINOR-DATA", "MAJOR-MATH", "MINOR-CSC"])
def test_new_courses_are_new(demo_student, pid):
    x = run(demo_student, pid)
    had = {n.course_id for n in x.baseline.needs}
    assert not {n.course_id for n in x.new_courses if n.course_id} & had
