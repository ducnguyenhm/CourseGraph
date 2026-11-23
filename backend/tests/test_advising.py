"""Checkpoint 4 (written before the code): who may see and comment on a plan.

The contract for `app/services/advising.py`: the rules alone, with no
database or login, so the API layer only has to look up the account and
store what these return.

    Account(key, role)              role: "student" | "advisor"; a student's
                                    key is their student_key
    Policy(assignments)             advisor key -> the student keys they advise
    policy.advisees(account) -> sorted student keys (Forbidden for a student)
    policy.can_view(account, student_key) -> bool
    policy.comment(account, student_key, plan, body, course_id=None) -> Comment
        starts a conversation on the plan as a whole, or on one placement in
        it; the comment keeps the term the course was in when it was written.
        The student and their advisors may both start one.
    policy.reply(account, parent, body) -> Comment
        an answer in that conversation, by the student or their advisor
        (added 2026-11-18: students chat back instead of only reading)
    policy.resolve(account, comment) -> a resolved copy (the plan's student only)
    policy.thread(account, student_key, comments) -> that student's
        conversations, unresolved first, each group oldest first, each
        conversation followed by its replies, oldest first
    awaiting_advisor(comments) -> how many open conversations last heard
        from the student

    Comment(student_key, author, body, course_id, term, resolved, created, id, parent_id)

Advisors choose their advisees (added 2026-11-18), but seeing a record needs
the student's yes, so adding is a request:

    Policy(assignments, invites)    invites: advisor key -> student keys asked
    policy.invite(advisor, student_key, students)   students: keys with a
                                    student login; asks, grants nothing yet
    policy.cancel_invite(advisor, student_key)
    policy.invites(account) -> sorted keys: the students an advisor asked,
                                    or the advisors asking a student
    policy.answer_invite(student, advisor_key, accept) -> accept; a yes makes
                                    the student an advisee
    policy.release(advisor, student_key)   off the list, access gone
"""

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from app.services.advising import Account, Comment, Forbidden, Policy, awaiting_advisor
from app.services.planner import Placement

pytestmark = pytest.mark.cp4


@pytest.fixture
def world():
    policy = Policy({"adv-smith": {"demo", "s2"}, "adv-lee": {"s3"}}, {"adv-lee": {"s2"}})
    smith = Account("adv-smith", "advisor")
    lee = Account("adv-lee", "advisor")
    demo = Account("demo", "student")
    s2 = Account("s2", "student")
    plan = [Placement("CSC-322", "2026SP"), Placement("CSC-498", "2027SP")]
    return policy, smith, lee, demo, s2, plan


def test_advisor_lists_only_their_advisees(world):
    policy, smith, lee, demo, *_ = world
    assert policy.advisees(smith) == ["demo", "s2"]
    assert policy.advisees(lee) == ["s3"]
    with pytest.raises(Forbidden):
        policy.advisees(demo)


def test_who_can_view_a_plan(world):
    policy, smith, lee, demo, s2, _ = world
    assert policy.can_view(smith, "demo")
    assert not policy.can_view(lee, "demo")
    assert policy.can_view(demo, "demo")
    assert not policy.can_view(s2, "demo")


def test_advisor_comments_on_a_specific_placement(world):
    policy, smith, _, _, _, plan = world
    c = policy.comment(smith, "demo", plan, "Take this before the capstone", course_id="CSC-322")
    assert (c.student_key, c.author, c.course_id, c.term) == ("demo", "adv-smith", "CSC-322", "2026SP")
    assert not c.resolved


def test_advisor_comments_on_the_whole_plan(world):
    policy, smith, _, _, _, plan = world
    c = policy.comment(smith, "demo", plan, "Looks on track for 2027SP")
    assert c.course_id is None and c.term is None


def test_comment_on_a_course_not_in_the_plan_is_refused(world):
    policy, smith, _, _, _, plan = world
    with pytest.raises(ValueError):
        policy.comment(smith, "demo", plan, "?", course_id="CSC-440")


@pytest.mark.parametrize("body", ["", "  \n"])
def test_empty_comment_is_refused(world, body):
    policy, smith, _, _, _, plan = world
    with pytest.raises(ValueError):
        policy.comment(smith, "demo", plan, body)


def test_only_the_student_and_their_advisor_comment(world):
    policy, smith, lee, demo, s2, plan = world
    with pytest.raises(Forbidden):
        policy.comment(lee, "demo", plan, "Not my advisee")
    with pytest.raises(Forbidden):
        policy.comment(s2, "demo", plan, "Not my plan")
    # The student may start a conversation on their own plan, e.g. a question.
    c = policy.comment(demo, "demo", plan, "Can I take this a term early?", course_id="CSC-498")
    assert (c.author, c.course_id, c.term) == ("demo", "CSC-498", "2027SP")


def test_student_and_advisor_reply_in_the_conversation(world):
    policy, smith, lee, demo, s2, plan = world
    root = replace(policy.comment(smith, "demo", plan, "Move this later?", course_id="CSC-322"), id=1)
    answer = policy.reply(demo, root, "  I need it for CSC 498.  ")
    # A reply belongs to the conversation, and so to the same placement.
    assert (answer.parent_id, answer.author, answer.body) == (1, "demo", "I need it for CSC 498.")
    assert (answer.course_id, answer.term) == ("CSC-322", "2026SP")
    assert policy.reply(smith, root, "Fine, keep it.").author == "adv-smith"
    with pytest.raises(Forbidden):
        policy.reply(s2, root, "Not my plan")
    with pytest.raises(Forbidden):
        policy.reply(lee, root, "Not my advisee")
    with pytest.raises(ValueError):
        policy.reply(demo, root, "   ")
    # Answers go to the conversation, not to another answer.
    with pytest.raises(ValueError):
        policy.reply(smith, replace(answer, id=2), "nested")
    # Resolving is for the conversation as a whole.
    with pytest.raises(ValueError):
        policy.resolve(demo, replace(answer, id=2))


def test_thread_keeps_each_answer_under_its_conversation(world):
    policy, smith, _, demo, _, _ = world
    t0 = datetime(2026, 11, 18, 10, 0)
    a = Comment("demo", "adv-smith", "A", None, None, False, t0, id=1)
    b = Comment("demo", "adv-smith", "B", None, None, False, t0 + timedelta(hours=1), id=2)
    a1 = Comment("demo", "demo", "a1", None, None, False, t0 + timedelta(hours=2), id=3, parent_id=1)
    a2 = Comment("demo", "adv-smith", "a2", None, None, False, t0 + timedelta(hours=3), id=4, parent_id=1)
    assert [c.body for c in policy.thread(demo, "demo", [a2, b, a1, a])] == ["A", "a1", "a2", "B"]


def test_awaiting_advisor_counts_open_conversations_the_student_spoke_last_in():
    t0 = datetime(2026, 11, 18, 10, 0)
    asked = Comment("demo", "adv-smith", "Q", None, None, False, t0, id=1)
    answered = Comment("demo", "demo", "A", None, None, False, t0 + timedelta(hours=1), id=2, parent_id=1)
    question = Comment("demo", "demo", "Can I?", None, None, False, t0, id=3)
    replied = Comment("demo", "adv-smith", "Yes", None, None, False, t0 + timedelta(hours=1), id=4, parent_id=3)
    done = Comment("demo", "demo", "Thanks", None, None, True, t0, id=5)
    assert awaiting_advisor([asked, answered, question, replied, done]) == 1
    assert awaiting_advisor([asked]) == 0


def test_student_resolves_comments_on_their_own_plan(world):
    policy, smith, _, demo, s2, plan = world
    c = policy.comment(smith, "demo", plan, "Add a MATH elective", course_id="CSC-498")
    done = policy.resolve(demo, c)
    assert done.resolved and not c.resolved  # a copy; the original is unchanged
    with pytest.raises(Forbidden):
        policy.resolve(s2, c)
    with pytest.raises(Forbidden):
        policy.resolve(smith, c)


def test_student_sees_comments_received(world):
    """The presentation's last beat: the advisor comments, the student sees it."""
    policy, smith, lee, demo, s2, plan = world
    t0 = datetime(2026, 11, 18, 10, 0)
    old = Comment("demo", "adv-smith", "First", "CSC-322", "2026SP", False, t0)
    new = Comment("demo", "adv-smith", "Second", None, None, False, t0 + timedelta(hours=1))
    gone = Comment("demo", "adv-smith", "Resolved", None, None, True, t0 - timedelta(days=1))
    other = Comment("s2", "adv-smith", "Not yours", None, None, False, t0)
    everything = [new, gone, other, old]
    assert [c.body for c in policy.thread(demo, "demo", everything)] == ["First", "Second", "Resolved"]
    assert [c.body for c in policy.thread(smith, "demo", everything)] == ["First", "Second", "Resolved"]
    with pytest.raises(Forbidden):
        policy.thread(s2, "demo", everything)
    with pytest.raises(Forbidden):
        policy.thread(lee, "demo", everything)


STUDENTS = {"demo", "s2", "s3", "s4"}


def test_an_invite_grants_nothing_until_the_student_accepts(world):
    policy, smith, lee, demo, *_ = world
    policy.invite(lee, "demo", STUDENTS)
    assert policy.invites(lee) == ["demo", "s2"]
    assert policy.invites(demo) == ["adv-lee"]
    assert not policy.can_view(lee, "demo")
    assert policy.answer_invite(demo, "adv-lee", accept=True) is True
    assert policy.can_view(lee, "demo")
    assert policy.advisees(lee) == ["demo", "s3"]
    assert policy.invites(demo) == []


def test_a_declined_invite_leaves_the_record_private(world):
    policy, _, lee, _, s2, _ = world
    assert policy.invites(s2) == ["adv-lee"]
    assert policy.answer_invite(s2, "adv-lee", accept=False) is False
    assert not policy.can_view(lee, "s2")
    assert policy.invites(lee) == []
    with pytest.raises(ValueError, match="no request"):
        policy.answer_invite(s2, "adv-lee", accept=True)


def test_invite_refusals(world):
    policy, smith, lee, demo, s2, _ = world
    with pytest.raises(Forbidden):
        policy.invite(demo, "s2", STUDENTS)  # only advisors invite
    with pytest.raises(ValueError, match="no student login"):
        policy.invite(smith, "nobody", STUDENTS)
    with pytest.raises(ValueError, match="already your advisee"):
        policy.invite(smith, "demo", STUDENTS)
    with pytest.raises(ValueError, match="already asked"):
        policy.invite(lee, "s2", STUDENTS)
    with pytest.raises(Forbidden):
        policy.answer_invite(lee, "adv-lee", accept=True)  # only the student answers


def test_advisor_withdraws_an_invite(world):
    policy, _, lee, _, s2, _ = world
    policy.cancel_invite(lee, "s2")
    assert policy.invites(s2) == []
    with pytest.raises(ValueError, match="no request"):
        policy.cancel_invite(lee, "s2")


def test_advisor_removes_an_advisee(world):
    policy, smith, _, demo, *_ = world
    policy.release(smith, "s2")
    assert policy.advisees(smith) == ["demo"]
    assert not policy.can_view(smith, "s2")
    with pytest.raises(ValueError, match="not your advisee"):
        policy.release(smith, "s2")
    with pytest.raises(Forbidden):
        policy.release(demo, "demo")
    # Removed students can be asked again.
    policy.invite(smith, "s2", STUDENTS)
    assert policy.invites(smith) == ["s2"]
