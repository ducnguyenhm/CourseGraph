"""Checkpoint 4 (written before the code): demonstration-mode sessions.

The contract for `app/services/demo.py`. A visitor without an account gets a
private copy of the demo student's plan; edits stay in that session and are
discarded when it ends or sits idle too long. Nothing reaches the seed.

    Sessions(seed, *, ttl=timedelta(hours=2), clock=datetime.now)
    sessions.start() -> token          unguessable, one per visitor
    sessions.plan(token) -> plan       KeyError when unknown, ended or expired
    sessions.save(token, plan)         KeyError likewise
    sessions.end(token)
    sessions.removed(token) -> terms   terms the visitor took out of the plan
    sessions.save_removed(token, terms)  (since 2026-11-18)
Reading or saving counts as activity and restarts the idle clock.
"""

from datetime import datetime, timedelta

import pytest

from app.services.demo import Sessions
from app.services.planner import Placement

pytestmark = pytest.mark.cp4


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 18, 9, 0)

    def __call__(self):
        return self.now


@pytest.fixture
def setup():
    seed = [Placement("CSC-322", "2026SP"), Placement("CSC-498", "2027SP")]
    clock = Clock()
    return Sessions(seed, ttl=timedelta(hours=2), clock=clock), seed, clock


def test_a_session_starts_from_the_seed(setup):
    sessions, seed, _ = setup
    assert sessions.plan(sessions.start()) == seed


def test_tokens_are_distinct_and_unguessable(setup):
    sessions, *_ = setup
    tokens = {sessions.start() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(t) >= 16 for t in tokens)


def test_removed_terms_stay_in_their_session(setup):
    sessions, _, _ = setup
    a, b = sessions.start(), sessions.start()
    assert sessions.removed(a) == []
    sessions.save_removed(a, ["2026MY"])
    assert sessions.removed(a) == ["2026MY"] and sessions.removed(b) == []
    sessions.end(a)
    with pytest.raises(KeyError):
        sessions.removed(a)


def test_edits_stay_in_their_session(setup):
    sessions, seed, _ = setup
    a, b = sessions.start(), sessions.start()
    sessions.save(a, seed + [Placement("CSC-440", "2026FA")])
    assert len(sessions.plan(a)) == 3
    assert sessions.plan(b) == seed
    assert sessions.plan(sessions.start()) == seed


def test_the_seed_is_never_modified(setup):
    sessions, seed, _ = setup
    before = list(seed)
    t = sessions.start()
    sessions.plan(t).append(Placement("CSC-440", "2026FA"))  # mutate what we were given
    sessions.save(t, [])
    assert seed == before
    assert sessions.plan(sessions.start()) == before


def test_ended_session_is_discarded(setup):
    sessions, *_ = setup
    t = sessions.start()
    sessions.end(t)
    with pytest.raises(KeyError):
        sessions.plan(t)
    with pytest.raises(KeyError):
        sessions.save(t, [])


def test_unknown_token_is_refused(setup):
    sessions, *_ = setup
    with pytest.raises(KeyError):
        sessions.plan("not-a-token")


def test_idle_session_expires_and_activity_keeps_it_alive(setup):
    sessions, seed, clock = setup
    idle, busy = sessions.start(), sessions.start()
    clock.now += timedelta(hours=1, minutes=30)
    sessions.plan(busy)
    clock.now += timedelta(hours=1)  # idle: 2h30 since start; busy: 1h since use
    with pytest.raises(KeyError):
        sessions.plan(idle)
    assert sessions.plan(busy) == seed
