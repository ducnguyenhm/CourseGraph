# CourseGraph — Checkpoint 2 Design

## Context

Checkpoint #2 is due **October 5–9, 2026**, budgeted at 20–30 hours in the proposal. The
audience is fellow computer science students, so this is the checkpoint where the
prerequisite graph is meant to be *finished*: it is the most technically interesting
component, and the proposal sequences it here on purpose.

The proposal commits to five demonstrable items:

1. The prerequisite graph with a **layered layout** in which dependency flows consistently in
   one direction, with nodes **color-coded by completion status** drawn from a seeded
   student record.
2. Selecting a course highlights its complete **upstream** prerequisite chain and its
   **downstream** unlocked courses — and one such result is **verified against the catalog
   by hand** during the presentation.
3. **Cycle detection**: a deliberately corrupted catalog fixture containing a circular
   prerequisite is loaded, and ingestion rejects it with an error identifying the cycle.
4. **Department and program filtering** on the graph view, with **~100 courses across three
   departments** loaded.
5. The **topological ordering** the system computes for one degree program.

Nothing else. The requirement engine, the major explorer, and the minimum-semester estimate
are Checkpoint 3; the planner, auth, advisors and demo mode are Checkpoint 4.

## Starting state

Checkpoint 1 already did more of this than it promised, so CP2 is mostly closing gaps rather
than starting from zero.

| deliverable | already in place | gap |
|---|---|---|
| 1 layered layout | `compute_layers` assigns longest-path depth server-side; `/graph` draws columns by depth | order *within* a layer is alphabetical, so edges cross freely; depth is computed on the **filtered** subset (see below) |
| 1 status colors | — | no student, enrollment, or evaluator exists |
| 2 upstream | client-side transitive closure over `payload.edges` in `graph/page.tsx` | wrong under a subject filter; treats `or` branches as if all were required |
| 2 downstream | — | not built |
| 3 cycle detection | `find_cycle` (DFS, white/grey/black) runs in `scripts/seed.py` and prints the path; tested | no corrupted fixture; no way to run the check without writing to the DB |
| 4 three departments | CSC (29) + MATH (35) = 64 real courses, 10 stubs | **a third department must be curated** — ~36 more courses |
| 4 program filter | — | no `program` tables |
| 5 topological order | — | no program definition to order |

### Two latent bugs the CP2 work has to fix anyway

**Filtering changes the answer.** `GET /api/graph?subject=CSC` loads only CSC versions, and
`build_graph` drops edges whose source is outside the subset. So under the CSC filter:

- CSC-380's required edge from MATH-141 disappears — its upstream chain is reported as
  complete when it is missing a course;
- CSC-380's depth is recomputed without that edge, so it moves left — the column it sits in
  stops meaning "prerequisite depth".

Today this only bites three cross-department edges (`MATH-141 → CSC-380`,
`CSC-236 → MATH-323`, `CSC-121 → MATH-367`). With a third department it gets worse, and
deliverable 4 makes filtering a headline feature. **Fix: compute depth, reachability, and
status over the whole catalog year, then filter what is *returned*.** Edges leaving the
visible subset are returned as stubs (`external: true`) so the UI can draw a short "from
MATH 141" pointer instead of silently dropping it.

**The upstream chain over-reports.** The current closure follows every incoming edge,
including `or` branches. CSC-340 is "either CSC 231 or CSC 235", but its highlighted chain
says the student must take both. The proposal's wording is "the complete set of courses
that must be taken before it", which is a different set. This is also the course most
likely to be picked for the hand-verification beat, so it has to be right.

## Scope decisions (need an answer before building)

### Third department — recommend **ECON**

ECON is already 5 of the 10 stubs (`ECON-100/350/375/385/450`) and 10 of the 16
references CSC and MATH make outside themselves. Curating it turns existing dangling stubs
into real nodes, and makes the department filter demo interesting: switching to MATH alone
should visibly show the ECON pointers into MATH-331.

Alternatives are PHYS (heavy MATH overlap, but nothing currently cites it) or BUSA/PSY
(only one or two inbound references each). Whatever is chosen, the bar is ~36 courses at the
same curation standard as CSC/MATH: one fixture, `conventions`-compliant trees, ambiguities
recorded in `notes`, checked line by line against the catalog PDF.

**This is the critical path and is hand work, not code.** Start it first; everything else
can be built against CSC+MATH and picks ECON up automatically when the fixture lands.

### Which program is ordered — recommend **the Computer Science major**

Its core is a real chain (121 → 125/231 → 235/236 → 498) with a cross-department leaf
(MATH-123) and an `or`-shaped elective block, so the ordering shows something non-trivial.
The Mathematics major is the fallback. The old `coursegraph-seed-data/majors_minors.json`
is a **cross-check only**, same as the old course scrape — program definitions are
transcribed from the 2025-26 catalog like everything else.

### Catalog year

The fixtures in the repo are 2025-26 and were verified against the 2025-26 PDF. The proposal
names 2026-27. Switching is out of scope for this week; the versioned schema means a 2026-27
load can be added later without touching the 2025-26 rows. Say so in the talk if asked,
rather than switch mid-checkpoint.

## Database schema — migration `0002`

Only what CP2 needs, shaped so CP3 and CP4 extend rather than rewrite it.

| table | columns | why now |
|---|---|---|
| `program` | `id PK`, `program_id UNIQUE` (`'MAJOR-CSC'`), `kind` (`major`/`minor`), `name`, `department` | program filter; `MAJOR-MATH` is already cited by MATH-495's `program` node |
| `program_version` | `id PK`, `program_id FK`, `catalog_year_id FK`, `requirement_root_id FK NULL`, `UNIQUE(program_id, catalog_year_id)` | same identity/version split as courses |
| `requirement` | `id PK`, `program_version_id FK`, `parent_id FK NULL` (self), `position`, `label`, `rule_type`, `spec JSONB` | the proposal's self-referential table, created now with its final shape |
| `student` | `id PK`, `name`, `catalog_year_id FK` (matriculation catalog), `class_standing`, `expected_graduation` | status coloring needs a student |
| `student_program` | `student_id FK`, `program_id FK`, `PK(both)` | "relevant to my declared programs" filter; `program` prereq nodes |
| `enrollment` | `id PK`, `student_id FK`, `course_id FK → course.id`, `term`, `status` (`completed`/`in_progress`), `grade NULL` | the transcript |
| `plan_item` | `id PK`, `student_id FK`, `course_id FK → course.id`, `term` | the "planned" state |

Notes:

- `enrollment` and `plan_item` reference **`course`**, not `course_version` — a transcript
  entry for CSC-122 must survive renumbering and resolve through `course_equivalence`.
- **Transcript and plan are separate tables on purpose.** A completed course is a fact; a
  planned one is an intention that CP4's drag-and-drop planner edits and advisors comment on.
  Putting `planned` in `enrollment.status` would have to be migrated back out at CP4.
  `plan` as a parent of `plan_item` (multiple named plans) is still deferred.
- `class_standing` is stored, not derived. Deriving it from entry term needs a "current term"
  setting and a credits rule; not worth it for one seeded student.
- `requirement.rule_type` is constrained to the proposal's four types
  (`specific_course`, `n_from_set`, `credit_minimum`, `attribute_count`) plus `all_of` /
  `any_of` for nesting. CP2 only needs to *store* requirements and read which course ids
  they mention; **evaluating** them is Checkpoint 3.

**Still deferred:** `plan`, `advisor`, `comment`, auth.

## Prerequisite evaluator (pulled forward from CP3)

"Eligible" vs "locked" is impossible without evaluating prerequisites against a student, so
the evaluator CP1 deferred to CP3 is built now. It is the piece CP3 and CP4 both build on,
so it gets the most tests.

Three-valued (Kleene) logic, since the fixtures define consent as UNKNOWN:

```
FALSE < UNKNOWN < TRUE
and = min(children)      or = max(children)
```

| leaf | evaluates to |
|---|---|
| `none` | TRUE |
| `course` | TRUE if the id — after equivalence resolution — is in the student's completed or in-progress set, else FALSE |
| `coreq` | TRUE if completed/in progress, else UNKNOWN (may be taken together) |
| `consent` | UNKNOWN, always |
| `standing` | compare `class_standing` against `min_level` / `max_level` |
| `course_level` | count completed courses in `subject` numbered ≥ `min_number` |
| `program` | TRUE if declared in `student_program`, else FALSE |
| `placement` | UNKNOWN — no placement scores are modelled yet |

Two details that are easy to get wrong:

- **Equivalences run forward from the transcript, both relations.** The graph currently
  reads only `renumber` rows. The evaluator also needs `satisfies`: a student with MATH-136
  on record satisfies a MATH-151 prerequisite. Expand the completed set through the
  equivalence table once, before evaluating anything.
- **In-progress counts as satisfied** for eligibility (the standard registration
  assumption — you can register for next term's course while finishing its prerequisite).

The return value is not just a truth value: for UNKNOWN and FALSE it carries **the
specific leaves responsible** ("needs CSC 231", "needs instructor consent"). The side panel
shows them now, and CP4's planner rejection message ("names the specific unmet
prerequisite") is the same output.

### Node status

Precedence, first match wins:

| status | rule | fill | border | icon |
|---|---|---|---|---|
| completed | completed (after equivalence) | solid | solid, heavy | check |
| planned | in progress, or in `plan_item` | tinted | dashed | calendar |
| eligible | prerequisites evaluate TRUE **or UNKNOWN** | light | solid | open circle |
| locked | prerequisites evaluate FALSE | muted | dotted | lock |

UNKNOWN is drawn as eligible plus the existing ◆ condition marker. Drawing it as locked would
repeat the proposal's "consent always fails" behaviour that CP1 already rejected.

The proposal's UI section requires border style **and** icon in addition to colour; the table
above satisfies that, so state is never conveyed by colour alone.

Status comes back on the graph payload (`GET /api/graph?student=demo`) as
`status` + `unmet: [...]` per node, so the page is still one request.

## Reachability — upstream and downstream

Moves to the backend (`services/reachability.py`), computed over the **full** catalog year,
which fixes the filtering bug by construction. The proposal's Algorithms section already
describes it this way: reverse and forward DFS at query time.

`GET /api/graph/chain/{course_id}` →

```jsonc
{
  "course_id": "CSC-340",
  "upstream":   [{"course_id": "CSC-121", "necessity": "required"},
                 {"course_id": "CSC-125", "necessity": "required"},
                 {"course_id": "CSC-231", "necessity": "alternative", "group": "CSC-340#or1"},
                 {"course_id": "CSC-235", "necessity": "alternative", "group": "CSC-340#or1"}],
  "downstream": [{"course_id": "...", "necessity": "required"}]
}
```

- **Upstream `required`** = courses on *every* satisfying path, computed recursively: a
  course leaf contributes itself **plus its own required set**, `and` takes the union, `or`
  the intersection. This is *not* the closure of the existing `required_ids()` — that
  returns nothing for CSC-340 (231 and 235 share no direct id), and would miss that both
  branches pass through CSC-125 and CSC-121. **Upstream `alternative`** = everything else
  reachable through an `or` branch. The UI draws the two differently, and the header counts
  required courses separately ("2 courses must come first, plus one of 2 alternatives").
- **Downstream** follows outgoing edges forward. `necessity: required` means the course
  can't be taken without the selected one; `alternative` means the selected course is one
  way in.
- Coreq edges are excluded from both directions — they constrain *same term*, not *before*.

### The hand-verification beat

Pick the course before the talk and rehearse it:

1. Click it; read the highlighted upstream set aloud from the side panel.
2. Open the catalog PDF to that course's prerequisite sentence and walk it backwards one
   level at a time until every branch bottoms out at a course with no prerequisite.
3. The two sets match, and the alternatives are shown as alternatives.

CSC-340 is the best choice: short enough to walk live, and the `or` is visible. A deeper
alternative is CSC-498 (standing + `course_level`), but it shows badges rather than edges.

## Layered layout

Depth already comes from `compute_layers` (longest path, coreqs excluded). Two changes:

1. **Compute depth over the full catalog year**, then filter (above).
2. **Order nodes within each layer by the barycenter heuristic**, the standard
   crossing-reduction step of a Sugiyama layout: a few alternating down/up sweeps, each
   placing a node at the mean position of its neighbours in the adjacent layer, with ties
   broken by course id so the layout is deterministic. Return `order` alongside `layer`; the
   frontend stops sorting alphabetically.

Test with a crossing count: the barycenter order must have no more crossings than
alphabetical on the real fixtures, and strictly fewer on a hand-built case. The before/after
crossing count is also a good number for the talk.

The layer-0 column (24 of 64 courses have no prerequisite) still wraps into sub-columns; with
a program filter on, it is short enough not to need it.

## Cycle detection demo

`find_cycle` and the seed-time refusal already work and are tested. What is missing is the
demo itself:

- **`scripts/seed.py --check`** — parse and validate, print the result, exit non-zero on
  failure, **never open a DB session**. The demo must not depend on (or risk) the live
  database.
- **Reject duplicate course ids across fixtures.** `read_fixtures` currently appends every
  entry and the `trees` dict keeps the last one, so a second file defining CSC-231 silently
  wins. That would let a "patch" fixture overwrite real data without anyone noticing.
- **`data/corrupt/`**, committed, each file a full standalone fixture so the demo is one
  command:
  - `csc_cycle_direct.json` — the CSC fixture with one prerequisite changed to close a loop:
    CSC-121 requires CSC-231, which requires CSC-125, which requires CSC-121.
  - `csc_cycle_via_renumber.json` — a cycle that only exists **after** equivalence
    resolution: CSC-235 is made to require the retired CSC-233, which resolves to CSC-236,
    which requires CSC-235. No id appears twice in the raw text, so a check that skipped
    equivalence resolution would pass it. This is the better talking point.
  - optionally `csc_or_loop.json` — a loop that exists only through an `or` branch, which is
    **accepted**, with the reason (an alternative is always escapable). Shows the check is
    precise, not just strict.

```sh
docker compose exec backend python -m scripts.seed --check data/corrupt/csc_cycle_direct.json
# refusing to load:
# 1 problem(s) found:
#   prerequisite cycle: CSC-121 -> CSC-231 -> CSC-125 -> CSC-121
```

Today the renumber case reports `CSC-235 -> CSC-236 -> CSC-235` — correct, but the fixture
text never mentions CSC-236, so on stage it reads like a wrong answer. `find_cycle` should
carry the cited id through and print `CSC-235 -> CSC-236 (cited as CSC-233) -> CSC-235`,
the same `via` the graph edges already record.

Each corrupted fixture gets a test asserting the exact cycle reported, so the demo cannot
silently rot.

## Topological ordering for one program

`services/ordering.py`, exposed as `GET /api/programs/{program_id}/order`.

1. Course set = every course id mentioned in the program's requirements, plus the upstream
   **required** closure of each (you cannot order MATH-223 without MATH-151 in the set).
2. Edges = required edges only, after equivalence resolution. Alternatives and coreqs do not
   constrain ordering — same rule `find_cycle` already uses.
3. **Kahn's algorithm**, emitting in rounds: each round is every course whose remaining
   in-degree is zero. Return the rounds, not just a flat list:

```jsonc
{"program_id": "MAJOR-CSC",
 "rounds": [["CSC-121", "MATH-123"], ["CSC-125", "CSC-231"], ["CSC-235", "CSC-236"], ...],
 "order":  ["CSC-121", "MATH-123", "CSC-125", ...]}
```

The rounds are the antichains of the DAG: courses in the same round can be taken together.
The number of rounds is the length of the longest chain, which **is** CP3's
chain-based lower bound on semesters — so this is CP3's minimum-semester computation
showing up a checkpoint early. Worth saying in the talk; worth not building further now.

Kahn's also detects a cycle (courses left over with non-zero in-degree). Validation already
rejects those at ingestion, so this path should be unreachable — assert it, don't handle it.

Frontend: a "Show order" toggle when a program filter is active, numbering each node by its
round and listing the rounds in the side panel.

## Filtering

Replace the CSC/MATH `<select>` with:

- **Departments** — checkboxes per subject present in the catalog year (CSC, MATH, ECON).
- **Program** — one program, or "My declared programs" (the seeded student's
  `student_program` rows). Shows the program's course set plus its upstream closure.
- Edges crossing out of the visible set render as short `external` pointers labelled with
  the source course, never silently dropped.

`GET /api/graph?subject=CSC&subject=ECON&program=MAJOR-CSC&student=demo` — filters
intersect.

## Seed data

- **`data/<dept>_catalog_2025_26.json`** — the third department. Stubs it replaces are
  removed from `math_catalog_2025_26.json`'s `stub_courses`, and the duplicate-id check above
  catches any that are missed.
- **`data/programs_2025_26.json`** — at least `MAJOR-CSC` and `MAJOR-MATH` (the latter is
  already referenced by MATH-495), plus the two minors if time allows. Same
  `catalog_year` rule as the course fixtures; requirement trees must reference only courses
  that exist, enforced by the existing dangling-reference check.
- **`data/demo_student.json`** — one **fictional** student (not the author's transcript; that
  is a CP3 validation step, not seed data), declared CSC major + MATH minor, sophomore, built
  so every status appears on the default view:
  - completed: an intro sequence, including **one course under a retired number** (CSC-122)
    so equivalence resolution visibly turns CSC-235 green;
  - in progress: one course, to show it counting toward eligibility;
  - planned: two or three `plan_item` rows;
  - at least one course that is eligible **only** via UNKNOWN (consent), and plenty locked.

The old `coursegraph-seed-data/demo_user.json` predates the renumbering logic and the v2
schema; don't import it.

## API surface (additions)

| method | path | purpose |
|---|---|---|
| `GET` | `/api/graph?subject=…&program=…&student=…` | adds `order`, `status`, `unmet`, `external` edges — deliverables 1, 4 |
| `GET` | `/api/graph/chain/{course_id}` | upstream/downstream with necessity — deliverable 2 |
| `GET` | `/api/programs` | list programs for the filter |
| `GET` | `/api/programs/{program_id}/order` | topological rounds — deliverable 5 |
| `GET` | `/api/students/{id}` | transcript, plan, declared programs (for the panel) |

## Frontend

- `/graph`: status fill/border/icon per node, a status legend beside the existing edge
  legend, downstream highlight (distinct colour from upstream), department checkboxes,
  program select, "Show order" toggle, `external` edge pointers.
- Side panel: add **unmet conditions** for the selected course, and **programs it counts
  toward** (from `requirement` rows — the proposal's UI spec lists it, and it is cheap once
  the table exists).
- `AppShell`/home page: "Checkpoint 1" labels → "Checkpoint 2".

## Build order

Sequenced so the hand work starts on day one and the demo-critical items land first.

| # | Task | Hours |
|---|---|---|
| 0 | **Start curating the third department** — runs in parallel with everything below | 6–8 |
| 1 | `seed.py --check`, duplicate-id rejection, `data/corrupt/` fixtures + tests | 2 |
| 2 | Reachability service over the full catalog, `necessity`, `/chain` endpoint, tests | 3 |
| 3 | Migration 0002; program + demo-student fixtures; seed them | 3–4 |
| 4 | Three-valued evaluator + node status, with tests for every leaf type | 3–4 |
| 5 | Full-catalog depth + barycenter ordering + crossing-count test | 2–3 |
| 6 | Topological rounds + endpoint | 1–2 |
| 7 | Frontend: status styling, downstream, filters, order view | 4–5 |
| 8 | Load the third department; check counts; rehearse the hand-verification and the cycle demo; record fallback capture | 2 |
|   | **Total** | **26–33** |

**If the week runs short, cut in this order:** the `or`-loop fixture → "My declared
programs" filter → barycenter ordering (depth columns alone still satisfy "dependency flows
in one direction") → minors. Do **not** cut the third department below ~25 courses or the
`necessity` split on upstream — the first is a stated bar, the second is what makes the
hand-verification come out right.

## Risks

- **Curation, again.** ~36 courses at this standard is most of a day of careful work. If the
  third department lands partial, load what is verified and say so; 90 well-curated courses
  beats 100 with guessed prerequisites.
- **The evaluator's edge cases surface on stage.** `standing` + `course_level` (CSC-498) and
  the `satisfies` equivalence are the likeliest to be wrong. Each gets a dedicated test, and
  the demo student is built to exercise them on purpose rather than by accident.
- **Docker on the demo machine.** Same fallbacks as CP1; record the capture after step 8.

## Verification

From a clean clone, `docker compose down -v && docker compose up --build`:

1. Seed log reports ~100 courses across three departments, programs, and the demo student.
2. `/graph` opens on the demo student: all four statuses visible, legend explains fill,
   border, and icon; no state is distinguishable by colour alone.
3. Click CSC-340: upstream shows required vs alternative; walk it against the catalog PDF.
4. Click a low-numbered course: downstream unlocks highlight in a different colour.
5. Filter to CSC only, select CSC-380: MATH-141 is still in its chain, as an external pointer.
6. `seed.py --check data/corrupt/csc_cycle_direct.json` and `…_via_renumber.json` → each is
   refused naming the cycle; the live DB is untouched (`/health` course count unchanged).
7. Program filter → CS major; "Show order" numbers nodes by round;
   `GET /api/programs/MAJOR-CSC/order` in `/docs` returns the same rounds.
8. `pytest` — evaluator, reachability, ordering, barycenter and corrupted-fixture tests pass.
