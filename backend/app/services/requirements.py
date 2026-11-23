"""Evaluate a program's requirement tree against one student's record.

The four rule types fall into two kinds, and the difference is the whole design:

- **Allocating** rules — `specific_course`, `n_from_set` — each need courses of
  their own. Within one program a course fills at most one of them: CSC 498 is
  a core course of the CS major, so it cannot also be one of the "three CSC
  courses at the 300 or 400 level" (the catalog excludes it there anyway).
  Which course goes where is a bipartite matching, not a greedy pass: a student
  with MATH 223 and MATH 123 on record, facing "MATH 123 (or 223)" and "one of
  MATH 223, 251", needs 123 in the first slot for both to be met.

- **Counting** rules — `credit_minimum`, `attribute_count` — observe courses
  without using them up. "Number 300 & 400 level courses: four including
  CSC 498" counts courses the other rules already placed; "31 credits" and
  "W competence" count the whole record.

  An `attribute_count` marked `exclusive` allocates instead. Exploratory
  Foundations are written that way: "no course may be used to satisfy more
  than one", and many courses are tagged "Arts and Humanities-or-Global
  Learning", so an AH-or-GL course fills one of the two, never both. Their
  `distinct_group` adds "each of the six AH/SM/SS credits from a different
  subject". That is not a bipartite matching any more, so the few slots it
  covers are searched exhaustively and everything else is matched around each
  candidate assignment.

`any_of` picks one branch. Every combination of branches is tried and the one
leaving the least work is kept — real programs have a handful of `any_of`
nodes, so this stays small.

Programs are evaluated independently: a course may count toward a major *and*
a minor, and `overlaps` reports where it does.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from app.services.validation import resolve

# Best first. A requirement filled partly by in-progress work is in progress.
STATES = ("completed", "in_progress", "planned")
# What a requirement is, from the states of the courses meeting it.
PROGRESS = ("complete", "in_progress", "planned", "outstanding")
_AS_PROGRESS = {"completed": "complete", "in_progress": "in_progress", "planned": "planned"}
ALLOCATING = {"specific_course", "n_from_set"}
COUNTING = {"credit_minimum", "attribute_count"}
# Exploratory Foundations areas. A course the catalog prints as "X-or-Y"
# carries both, and fills whichever one the engine (or the student) picks.
FOUNDATION_AREAS = frozenset({"AH", "SM", "SS", "LA", "GL", "PPD"})
# Distinct-subject assignments tried before giving up; a real degree has six
# such slots and a student a handful of candidates for each.
SEARCH_LIMIT = 50_000


class RequirementLike(Protocol):
    label: str
    rule_type: str
    spec: dict
    children: Sequence["RequirementLike"]


@dataclass(frozen=True)
class CourseInfo:
    subject: str
    number: int
    credits: float
    # Distribution area, catalog attributes (ES, GL, ...): what the course
    # always carries. Competence is per section, so it lives on the entry.
    tags: frozenset[str] = frozenset()
    # Outside the curated departments: its prerequisites are not recorded,
    # so it only looks easy to take.
    stub: bool = False


@dataclass(frozen=True)
class Entry:
    """One course on a student's record, in current numbering."""

    course_id: str
    state: str  # completed | in_progress | planned
    counts_as: frozenset[str]  # itself, its old number, whatever it satisfies
    subject: str
    number: int
    credits: float
    tags: frozenset[str]


@dataclass
class Record:
    entries: list[Entry]

    @classmethod
    def build(
        cls,
        taken: Iterable[tuple[str, str, str | None]],
        catalog: dict[str, CourseInfo],
        equivalences: Iterable[tuple[str, str, str]] = (),
    ) -> "Record":
        """taken: (course_id, state, competence earned in that section or None,
        optionally the Foundations area the student pinned it to or None).
        equivalences: (from_id, to_id, relation) rows, every relation."""
        counts_as: dict[str, set[str]] = {}
        renumbering: dict[str, str] = {}
        for f, t, relation in equivalences:
            counts_as.setdefault(f, set()).add(t)
            if relation == "renumber":
                renumbering[f] = t

        def expand(cid: str) -> frozenset[str]:
            out, stack = set(), [cid]
            while stack:
                c = stack.pop()
                if c not in out:
                    out.add(c)
                    stack.extend(counts_as.get(c, ()))
            return frozenset(out)

        best: dict[str, Entry] = {}
        for raw, state, competence, *pinned in taken:
            cid = resolve(raw, renumbering)
            info = catalog.get(cid) or catalog.get(raw)
            subject, number = cid.split("-")
            tags = info.tags if info else frozenset()
            if pinned and pinned[0]:
                # "Count REL 130 as Global Learning": it stops being an
                # Arts and Humanities candidate for this student.
                tags = (tags - FOUNDATION_AREAS) | {pinned[0]}
            entry = Entry(
                course_id=cid,
                state=state,
                counts_as=expand(raw) | expand(cid),
                subject=subject,
                number=int(number),
                credits=info.credits if info else 1.0,
                tags=tags | ({competence} if competence else set()),
            )
            # A repeat (or CSC 122 and CSC 235 both on record) is one course.
            old = best.get(cid)
            if old is None or STATES.index(state) < STATES.index(old.state):
                best[cid] = entry if old is None else _merge(entry, old)
            else:
                best[cid] = _merge(old, entry)
        return cls(sorted(best.values(), key=lambda e: (STATES.index(e.state), e.course_id)))


def _merge(keep: Entry, other: Entry) -> Entry:
    return Entry(
        keep.course_id, keep.state, keep.counts_as | other.counts_as,
        keep.subject, keep.number, keep.credits, keep.tags | other.tags,
    )


@dataclass
class Outcome:
    label: str
    rule_type: str
    spec: dict
    # complete | in_progress | planned | outstanding
    state: str
    # Courses this requirement is met with. For counting rules, the courses
    # it counted.
    applied: list[str] = field(default_factory=list)
    need: float = 0  # courses, or credits for credit_minimum
    have: float = 0
    # Courses in the catalog that would count here and are not on the record.
    options: list[str] = field(default_factory=list)
    children: list["Outcome"] = field(default_factory=list)
    # False on an any_of branch that was not used.
    chosen: bool = True
    notes: str = ""
    # need/have are in courses (allocating rules and groups), so they add up
    # in a group's totals; credit and plain attribute counts do not.
    in_courses: bool = True

    @property
    def remaining(self) -> float:
        return max(0.0, self.need - self.have)


@dataclass
class Audit:
    program_id: str
    root: Outcome
    # Courses the allocating rules placed — what "counts toward" the program.
    applied: set[str]

    def leaves(self) -> Iterable[Outcome]:
        def walk(o: Outcome):
            if not o.chosen:
                return
            if o.children:
                for c in o.children:
                    yield from walk(c)
            else:
                yield o

        return walk(self.root)


def _label(cid: str) -> str:
    return cid.replace("-", " ")


def _in_set(spec: dict, e: Entry) -> bool:
    """Does entry `e` belong to an n_from_set's set?"""
    if "courses" in spec and any(c in e.counts_as for c in spec["courses"]):
        return True
    if "subject" in spec:
        return (
            e.subject == spec["subject"]
            and e.number >= spec.get("min_number", 0)
            and not (e.counts_as & set(spec.get("exclude", [])))
        )
    return False


def _counts(spec: dict, e: Entry) -> bool:
    """Does entry `e` pass a counting rule's filters?"""
    if "subject" in spec and e.subject != spec["subject"]:
        return False
    if e.number < spec.get("min_number", 0):
        return False
    if "attribute" in spec and spec["attribute"] not in e.tags:
        return False
    return True


def _accepts(rule_type: str, spec: dict, e: Entry) -> bool:
    if rule_type == "specific_course":
        return spec["course_id"] in e.counts_as
    if rule_type == "attribute_count":
        return _counts(spec, e)
    return _in_set(spec, e)


def allocates(rule_type: str, spec: dict) -> bool:
    """Does this rule take courses for itself (one course, one rule)?"""
    return rule_type in ALLOCATING or (rule_type == "attribute_count" and bool(spec.get("exclusive")))


def _slots(rule_type: str, spec: dict) -> int:
    return 1 if rule_type == "specific_course" else spec["n"]


class Engine:
    """Evaluates requirement trees against one record."""

    def __init__(self, record: Record, catalog: dict[str, CourseInfo]):
        self.record = record
        self.catalog = catalog
        self.by_id = {e.course_id: e for e in record.entries}
        self.on_record = set().union(*(e.counts_as for e in record.entries))

    def audit(self, program_id: str, root: RequirementLike) -> Audit:
        nodes: list[RequirementLike] = []

        def collect(n: RequirementLike):
            nodes.append(n)
            for c in n.children:
                collect(c)

        collect(root)
        choices = [n for n in nodes if n.rule_type == "any_of" and n.children]
        best: tuple | None = None
        for combo in itertools.product(*(range(len(n.children)) for n in choices)):
            picked = {id(n): i for n, i in zip(choices, combo)}
            outcome, applied = self._evaluate(root, picked)
            leaves = list(_active_leaves(outcome))
            score = (
                sum(o.remaining for o in leaves),
                -sum(
                    1
                    for o in leaves
                    if allocates(o.rule_type, o.spec)
                    for c in o.applied
                    if self.by_id[c].state == "completed"
                ),
                combo,
            )
            if best is None or score < best[0]:
                best = (score, outcome, applied)
        _, outcome, applied = best
        return Audit(program_id=program_id, root=outcome, applied=applied)

    # -- one fixed choice of any_of branches -------------------------------

    def _evaluate(self, root: RequirementLike, picked: dict[int, int]) -> tuple[Outcome, set[str]]:
        active: list[RequirementLike] = []

        def mark(n: RequirementLike, on: bool):
            if on:
                active.append(n)
            for i, c in enumerate(n.children):
                mark(c, on and (n.rule_type != "any_of" or picked[id(n)] == i))

        mark(root, True)
        slots = [
            n
            for n in active
            if allocates(n.rule_type, n.spec)
            for _ in range(_slots(n.rule_type, n.spec))
        ]
        # Most constrained first, so the matching settles them early; the
        # result is maximal either way.
        slots.sort(
            key=lambda n: 0 if n.rule_type == "specific_course"
            else 1 if "courses" in n.spec else 2 if n.rule_type == "n_from_set" else 3
        )
        match = _allocate(slots, self.record.entries)
        placed: dict[int, list[str]] = {}
        for slot_i, entry_i in match.items():
            placed.setdefault(id(slots[slot_i]), []).append(self.record.entries[entry_i].course_id)
        applied = {c for cs in placed.values() for c in cs}

        def build(n: RequirementLike, chosen: bool) -> Outcome:
            kids = [
                build(c, chosen and (n.rule_type != "any_of" or picked[id(n)] == i))
                for i, c in enumerate(n.children)
            ]
            o = self._leaf(n, placed.get(id(n), []), applied) if not kids else _group(n, kids)
            o.chosen = chosen
            o.notes = getattr(n, "notes", "") or ""
            return o

        return build(root, True), applied

    def _leaf(self, n: RequirementLike, placed: list[str], applied: set[str]) -> Outcome:
        spec, rule = n.spec, n.rule_type
        if rule == "specific_course":
            o = Outcome(n.label or _label(spec["course_id"]), rule, spec, "", sorted(placed), 1, len(placed))
            o.options = [] if placed else [spec["course_id"]]
        elif rule == "n_from_set":
            o = Outcome(n.label, rule, spec, "", sorted(placed), spec["n"], len(placed))
            if o.remaining:
                o.options = self._catalog_matching(lambda e: _in_set(spec, e))
        elif rule == "credit_minimum":
            pool = self._pool(spec, applied)
            counted = [e for e in pool if _counts(spec, e)]
            o = Outcome(n.label, rule, spec, "", [e.course_id for e in counted], spec["credits"])
            o.have = sum(e.credits for e in counted)
            o.in_courses = False
            if o.remaining and spec.get("scope", "record") == "record":
                o.options = self._catalog_matching(lambda e: _counts(spec, e)) if _filtered(spec) else []
        elif rule == "attribute_count" and spec.get("exclusive"):
            o = Outcome(n.label, rule, spec, "", sorted(placed), spec["n"], len(placed))
            if o.remaining:
                o.options = self._catalog_matching(lambda e: _counts(spec, e))
        elif rule == "attribute_count":
            counted = [e for e in self._pool(spec, applied) if _counts(spec, e)]
            if spec.get("distinct_subjects"):
                # Exploratory Foundations: each credit from a different subject.
                seen: set[str] = set()
                counted = [e for e in counted if not (e.subject in seen or seen.add(e.subject))]
            o = Outcome(n.label, rule, spec, "", [e.course_id for e in counted], spec["n"], len(counted))
            o.in_courses = False
            if o.remaining:
                o.options = self._catalog_matching(lambda e: _counts(spec, e))
        else:
            raise ValueError(f"{rule} must have children")
        o.state = self._fill_state(o)
        return o

    def _pool(self, spec: dict, applied: set[str]) -> list[Entry]:
        if spec.get("scope", "record") == "program":
            return [e for e in self.record.entries if e.course_id in applied]
        return self.record.entries

    def _fill_state(self, o: Outcome) -> str:
        if o.remaining:
            return "outstanding"
        used = [self.by_id[c] for c in o.applied]
        if not allocates(o.rule_type, o.spec):
            # Met once enough is counted, best courses first: 31 credits are
            # complete even while a 32nd is in progress.
            used.sort(key=lambda e: STATES.index(e.state))
            total, enough = 0.0, []
            for e in used:
                enough.append(e)
                total += e.credits if o.rule_type == "credit_minimum" else 1
                if total >= o.need:
                    break
            used = enough
        worst = max((e.state for e in used), key=STATES.index, default="completed")
        return _AS_PROGRESS[worst]

    def options_for(self, rule_type: str, spec: dict) -> list[str]:
        """Catalog courses not on the record that would count toward a rule."""
        if rule_type == "specific_course":
            return [] if spec["course_id"] in self.on_record else [spec["course_id"]]
        if rule_type == "n_from_set":
            return self._catalog_matching(lambda e: _in_set(spec, e))
        return self._catalog_matching(lambda e: _counts(spec, e))

    def _catalog_matching(self, test) -> list[str]:
        out = []
        for cid, info in sorted(self.catalog.items()):
            if cid in self.on_record:
                continue
            probe = Entry(cid, "planned", frozenset({cid}), info.subject, info.number, info.credits, info.tags)
            if test(probe):
                out.append(cid)
        return out


def _filtered(spec: dict) -> bool:
    return any(k in spec for k in ("subject", "min_number", "attribute"))


def _group(n: RequirementLike, kids: list[Outcome]) -> Outcome:
    used = kids
    if n.rule_type == "any_of":
        # Only the branch taken; the others are reported but not counted.
        used = [k for k in kids if k.chosen] or kids[:1]
    # Credit and plain attribute counts are left out of the group's course
    # totals; they still decide its state.
    courses = [k for k in used if k.in_courses]
    return Outcome(
        n.label,
        n.rule_type,
        n.spec,
        max((k.state for k in used), key=PROGRESS.index),
        sorted({c for k in courses for c in k.applied}),
        need=sum(k.need for k in courses),
        have=sum(min(k.have, k.need) for k in courses),
        children=kids,
        # "Competencies" is three counts, not a number of courses.
        in_courses=bool(courses),
    )


def _active_leaves(o: Outcome) -> Iterable[Outcome]:
    if not o.chosen:
        return
    if o.children:
        for c in o.children:
            yield from _active_leaves(c)
    else:
        yield o


def _group_of(n: RequirementLike) -> object | None:
    """The distinct-subject group an exclusive attribute rule belongs to."""
    if n.rule_type != "attribute_count" or not n.spec.get("exclusive"):
        return None
    if n.spec.get("distinct_group"):
        return n.spec["distinct_group"]
    return id(n) if n.spec.get("distinct_subjects") else None


def _allocate(slots: list[RequirementLike], entries: list[Entry]) -> dict[int, int]:
    """slot index -> entry index: as many slots filled as possible, then as
    many with completed courses.

    Slots under a distinct-subject group are assigned by exhaustive search;
    for each candidate assignment the remaining slots get a maximum matching
    over the courses left. Without such slots this is just the matching.
    """
    gated_rules: list[RequirementLike] = []
    for n in slots:
        if _group_of(n) is not None and all(n is not g for g in gated_rules):
            gated_rules.append(n)
    free = [i for i, n in enumerate(slots) if _group_of(n) is None]
    if not gated_rules:
        return _max_matching(slots, entries, free, set())

    def done(m: dict[int, int]) -> tuple[int, int]:
        return len(m), sum(1 for ei in m.values() if entries[ei].state == "completed")

    def options(rule: RequirementLike) -> list[tuple[int, ...]]:
        cands = [i for i, e in enumerate(entries) if _counts(rule.spec, e)]
        out = []
        for k in range(min(rule.spec["n"], len(cands)), -1, -1):
            for combo in itertools.combinations(cands, k):
                subjects = [entries[i].subject for i in combo]
                if len(set(subjects)) == len(subjects):
                    out.append(combo)
        return out

    per_rule = [options(r) for r in gated_rules]
    best: tuple[tuple[int, int], dict[int, int]] | None = None
    tried = 0

    def search(r: int, used: set[int], subjects: dict[object, set[str]], chosen: dict[int, tuple[int, ...]]):
        nonlocal best, tried
        if r == len(gated_rules):
            tried += 1
            if tried > SEARCH_LIMIT:
                raise RuntimeError("distinct-subject search exceeded its limit")
            m = _max_matching(slots, entries, free, used)
            for ri, combo in chosen.items():
                mine = [i for i, n in enumerate(slots) if n is gated_rules[ri]]
                m.update(zip(mine, combo))
            score = done(m)
            if best is None or score > best[0]:
                best = (score, m)
            return
        group = _group_of(gated_rules[r])
        taken = subjects.setdefault(group, set())
        for combo in per_rule[r]:
            if used.intersection(combo) or taken.intersection(entries[i].subject for i in combo):
                continue
            new = {entries[i].subject for i in combo}
            taken |= new
            chosen[r] = combo
            search(r + 1, used | set(combo), subjects, chosen)
            taken -= new
            del chosen[r]

    search(0, set(), {}, {})
    return best[1]


def _max_matching(
    slots: list[RequirementLike], entries: list[Entry], which: list[int], blocked: set[int]
) -> dict[int, int]:
    """slot index -> entry index for the slots in `which`, maximum
    cardinality (Kuhn's augmenting paths), never using a `blocked` entry.
    Entries are tried best state first, so where there is a choice a
    completed course is used before an in-progress one."""
    owner: dict[int, int] = {}  # entry -> slot

    def augment(s: int, seen: set[int]) -> bool:
        for ei, e in enumerate(entries):
            if ei in seen or ei in blocked or not _accepts(slots[s].rule_type, slots[s].spec, e):
                continue
            seen.add(ei)
            if ei not in owner or augment(owner[ei], seen):
                owner[ei] = s
                return True
        return False

    for s in which:
        augment(s, set())
    return {s: ei for ei, s in owner.items()}


def overlaps(audits: Iterable[Audit]) -> dict[str, list[str]]:
    """course id -> the programs it counts toward, for courses in two or more."""
    by_course: dict[str, list[str]] = {}
    for a in audits:
        for cid in a.applied:
            by_course.setdefault(cid, []).append(a.program_id)
    return {c: sorted(ps) for c, ps in sorted(by_course.items()) if len(ps) > 1}
