"""How many more terms a student needs: the minimum-semester estimate.

Two lower bounds, and the estimate is the greater, because a plan has to
satisfy both:

- **Chain bound.** The longest prerequisite chain through what is left. A
  student with three courses to go still needs three terms if each requires
  the one before, however many credits they are willing to take.
- **Credit bound.** Remaining credits divided by the most a term can hold
  (4.5 at DePauw before overload fees). Remaining credits are the larger of
  the courses the programs still name and the degree's credit floor (31,
  less what is on the record), since the named courses count toward the 31.

"What is left" is read off the requirement audits: every slot no course on
the record fills, every slot filled only by a *planned* course, and every
prerequisite those courses need that the student has not done. Where a
requirement offers a choice ("three CSC courses at the 300 or 400 level"),
the estimate picks optimistically and says what it picked: first a course
already needed for another requirement (it counts twice), then one open
without permission, then the earliest it could be taken.

Like the program order, this assumes every course is offered every term.
"""

from __future__ import annotations

import math
from datetime import date
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.services.ordering import STANDING_ROUNDS, UNREACHABLE, Orderer
from app.services.requirements import (
    Audit,
    Engine,
    Entry,
    Outcome,
    _counts,
    allocates,
)

MAX_LOAD = 4.5  # catalog p. 606: "a maximum of 4.5 course credits per semester"
PRIMARY = ("SP", "FA")


@dataclass
class Need:
    """One course the estimate counts, or a slot no loaded course can fill."""

    course_id: str | None
    credits: float
    # planned | required | chosen | prerequisite | unnamed
    kind: str
    reasons: list[str] = field(default_factory=list)
    round: int = 1  # the earliest term it could be taken, 1 = next term


@dataclass
class Estimate:
    chain_bound: int
    # The courses along the longest chain, earliest first.
    chain: list[str]
    remaining_credits: float
    max_load: float
    credit_bound: int
    estimate: int
    binding: str  # chain | credits | both | none
    current_term: str | None
    terms_left: int
    feasible: bool
    needs: list[Need]
    assumed: list[str]
    # Where the credit total comes from, in words.
    credit_basis: str


# -- terms ----------------------------------------------------------------------


def next_primary(term: str) -> str:
    """The fall or spring term after `term` (Winter Term leads into spring,
    May Term and summer into fall)."""
    year, kind = int(term[:4]), term[4:]
    if kind == "FA":
        return f"{year + 1}SP"
    if kind in ("WI",):
        return f"{year}SP"
    return f"{year}FA"


def term_index(term: str) -> int:
    """Fall and spring terms numbered consecutively."""
    return int(term[:4]) * 2 + (1 if term[4:] == "FA" else 0)


# The planner's terms: Winter Term after each fall, May Term after each
# spring. Summer is on records but not planned.
PLAN_KINDS = ("WI", "SP", "MY", "FA")
# Winter and May Term are short: catalog p. 23 places Extended Studies courses
# there, and those carry at most half a credit ("May be offered for .5 course
# credits or as a co-curricular (0 credit)", CSC 184).
SHORT_KINDS = ("WI", "MY")
SHORT_MAX_LOAD = 0.5
_ORDER = {"WI": 0, "SP": 1, "MY": 2, "SU": 3, "FA": 4}


def term_order(term: str) -> int:
    """Every kind of term numbered in calendar order, so that a summer comes
    after its spring and a Winter Term after the fall before it.
    `term_index` counts semesters; this orders terms."""
    return int(term[:4]) * 5 + _ORDER.get(term[4:], 5)


def next_plan_term(term: str) -> str:
    """The planner's term after `term`: fall, Winter Term, spring, May Term."""
    year, kind = int(term[:4]), term[4:]
    if kind == "FA":
        return f"{year + 1}WI"
    if kind == "WI":
        return f"{year}SP"
    if kind == "SP":
        return f"{year}MY"
    return f"{year}FA"


def academic_year(term: str) -> int:
    """The year whose fall opens `term`'s academic year: 2026SP -> 2025."""
    return int(term[:4]) - (term[4:] != "FA")


def past_terms(start: str | None, current: str | None, taken: Iterable[str]) -> list[str]:
    """The terms a student has already been through, for the planner to show
    the whole degree: every planner term from the fall their first year began
    through `current`, plus any other term on the record (a summer). Without a
    start term the earliest course on the record stands in for it."""
    taken = list(taken)
    first = start or min(taken, key=term_order, default=None)
    if first is None or current is None:
        return []
    out, term = set(taken), f"{academic_year(first)}FA"
    while term_order(term) <= term_order(current):
        out.add(term)
        term = next_plan_term(term)
    return sorted((t for t in out if term_order(t) <= term_order(current)), key=term_order)


def semesters_between(start: str, end: str) -> int:
    """Fall and spring terms from `start` up to, not including, `end`: the
    semesters finished by the time `end` begins."""
    n, term = 0, start
    while term_order(term) < term_order(end):
        n += term[4:] in PRIMARY
        term = next_plan_term(term)
    return n


def terms_between(current: str | None, graduation: str) -> int:
    """Fall/spring terms after `current`, up to and including `graduation`."""
    if current is None:
        return 0
    first = next_primary(current)
    return max(0, term_index(graduation) - term_index(first) + 1)


# -- the estimate ------------------------------------------------------------


class Estimator:
    def __init__(self, engine: Engine, orderer: Orderer):
        self.engine = engine
        self.orderer = orderer
        self.needs: dict[str, Need] = {}
        self.unnamed: list[Need] = []

    def _credits(self, cid: str) -> float:
        info = self.engine.catalog.get(cid)
        return info.credits if info else 1.0

    # When one course is needed for several reasons, the strongest names it.
    KINDS = ("required", "planned", "chosen", "prerequisite")

    def _add(self, cid: str, kind: str, reason: str) -> None:
        n = self.needs.get(cid)
        if n is None:
            self.needs[cid] = Need(cid, self._credits(cid), kind, [reason])
        else:
            if reason not in n.reasons:
                n.reasons.append(reason)
            if self.KINDS.index(kind) < self.KINDS.index(n.kind):
                n.kind = kind
        if kind != "prerequisite":
            # Its prerequisites are needed from now on, so a later choice can
            # see them as already needed (ECON 385 brings ECON 350, which then
            # fills "MATH 141, PSY 214, ECON 350 or BIO 375" for free).
            label = cid.replace("-", " ")
            for pre in self.orderer.place(cid).needs - self.orderer.done:
                self._add(pre, "prerequisite", f"before {label}")

    def _rank(self, cid: str) -> tuple:
        """Already needed elsewhere, then open without permission, then
        earliest, then fewest extra courses to take first, then a curated
        course over a stub whose prerequisites are unknown, then the fewest
        credits (an Extended Studies project can carry none)."""
        p = self.orderer.place(cid)
        extra = len(p.needs - self.orderer.done - set(self.needs))
        info = self.engine.catalog.get(cid)
        return (
            cid not in self.needs, p.via_consent, p.round, extra,
            bool(info and info.stub), self._credits(cid), cid,
        )

    def _pick(self, options: Iterable[str], k: int, used: set[str], reason: str) -> int:
        """Pick up to k courses one at a time, re-ranking after each: a pick
        brings its prerequisites, which may make the next pick free."""
        options = [c for c in options if self.orderer.place(c).round < UNREACHABLE]
        picked = 0
        while picked < k:
            left = [c for c in options if c not in used]
            if not left:
                break
            c = min(left, key=self._rank)
            self._add(c, "chosen", reason)
            used.add(c)
            picked += 1
        return picked

    def collect(self, audits: list[Audit]) -> None:
        # Within a program a course counts once; across programs it may count
        # toward each.
        used = {a.program_id: set(a.applied) for a in audits}
        choices: list[tuple[int, int, Audit, Outcome, int]] = []
        later: list[tuple[Audit, Outcome]] = []
        for i, audit in enumerate(audits):
            for leaf in audit.leaves():
                reason = f"{audit.program_id}: {leaf.label}"
                if leaf.rule_type == "credit_minimum":
                    if leaf.spec.get("scope") == "program":
                        later.append((audit, leaf))  # once the program's choices are known
                    continue  # the record-wide floor goes into the credit bound
                if allocates(leaf.rule_type, leaf.spec):
                    for c in leaf.applied:
                        if self.engine.by_id[c].state == "planned":
                            self._add(c, "planned", reason)
                missing = math.ceil(leaf.remaining)
                if not missing:
                    continue
                if leaf.rule_type == "specific_course":
                    for c in leaf.options:
                        self._add(c, "required", reason)
                        used[audit.program_id].add(c)
                else:
                    choices.append((len(leaf.options), i, audit, leaf, missing))

        # Fewest options first, across every program: the Data Science minor's
        # "MATH 261, CSC 370 or CSC 380" picks before the CS major's "any
        # three 300-level CSC courses", which can then take the same course
        # and count it twice instead of adding another.
        for _, _, audit, leaf, missing in sorted(choices, key=lambda t: (t[0], t[1])):
            reason = f"{audit.program_id}: {leaf.label}"
            picked = self._pick(leaf.options, missing, used[audit.program_id], reason)
            self.unnamed += [Need(None, 1.0, "unnamed", [reason]) for _ in range(missing - picked)]

        for audit, leaf in later:
            # "Four 300/400-level courses, including CSC 498": count what the
            # program has now plus what was just chosen for it.
            mine = used[audit.program_id]
            counted = sum(
                self._credits(c)
                for c in mine - set(leaf.applied)
                if c in self.needs and _counts(leaf.spec, self._probe(c))
            )
            short = leaf.need - leaf.have - counted
            if short > 0:
                options = self.engine.options_for(leaf.rule_type, leaf.spec)
                self._pick(options, math.ceil(short), mine, f"{audit.program_id}: {leaf.label}")

        # Everything those courses need first, on the branches the order assumes.
        for cid in list(self.needs):
            for pre in self.orderer.place(cid).needs - self.orderer.done:
                self._add(pre, "prerequisite", f"before {cid.replace('-', ' ')}")
        for n in self.needs.values():
            n.round = self.orderer.place(n.course_id).round

    def _probe(self, cid: str) -> Entry:
        info = self.engine.catalog.get(cid)
        subject, number = cid.split("-")
        return Entry(
            cid, "planned", frozenset({cid}), subject, int(number),
            info.credits if info else 1.0, info.tags if info else frozenset(),
        )

    def chain(self) -> list[str]:
        """The longest chain, read back from the latest course through the
        prerequisite placed latest before it. Among courses tied for latest,
        the one with the most courses on its chain, then one a program names
        outright, so the chain shown is the most telling one."""
        if not self.needs:
            return []
        top = max(n.round for n in self.needs.values())
        kind_rank = {"required": 0, "planned": 1, "chosen": 2, "prerequisite": 3}
        return min(
            (self._chain_from(n.course_id) for n in self.needs.values() if n.round == top),
            key=lambda ch: (-len(ch), kind_rank[self.needs[ch[-1]].kind], ch[-1]),
        )

    def _chain_from(self, cid: str) -> list[str]:
        out = [cid]
        while True:
            before = [
                c for c in self.orderer.place(out[-1]).needs - self.orderer.done
                if self.orderer.place(c).round < self.orderer.place(out[-1]).round
            ]
            if not before:
                break
            out.append(max(before, key=lambda c: (self.orderer.place(c).round, c)))
        return out[::-1]


def estimate(
    engine: Engine,
    orderer: Orderer,
    audits: list[Audit],
    *,
    current_term: str | None,
    graduation: str,
    max_load: float = MAX_LOAD,
    removed: Iterable[str] = (),
) -> Estimate:
    """removed: terms the student took out of their plan; a fall or spring
    among them is a semester they will not be taking courses in."""
    est = Estimator(engine, orderer)
    est.collect(audits)
    needs = sorted(est.needs.values(), key=lambda n: (n.round, n.course_id)) + est.unnamed

    named = sum(n.credits for n in needs)
    done_credits = sum(
        e.credits for e in engine.record.entries if e.state in ("completed", "in_progress")
    )
    floor = 0.0
    for a in audits:
        for leaf in a.leaves():
            unfiltered = not any(k in leaf.spec for k in ("subject", "min_number", "attribute"))
            if leaf.rule_type == "credit_minimum" and leaf.spec.get("scope", "record") == "record" and unfiltered:
                floor = max(floor, leaf.need - done_credits)
    remaining = max(named, floor)
    basis = (
        f"{_fmt(floor)} credits to reach the degree minimum ({_fmt(done_credits)} done or in progress)"
        if floor >= named and floor > 0
        else f"{_fmt(named)} credits of courses the programs still need"
    )

    chain_bound = max((n.round for n in needs), default=0)
    credit_bound = math.ceil(remaining / max_load - 1e-9) if remaining > 0 else 0
    best = max(chain_bound, credit_bound)
    binding = (
        "none" if best == 0
        else "both" if chain_bound == credit_bound
        else "chain" if chain_bound > credit_bound
        else "credits"
    )
    left = terms_between(current_term, graduation)
    if current_term is not None:
        left -= sum(
            1
            for t in set(removed)
            if t[4:] in PRIMARY and term_order(current_term) < term_order(t) <= term_order(graduation)
        )
    assumed: list[str] = []
    for n in needs:
        if n.course_id:
            assumed += [a for a in orderer.place(n.course_id).assumed if a not in assumed]
    return Estimate(
        chain_bound=chain_bound,
        chain=est.chain(),
        remaining_credits=remaining,
        max_load=max_load,
        credit_bound=credit_bound,
        estimate=best,
        binding=binding,
        current_term=current_term,
        terms_left=left,
        feasible=best <= left,
        needs=needs,
        assumed=assumed,
        credit_basis=basis,
    )


def _fmt(x: float) -> str:
    return f"{x:g}"


def current_term(terms: Iterable[tuple[str, str]]) -> str | None:
    """The term in progress, else the latest on the record.
    terms: (term, status) for every enrollment."""
    terms = list(terms)
    doing = [t for t, s in terms if s == "in_progress"]
    pool = doing or [t for t, _ in terms]
    order = {"WI": 0, "SP": 1, "MY": 2, "SU": 3, "FA": 4}
    return max(pool, key=lambda t: (t[:4], order.get(t[4:], 5)), default=None)


def calendar_term(today: date) -> str:
    """The term a date falls in: spring January to May, summer June and July,
    fall August to December."""
    kind = "SP" if today.month <= 5 else "SU" if today.month <= 7 else "FA"
    return f"{today.year}{kind}"


def starting_term(start: str | None, today: date) -> str:
    """Where a record with no courses stands, so a new account can plan:
    today's term, or, for a student who has not started, the term just before
    their first, so that `next_primary` lands on the start term."""
    now = calendar_term(today)
    if start and _term_key(start) > _term_key(now):
        return f"{start[:4]}{'SU' if start[4:] == 'FA' else 'WI'}"
    return now


def _term_key(term: str) -> tuple[str, int]:
    return term[:4], {"WI": 0, "SP": 1, "MY": 2, "SU": 3, "FA": 4}.get(term[4:], 5)


def terms_elapsed(
    terms: Iterable[str], standing: str, start: str | None = None, current: str | None = None
) -> int:
    """Fall/spring terms finished or under way. With a start term, every
    fall and spring from it through the current term counts, taken or not;
    without one, at least what the student's standing implies (a transfer
    student's record starts late)."""
    primary = {t for t in terms if t[4:] in PRIMARY}
    if start and current:
        return max(len(primary), terms_from(start, current))
    return max(len(primary), STANDING_ROUNDS.get(standing, 0))


def terms_from(start: str, current: str) -> int:
    """Fall/spring terms from `start` through `current`, both included."""
    y, k = int(start[:4]), start[4:]
    first = y * 2 + (0 if k in ("WI", "SP") else 1)
    y, k = int(current[:4]), current[4:]
    last = y * 2 + {"WI": -1, "FA": 1}.get(k, 0)
    return max(0, last - first + 1)
