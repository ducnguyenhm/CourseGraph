# CourseGraph — Checkpoint 3 Design

## Context

Checkpoint #3 is due **October 26–30, 2026**, budgeted at 25–35 hours in the proposal. The
talk is framed for investors, so this is where the **major and minor explorer** has to be
finished, since it answers the question a non-technical audience cares about: *if I add this
program, can I still graduate on time?*

The proposal commits to five demonstrable items:

1. The **requirement engine** evaluating a seeded student against a complete major, showing
   satisfied and outstanding requirements, with **at least one requirement of each
   implemented rule type**.
2. The **major and minor explorer**: add a second, undeclared program to a seeded student and
   show the recomputed remaining courses, the **courses that overlap** with their existing
   program, and the **additional credits** required.
3. The **minimum-semester calculation**, showing both the **longest remaining prerequisite
   chain** and the **credit-based bound**, and that the system reports the greater of the two.
4. The **degree progress view**: grouped requirement categories with completion state, for a
   student holding **two declared programs**.
5. The engine's **unit test suite** passing, including tests for **alternative groups** and
   **courses counted toward more than one program**.

The planner, overload warnings, auth, advisors and demo mode are still Checkpoint 4.

## Starting state

| deliverable | already in place | gap |
|---|---|---|
| 1 engine | `requirement` table and `rule_type` constraint (migration 0002); program fixtures; `program_courses()` reads which courses a program names | **nothing evaluates a requirement**; no fixture uses `credit_minimum` or `attribute_count` |
| 2 explorer | `GET /api/programs/{id}`; four programs (CSC/MATH major and minor) | no explorer endpoint or page; no program that overlaps the demo student's |
| 3 min semesters | `Orderer` computes rounds from scratch, and the CP2 doc already notes rounds = the chain bound | rounds ignore what the student has done; no credit bound; no "current term" |
| 4 progress view | demo student already holds two programs (`MAJOR-CSC`, `MINOR-MATH`) | no progress endpoint or page |
| 5 tests | 82 backend tests (evaluator, ordering, reachability, fixtures) | no requirement tests |

## Already built on this branch: the requirement engine

`backend/app/services/requirements.py`, with 20 tests in `tests/test_requirements.py`
(102 total, all passing). It is pure Python with no database, like the evaluator and
`Orderer`.

The four rule types split into two kinds, and that split is the main design decision:

| kind | rule types | uses courses up? | counts over |
|---|---|---|---|
| **allocating** | `specific_course`, `n_from_set` | yes: within one program a course fills one slot | the record |
| **counting** | `credit_minimum`, `attribute_count` | no, it only observes | the record (`scope: "record"`, default) or the courses this program already placed (`scope: "program"`) |

This is how the catalog is written. "Number 300 & 400 Level Courses: Four including CSC 498"
counts courses the core and elective rules already placed; it doesn't need four more. "31
credits" and "W competence" count the whole record.

- **Allocation is a maximum bipartite matching** (Kuhn's augmenting paths), not a greedy pass.
  A student with MATH 123 and MATH 223 facing "123 or 223" and "223 or 251" needs 123 in the
  first slot, or the second requirement goes unmet. There is a test for exactly this.
  Completed courses are tried before in-progress ones, which are tried before planned ones.
- **`any_of` picks one branch.** Every combination of branches is tried and the one leaving
  the least work wins (ties go to the branch using more completed courses, then the first
  one written). Unchosen branches stay in the output marked `chosen: false`, so the UI can
  show "satisfied via MATH 223" and the alternatives.
- **Programs are evaluated independently.** A course can count toward a major and a minor;
  `overlaps()` reports each course that does. This is the multi-program question, so it is
  reported rather than hidden.
- **States:** `complete` / `in_progress` / `planned` / `outstanding`. A filled requirement
  takes the state of its least-finished course, and a group takes its least-finished child.
  A counting rule is complete once enough complete courses are counted: 31 credits done is
  complete even while a 32nd is in progress.
- **Equivalences** use the same rules as the prerequisite evaluator: CSC 122 on the record
  meets a CSC 235 requirement (`renumber`), and MATH 136 meets MATH 151 while still counting
  as itself (`satisfies`).
- **Competence is per section**, as the fixture conventions already say: Q on MATH 151 counts
  only if the transcript records it. Catalog attributes (ES, GL) and distribution areas (SM,
  SS) come from the course.
- Every outstanding requirement carries **`options`**: the catalog courses not on the record
  that would count. The explorer and the semester estimate choose from these.

Against the fixtures, the demo student's CS major is 9 of 11: core done except CSC 236 (in
progress) and CSC 498 (planned); electives 2 of 3 (CSC 322 and 340, both planned); MATH 123
done; the allied course is outstanding with no options, because the department's list
isn't printed in the catalog.

## Deliverable 1: done (2026-10-28)

Built with the recommendations for decisions 1 and 2 below (the degree as a program, the
300/400 count on the CS major); the Data Science minor and ECON programs are not added yet.

- **`DEGREE-BA`** in `programs_2025_26.json` (`kind: "degree"`), transcribed from pp. 15–23:
  31 credits, First-Year Seminar, six Exploratory Foundations areas, W/Q/S, two Extended
  Studies. Unverified, like the rest of the program fixture.
- **Exploratory Foundations are exclusive, not counted.** The catalog prints many areas as
  "Arts and Humanities-or-Global Learning", and says no course satisfies two Foundations
  requirements. Those rules take `exclusive: true`, so they allocate like `n_from_set`, and
  `distinct_group: "foundations"` enforces "six AH/SM/SS credits from six different
  subjects". That constraint is not a bipartite matching, so the engine searches those
  few slots exhaustively and matches everything else around each candidate.
- **The CS major** gains "Four 300/400-level courses, including CSC 498" as a
  `credit_minimum` with `scope: "program"`. With it, the major has three rule types and the
  degree supplies `attribute_count`. `test_cs_major_and_degree_cover_every_rule_type`
  asserts the pair covers all four.
- **Migration 0003**: `enrollment.competence` (W/Q/S, per section), `degree` allowed in
  `program.kind`. Seeding rejects a competence the course is never offered with.
- **`data/other_stubs_2025_26.json`**: six real 2025–26 courses outside CSC/MATH/ECON
  (ARTH 197 FYS, ARTH 132, JAPN 151–152, REL 130, SOC 237) for the demo transcript, which
  now has competence on MATH 151 (Q) and MATH 270 (W). Unverified.
- **`GET /api/students/{key}/audit/{program_id}`** and the **`/audit`** page (program
  picker, per-state counts, the rule types present, the requirement tree with state shown by
  fill, border and icon). `components/RequirementAudit.tsx` is meant to be reused by
  `/progress`.

Demo: `/audit?program=MAJOR-CSC`, then `/audit?program=DEGREE-BA`. In the degree audit, REL 130
(AH-or-GL) and SOC 237 (SS-or-PPD) each fill one area, so Global Learning and PPD stay
outstanding. That's the either-or rule working, and worth pointing at.

## Deliverable 3: done (2026-10-28)

`services/semesters.py`, `GET /api/students/{key}/semesters`, and the "Minimum terms to
finish" card at the top of `/audit`. 20 tests in `tests/test_semesters.py`.

- **What's left** is read off the audits of every declared program plus `DEGREE-BA` (plus
  any `add=`). That means unfilled slots, slots filled only by a planned course, and every
  prerequisite those need. For a choice, the estimate prefers a course already needed
  elsewhere, then one open without permission, then the earliest, then the one adding the
  fewest prerequisites. A slot nothing in the catalog can fill (the allied course, PPD)
  still costs one credit.
- **Chain bound:** `Orderer` now takes `done` and `terms_elapsed`. Done or in-progress
  courses sit at round 0, and senior standing is counted from the student's terms so far,
  not from semester one. A corequisite that is already done no longer pulls a course to
  round 0. The CP2 program order is unchanged (both default to empty).
- **Credit bound:** the larger of the named courses' credits and the degree floor (31
  minus credits done or in progress), divided by `max_load` (4.5 by default, per catalog
  p. 606).
- **Terms left:** the fall/spring terms after the term in progress, through
  `expected_graduation`.

Demo student: chain 2 (CSC 498 waits for senior standing), credits 13.5 ÷ 4.5 = 3, so **3
terms, on time** for Spring 2027. At 4.0 credits a term it becomes 4, one term late. The demo
student is always credit-bound. To show the chain winning, use a student with few credits
left and a long chain.

## Deliverable 2: done (2026-10-28)

`services/explore.py`, `GET /api/students/{key}/explore?add=…&max_load=…`, and the
**`/explore`** page. 9 tests in `tests/test_explore.py`, with the demo student shared through
`tests/conftest.py`.

- **Two estimates over the same record:** the declared programs plus the degree (baseline),
  and the same with the added programs. The added programs are audited like declared ones:
  - requirements already met by completed courses, under way, and outstanding;
  - courses that count twice, split into ones on the record and ones still to take;
  - new courses (on the combined plan, not on the baseline);
  - the change in minimum terms, and whether the student still graduates on time.
- **Two "how much more" numbers, on purpose:** new courses (and their credits) versus
  *extra credits to graduate*. The second is often smaller, because the 31-credit degree
  already leaves room for electives that a new program's courses can fill.
- **Choices are made across programs, fewest options first, one course at a time.** A pick
  brings its prerequisites, so the next choice can reuse them. For the Data Science minor,
  ECON 385's prerequisite ECON 350 also fills the minor's Statistics slot. The Math major's
  300-level courses include the course the Math minor needs, so it counts twice. Stubs rank
  after curated courses, since their prerequisites are unknown.
- **Minor overlap rules (p. 27)** are warnings, not re-planning: "at least three courses
  outside the major" ("major area" is read as "not counted toward a declared major"), and
  "double minors need four that do not overlap".
- **`MINOR-DATA`** transcribed (pp. 194, 393), unverified.

Demo script (demo student, 4.5 credits a term):

| add | terms | new courses | extra credits to graduate | |
|---|---|---|---|---|
| Data Science minor | 3 → 3 | 3 | 0 | CSC 121/125 count twice |
| Math major | 3 → 3 | 5 | 0 | MATH 332 counts for the minor and the major |
| both | 3 → **4**, late | 8 | 3 | the comparison the proposal describes |
| CS minor | 3 → 3 | 0 | 0 | warning: no courses outside the major |

## Deliverable 4: done (2026-10-28)

`GET /api/students/{key}/progress` and the **`/progress`** page.

- **Overview:** credits on the record against the degree's 31 (completed, in progress,
  planned), a jump link per program with its state, and how many courses count toward more
  than one major or minor.
- **One card per declared program, then the degree:** requirement counts by state, the
  course slots still open, the credits that program's rules have placed, and the full
  requirement tree, grouped the way the catalog groups it (Core courses, Exploratory
  Foundations, Competencies and so on).
- **Shared courses:** a course that counts toward two declared programs gets a gold **×2**
  badge naming the other program (`SharedCourses` context in
  `components/RequirementAudit.tsx`). Counting toward the degree is expected, so it is left
  out of the badge.
- The demo student's CS major and Math minor share no course, so the badge does not appear
  for them. To show it, declare an overlapping pair (e.g. the CS major and the Data Science
  minor, which share CSC 121 and 125) on a record from `/record`.

## Added on request: a student's own record (2026-10-28)

So the author can track real progress against the engine, not only the fictional demo
student:

- **`/record`**: create a record, set standing, graduation term and declared programs, then
  add, change and remove courses. A course outside the loaded catalog (most non-CSC/MATH/ECON
  courses) is described inline (title, credits, areas, FYS/ES) and stored as a stub with
  `extra.added_by = "student"`, so it never appears on the graph.
- **Pinning an either-or course.** Migration 0004 adds `enrollment.area_choice`. For a course
  printed "X-or-Y", the student can fix the area. The engine then drops the course's other
  Foundations areas for that enrollment, leaving W/Q/S, ES and FYS alone. Left on "Auto", the
  engine chooses, and the page shows which area it chose.
- **Validation:** competence must be one the course is offered with, a pinned area must be one
  the course carries, and the same course can't be added twice in one term.
- **Privacy:** these records live only in the database. Nothing writes them back to the seed
  fixtures. The demo student stays fictional.
- `/audit` takes `?student=`, and both pages remember the last record used.

## Scope decisions (need an answer before building)

### 1. Where `attribute_count` comes from: recommend **the B.A. degree requirements as a program**

No major or minor in the catalog uses an attribute rule. CSC, MATH and ECON are written
entirely as named courses, sets, and counts. Attribute rules live in the **university
graduation requirements** (catalog pp. 15–23), which the proposal's Data section already
promises ("the three distribution areas, the W, Q, and S competence requirements, the language
requirement, Power, Privilege and Diversity, and Extended Studies … exercises every
requirement rule type").

Recommendation: add `DEGREE-BA` to `programs_2025_26.json` with `kind: "degree"`:

| requirement | rule |
|---|---|
| 31 credits | `credit_minimum`, `credits: 31` |
| First-Year Seminar | `attribute_count`, `n: 1`, `attribute: "FYS"` |
| Arts & Humanities / Science & Math / Social Science: 2 each, all six from different subjects | `attribute_count`, `n: 2`, `distinct_subjects: true`, one per area |
| Language (LA) 2, Global Learning (GL) 1, PPD 1 | `attribute_count` |
| W, Q, S competence | `attribute_count`, `n: 1` each |
| Extended Studies: 2 experiences | `attribute_count`, `n: 2`, `attribute: "ES"` |

Item 1 is then demonstrated on the **CS major plus the degree requirements** side by side.
The talk should say that plainly: the major itself has three of the four rule types (see
decision 2), and the fourth exists only at the degree level.

This needs:

- **Migration 0003:** `enrollment.competence` (nullable, `W`/`Q`/`S`), and `degree` allowed in
  `program.kind`.
- **A fuller demo transcript.** A junior with only CSC/MATH/ECON courses has about 11 credits,
  where a real one has about 20, and every non-STEM area reads as outstanding. Add about 8
  **stub** courses from other subjects (an FYS, an AH course, a language pair, and so on),
  with distribution and attribute tags transcribed from the catalog. These are stubs, not
  curated departments. The record stays fictional.

*Alternative:* skip `DEGREE-BA` and say the engine "implements three rule types". That's
honest, but it walks back the proposal and leaves the credit bound in decision 3 with
nothing to bind on.

### 2. Program fixture additions: recommend **300/400 counts on existing programs + Data Science minor + ECON major/minor**

- **Add the catalog's "Number 300 & 400 Level Courses" line** to each program as
  `credit_minimum` with `scope: "program"`, `min_number: 300`. For the CS major that's "Four
  including CSC 498". It's already printed for every program and currently dropped, and it
  gives the CS major its third rule type.
- **`MINOR-DATA`** (Data Science, catalog p. 194): five courses, each written as alternatives
  ("MATH 141 or PSY 214 or ECON 350 or BIO 375", "MATH 261 or CSC 370 or CSC 380", …, CSC 121,
  CSC 125). It's the **recommended explorer demo**: it overlaps a CS major on CSC 121/125,
  it's built from alternative groups, and every course it names is already loaded or a
  stub.
- **`MAJOR-MATH`** as the second explorer case: "adding a second major vs. adding a minor",
  which the proposal's explorer description uses as its example. It already exists.
- **`MAJOR-ECON` / `MINOR-ECON`** (p. 205, 208): cheap now that ECON is loaded, and they make
  the program list look like a catalog rather than a demo.

As with the CP2 program fixture, everything Claude transcribes is marked **unverified** in
`provenance` until it has been checked against the PDF.

### 3. "Now" and the per-term load: recommend **derive the current term from the record; max load 4.5**

- **Current term** = the term of the student's in-progress enrollments (the demo student:
  2025FA). Terms left = fall and spring terms after it, through `expected_graduation`
  (2026SP, 2026FA, 2027SP = **3**). The demo record is a year behind the real calendar.
  That's harmless as long as nothing reads the system clock. A `current_term` setting
  can override it later.
- **Max load:** the catalog caps a semester at **4.5 credits** ("a maximum of 4.5 course
  credits per semester", p. 606), with 4.0 as the normal load ("may vary from three to four
  and one-half", p. 619). The proposal asks for the maximum.
  Use 4.5 as the default and take `max_load` as a query parameter, so the talk can show the
  bound moving at 4.0.

### 4. Cross-program rules: recommend **report them as warnings, don't re-allocate**

The catalog has two overlap rules (p. 27): "Double minors must have at least four courses that
do not overlap", and "At least three courses in the minor must be outside the student's major
area." Check both after the independent audits and attach a warning to the program that
breaks one. "Major area" is read as "not counted toward a declared major". Note that
interpretation in the response and in the talk, and keep it out of the allocation.

## Minimum semesters

`services/semesters.py`, reusing `Orderer` and the engine.

1. **What is left.** For each audited program, every outstanding slot and every slot filled
   only by a *planned* course is remaining work. For a short `n_from_set`, choose from its
   `options`. Prefer a course that is already remaining for another program (it counts twice),
   then one that needs no consent, then the earliest round, then the course id. Report the
   choices, the same way `Orderer` reports `assumed`.
2. **Chain bound.** Make `Orderer` student-relative: a course on the record (completed or in
   progress) is placed at round 0, and standing waits count from the student's current
   standing (a junior reaches senior standing 2 terms out, not 6). The chain bound is the
   highest round among the remaining courses, and the chain itself is read back through
   `needs`.
3. **Credit bound.** Remaining credits = the larger of (credits of the remaining named
   courses) and (31 − credits on record), since the named courses count toward the 31. Bound
   = ⌈remaining ÷ `max_load`⌉.
4. **Report** both bounds, which one binds, the chain as a course list, terms left, and
   `feasible = estimate ≤ terms_left`.

For the demo student, the chain is short: CSC 498 needs senior standing, which is about 2
terms out. The credit bound decides the answer. Without decision 1 there is no 31-credit
floor, the credit bound is tiny, and the chain always wins. The demo then can't show "the
greater of the two" switching sides. This is the strongest argument for `DEGREE-BA`.

Rehearse a case for each side. Adding `MAJOR-MATH` should make the chain bind (MATH 495
needs senior standing, and four 300-level MATH courses have their own chains). The base case
should be credit-bound.

## API surface (additions)

| method | path | purpose |
|---|---|---|
| `GET` | `/api/students/{key}/progress` | audits of every declared program + `DEGREE-BA`, `overlaps`, warnings, deliverable 4 |
| `GET` | `/api/students/{key}/explore?add=MINOR-DATA&add=…&max_load=4.5` | baseline vs. with the additions: per-program audit, newly remaining courses, overlap, additional credits, both semester bounds, feasibility, deliverables 2–3 |
| `GET` | `/api/students/{key}/audit/{program_id}` | one program's audit tree, deliverable 1 (also reachable from `/docs`) |

The explorer takes **several** `add` values, because the proposal's explorer compares "a
second major against two minors". The UI starts with one.

## Frontend

- **`/progress`**: one card per declared program plus the degree card. Requirement groups
  are collapsible, and each row shows state (fill, border and icon, never colour alone, same
  rule as the graph), the courses applied, and `have/need`. A course counted toward two
  programs gets a "×2" badge naming the other program. Credit totals go in each card header.
- **`/explore`**: the two-panel layout from the proposal's UI section. On the left, a
  searchable program list with declared programs marked. On the right, the impact analysis
  with the **headline first**: "+N semesters · graduates on time ✓/✗". Under it, both bounds
  side by side with the binding one highlighted and the chain drawn as a short course path,
  then satisfied/outstanding requirements, the overlap list and additional credits.
- Graph side panel: a "counts toward" line using the progress endpoint (optional).
- `AppShell` nav gains Progress and Explore. "Checkpoint 2" labels become "Checkpoint 3".

## Build order

| # | Task | Hours |
|---|---|---|
| ✓ | Requirement engine + 20 tests | done |
| 1 | Decisions 1–2: transcribe `DEGREE-BA`, `MINOR-DATA`, ECON programs, 300/400 counts; stub courses; verify against the PDF | 4–6 |
| 2 | Migration 0003 (`enrollment.competence`, `degree` kind); seed changes; demo transcript fill-out | 2–3 |
| 3 | Student-relative `Orderer`, remaining-course selection, `semesters.py` + tests | 4–5 |
| 4 | Cross-program warnings + tests | 1 |
| 5 | `/progress`, `/explore`, `/audit` endpoints | 3 |
| 6 | Frontend: `/progress` | 3–4 |
| 7 | Frontend: `/explore` | 4–5 |
| 8 | Rehearse: credit-bound and chain-bound cases; hand-check one audit against the catalog; record fallback capture | 2 |
|   | **Total remaining** | **23–29** |

**If the week runs short, cut in this order:** ECON programs, then cross-program warnings,
then the graph "counts toward" line, then several `add` values (keep one), then
collapsible groups. Do **not** cut `DEGREE-BA` or the student-relative chain bound. The first
is what makes "the greater of the two" demonstrable. Without the second, the chain bound
counts courses the student already has.

## Risks

- **Transcribing graduation requirements.** Distribution and competence tags exist only for
  the loaded departments, and ECON courses carry no competence variants in the fixture. Check
  the ECON fixture's tags against the PDF while transcribing (it's still marked unverified
  from CP2).
- **The `any_of` combination count.** Data Science has four alternative groups; a program
  with 10+ would blow up the product. Assert a ceiling (say 4,096 combinations) and fail
  loudly rather than slow down quietly.
- **Optimistic estimates.** The semester estimate assumes every course is offered every
  term. That's already listed as a future enhancement (term offering patterns); say so on
  the slide next to the number.
- **Validating against a real transcript.** The proposal promises to check the engine against
  the author's own advising transcript. Do that locally and keep it out of the repository:
  the seeded student stays fictional.

## Verification

From a clean clone, `docker compose down -v && docker compose up --build`:

1. `pytest`: the requirement tests pass, including `test_allocation_is_a_matching_not_greedy`,
   the `any_of` tests, and `test_course_counts_toward_two_programs`.
2. `GET /api/students/demo/audit/MAJOR-CSC` shows satisfied and outstanding requirements;
   `…/audit/DEGREE-BA` shows the counting rules. Together they cover all four rule types.
3. `/progress`: two declared programs plus the degree, grouped, with state per requirement
   and the ×2 badge on any shared course.
4. `/explore` → add Data Science: remaining courses, overlap (CSC 121, CSC 125), additional
   credits, and the headline semester count.
5. Same page, both bounds shown with the greater one reported; switch `max_load` to 4.0 or
   add `MAJOR-MATH` and watch which bound binds change.
