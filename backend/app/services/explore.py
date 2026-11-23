"""The major and minor explorer: what adding a program would cost.

Everything is a difference between two estimates over the same record:
the student's declared programs plus the degree (the baseline), and the same
with the added programs. The added programs are audited like declared ones,
so the explorer reports which of their requirements the record already
meets, which courses would count twice, the courses it adds, and the terms.

Two numbers answer "how much more work", and they differ on purpose:

- **new courses**: courses the added programs would put on the plan that
  the baseline does not have;
- **extra credits to graduate**: how much the total left grows. Usually
  less, because the degree's 31 credits already leave room for electives,
  and a minor's courses can fill that room instead of adding to it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.services.ordering import Orderer
from app.services.requirements import Audit, Engine, Outcome
from app.services.semesters import Estimate, Need, estimate


@dataclass
class Impact:
    """One added program."""

    program_id: str
    kind: str
    audit: Audit
    satisfied: list[Outcome]  # met by completed courses
    underway: list[Outcome]  # met only with in-progress or planned courses
    outstanding: list[Outcome]
    # Course on the record (taken, in progress or planned) -> declared
    # programs it already counts toward.
    shared_done: dict[str, list[str]]
    # Course still to take -> declared programs it would also count toward.
    shared_needed: dict[str, list[str]]
    new_courses: list[Need]
    warnings: list[str] = field(default_factory=list)

    @property
    def new_credits(self) -> float:
        return sum(n.credits for n in self.new_courses)


@dataclass
class Exploration:
    baseline: Estimate
    combined: Estimate
    impacts: list[Impact]
    new_courses: list[Need]

    @property
    def new_credits(self) -> float:
        return sum(n.credits for n in self.new_courses)

    @property
    def extra_credits_to_graduate(self) -> float:
        return self.combined.remaining_credits - self.baseline.remaining_credits

    @property
    def additional_terms(self) -> int:
        return self.combined.estimate - self.baseline.estimate


def _programs_of(n: Need) -> set[str]:
    return {r.split(":", 1)[0] for r in n.reasons if ":" in r}


def explore(
    engine: Engine,
    orderer: Orderer,
    declared: list[tuple[str, str, object]],
    added: list[tuple[str, str, object]],
    *,
    current_term: str | None,
    graduation: str,
    max_load: float,
    removed: Iterable[str] = (),
) -> Exploration:
    """declared / added: (program_id, kind, requirement tree). Declared
    includes the degree; it is not something the student adds."""
    base_audits = [engine.audit(pid, tree) for pid, _, tree in declared]
    add_audits = [engine.audit(pid, tree) for pid, _, tree in added]
    kinds = {pid: kind for pid, kind, _ in declared + added}
    kw = dict(current_term=current_term, graduation=graduation, max_load=max_load, removed=removed)
    baseline = estimate(engine, orderer, base_audits, **kw)
    combined = estimate(engine, orderer, base_audits + add_audits, **kw)

    # New: named courses the baseline lacks, and slots nothing can fill that
    # belong to an added program.
    had = {n.course_id for n in baseline.needs if n.course_id}
    added_ids = {pid for pid, _, _ in added}
    new = [
        n for n in combined.needs
        if (n.course_id and n.course_id not in had)
        or (n.course_id is None and _programs_of(n) & added_ids)
    ]

    programs = {pid for pid, kind, _ in declared if kind != "degree"}
    counted_for = {a.program_id: a.applied for a in base_audits if a.program_id in programs}

    impacts = []
    for a in add_audits:
        pid = a.program_id
        leaves = [o for o in a.leaves() if o.rule_type != "credit_minimum" or o.spec.get("scope") == "program"]
        satisfied, underway, outstanding = [], [], []
        for o in leaves:
            {"complete": satisfied, "outstanding": outstanding}.get(o.state, underway).append(o)
        shared_done = {
            c: sorted(p for p, applied in counted_for.items() if c in applied)
            for c in sorted(a.applied)
            if any(c in applied for applied in counted_for.values())
        }
        shared_needed = {
            n.course_id: sorted(_programs_of(n) & programs)
            for n in combined.needs
            if n.course_id
            and n.course_id not in shared_done  # a planned course is already listed
            and pid in _programs_of(n)
            and _programs_of(n) & programs
        }
        mine = _attributed(pid, new)
        impacts.append(
            Impact(pid, kinds[pid], a, satisfied, underway, outstanding, shared_done, shared_needed, mine)
        )

    for imp in impacts:
        imp.warnings = _minor_rules(imp, base_audits, add_audits, combined, kinds)
    return Exploration(baseline, combined, impacts, new)


def _attributed(pid: str, new: list[Need]) -> list[Need]:
    """New courses an added program is responsible for: those it names, and
    the prerequisites they bring ("before X" where X is already its own)."""
    mine = [n for n in new if pid in _programs_of(n)]
    labels = {n.course_id.replace("-", " ") for n in mine if n.course_id}
    grew = True
    while grew:
        grew = False
        for n in new:
            if n in mine or not n.course_id:
                continue
            if any(r.startswith("before ") and r[7:] in labels for r in n.reasons):
                mine.append(n)
                labels.add(n.course_id.replace("-", " "))
                grew = True
    return mine


def _courses_for(pid: str, audits: list[Audit], est: Estimate) -> set[str]:
    """Courses that count toward a program: on the record or still to take."""
    applied = next((a.applied for a in audits if a.program_id == pid), set())
    planned = {n.course_id for n in est.needs if n.course_id and pid in _programs_of(n)}
    return set(applied) | planned


def _minor_rules(imp, base_audits, add_audits, combined, kinds) -> list[str]:
    """The catalog's two overlap rules for minors (p. 27), as warnings. The
    estimate does not re-plan around them; it says which one a plan breaks."""
    if imp.kind != "minor":
        return []
    audits = base_audits + add_audits
    minor = _courses_for(imp.program_id, audits, combined)
    majors = {p for p, k in kinds.items() if k == "major"}
    in_majors = set().union(*(_courses_for(p, audits, combined) for p in majors)) if majors else set()
    out = []
    outside = minor - in_majors
    if majors and len(outside) < 3:
        out.append(
            f"Only {len(outside)} of this minor's courses would fall outside the major; the catalog "
            "requires at least three (p. 27). Pick a course that does not also count toward the "
            "major for one of its choices. ('Outside the major area' is read here as not "
            "counting toward a declared major.)"
        )
    for other in (p for p, k in kinds.items() if k == "minor" and p != imp.program_id):
        own = minor - _courses_for(other, audits, combined)
        if len(own) < 4:
            out.append(
                f"With {other}, only {len(own)} of this minor's courses do not overlap; double minors "
                "need at least four that do not (p. 27)."
            )
    return out
