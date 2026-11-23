"""Demonstration-mode sessions: a visitor's private copy of the demo plan.

No account and nothing written to the database. Each visitor gets a token;
their plan edits live under it in memory and are discarded when the session
ends or sits idle past `ttl`. The seed is copied in and out, never shared,
so no visitor can change what the next one starts from.

In memory means one API process, which is how the app runs under Docker
Compose; a restart ends every demo session, which is fine for a demo.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import datetime, timedelta
from threading import Lock

from app.services.planner import Placement


class Sessions:
    def __init__(
        self,
        seed: list[Placement],
        *,
        ttl: timedelta = timedelta(hours=2),
        clock: Callable[[], datetime] = datetime.now,
    ):
        self.seed = list(seed)
        self.ttl = ttl
        self.clock = clock
        self._sessions: dict[str, tuple[list[Placement], datetime]] = {}
        # Terms each visitor took out of the plan; gone with the session.
        self._removed: dict[str, list[str]] = {}
        self._lock = Lock()

    def start(self, seed: list[Placement] | None = None) -> str:
        """A new session from the seed (or from `seed`, the demo student's
        plan as it stands in the database now)."""
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._sweep()
            self._sessions[token] = (list(self.seed if seed is None else seed), self.clock())
        return token

    def _live(self, token: str) -> list[Placement]:
        plan, last = self._sessions[token]
        if self.clock() - last > self.ttl:
            del self._sessions[token]
            self._removed.pop(token, None)
            raise KeyError(token)
        return plan

    def plan(self, token: str) -> list[Placement]:
        with self._lock:
            plan = self._live(token)
            self._sessions[token] = (plan, self.clock())
            return list(plan)

    def save(self, token: str, plan: list[Placement]) -> None:
        with self._lock:
            self._live(token)
            self._sessions[token] = (list(plan), self.clock())

    def removed(self, token: str) -> list[str]:
        with self._lock:
            plan = self._live(token)
            self._sessions[token] = (plan, self.clock())
            return list(self._removed.get(token, []))

    def save_removed(self, token: str, terms: list[str]) -> None:
        with self._lock:
            plan = self._live(token)
            self._sessions[token] = (plan, self.clock())
            self._removed[token] = list(terms)

    def end(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(token, None)
            self._removed.pop(token, None)

    def _sweep(self) -> None:
        """Drop expired sessions, so abandoned tabs do not pile up."""
        now = self.clock()
        for token in [t for t, (_, last) in self._sessions.items() if now - last > self.ttl]:
            del self._sessions[token]
            self._removed.pop(token, None)
