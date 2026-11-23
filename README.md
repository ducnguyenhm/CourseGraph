# CourseGraph

Interactive prerequisite graph and multi-major degree planner for the DePauw
catalog. Senior project, CSC 498S.

Design for the current checkpoint: [`docs/checkpoint-4-design.md`](docs/checkpoint-4-design.md)
(previous: [`docs/checkpoint-3-design.md`](docs/checkpoint-3-design.md),
[`docs/checkpoint-2-design.md`](docs/checkpoint-2-design.md),
[`docs/checkpoint-1-design.md`](docs/checkpoint-1-design.md)).

## Running

```sh
docker compose up --build
```

That brings up PostgreSQL 16, the FastAPI backend, and the Next.js client. The
backend waits for the database healthcheck, applies migrations, and seeds the
catalog if it is empty.

| what | where |
|---|---|
| Client | http://localhost:3000 |
| Prerequisite graph | http://localhost:3000/graph |
| API docs (generated) | http://localhost:8000/docs |
| Health | http://localhost:8000/health |

Checkpoint 2 endpoints (all also in `/docs`):

| endpoint | what it shows |
|---|---|
| `GET /api/graph?student=demo` | every course with the demo student's status: completed, planned, eligible, locked |
| `GET /api/graph?subject=CSC&subject=ECON` | department filter; depth still comes from the whole catalog |
| `GET /api/graph?program=MAJOR-CSC` | a program's courses and everything leading to them |
| `GET /api/graph/chain/CSC-340` | what must come first (required vs one-of-a-choice) and what it opens up |
| `GET /api/programs/MAJOR-CSC/order` | topological order in terms, with the branch choices it assumed |
| `GET /api/students/demo` | the fictional demo student's transcript, plan and programs |

Checkpoint 3 so far:

| endpoint / page | what it shows |
|---|---|
| `GET /api/students/demo/audit/MAJOR-CSC` | the requirement engine on the CS major: every requirement complete, in progress, planned or outstanding, with the courses meeting it |
| `GET /api/students/demo/audit/DEGREE-BA` | the B.A. graduation requirements: credit and attribute counts, Exploratory Foundations |
| http://localhost:3000/audit | the same, as a page, for any program, for the logged-in student |
| `GET /api/students/demo/semesters?max_load=4.5&add=MAJOR-MATH` | minimum terms left: the prerequisite-chain bound, the credit bound, the greater of the two, and whether that fits before graduation |
| `GET /api/students/demo/explore?add=MINOR-DATA` | the explorer: what adding programs would cost (requirements already met, courses counting twice, new courses and credits, change in minimum terms) |
| http://localhost:3000/explore | the same, as the two-panel explorer page |
| `GET /api/students/demo/progress` | every declared program plus the degree, with credit totals and the courses counting toward more than one program |
| http://localhost:3000/progress | the degree progress view |
| http://localhost:3000/record | your own course record: add, correct and remove courses; set your start and graduation terms and programs (advisors see it read-only) |
| http://localhost:3000/signup | create a student account with an empty record, and pick an advisor |

Checkpoint 4:

| endpoint / page | what it shows |
|---|---|
| http://localhost:3000 | landing page; **Try the demo** plans for the fictional demo student without an account |
| http://localhost:3000/planner | the semester planner: drag courses into terms, rejections name the unmet prerequisite, overload warnings, overrides with a note |
| http://localhost:3000/login | demonstration logins: `advisor` / `advisor-demo`, `demo` / `student-demo`, `demo-2` / `student-demo` |
| http://localhost:3000/advisees | the advisor dashboard (log in as `advisor`) |
| `GET /api/students/demo/plan?max_load=4.5` | the plan in term columns, every placement checked, loads, overloaded terms, courses still needed |
| `PUT /api/students/demo/plan/CSC-498` `{"term": "2026SP"}` | place or move a course; 409 with the check when a prerequisite is unmet, unless `override` gives a note |
| `POST /api/demo/session` | a demo session: send its token as `X-Demo-Session`; nothing under it is saved |
| `POST /api/auth/login`, `GET /api/advisor/advisees` | logins and the dashboard |
| `DELETE/PUT /api/students/{key}/plan/terms/{term}` | take an empty future term out of the plan, or put it back |
| `GET/POST /api/students/{key}/comments`, `POST /api/comments/{id}/replies`, `POST /api/comments/{id}/resolve` | conversations between a student and their advisor on a plan or a placement |

Every page shows one student, chosen by the login: a student sees only their own record, an
advisor only their advisees (opened from `/advisees`), and a demo session the demo student.
Without a login, the pages ask you to log in or try the demo; the catalog graph stays open.
The API enforces the same rule (`check_view`): a student's record answers 401 without a login
and 403 to anyone else, except the fictional `demo` student, which is public for demo mode.
Writes to a record need the student's own login; writes to a plan, the student's login or a
demo session. Records created on `/record` or by signing up live only in the database, never in
`backend/data/`, and are lost by `docker compose down -v`. The demo logins' records can be
changed freely; `docker compose exec backend python -m scripts.seed` puts `demo` and `demo-2`
back as they were. Set `SECRET_KEY` before the app is reachable
by anyone else; the default only suits a local Docker Compose stack.

Postgres is deliberately not published to a host port — reach it with
`docker compose exec db psql -U coursegraph -d coursegraph`. Publishing it only
invites a port collision on whatever machine the project is demonstrated from.

## Why prerequisites are expression trees

A flat list of prerequisite edges cannot represent disjunction. In the scraped
catalog this project started from, these two courses are indistinguishable:

| course | catalog text | flat list |
|---|---|---|
| CSC 322 | CSC 231 **and** CSC 235. | `['CSC 231', 'CSC 235']` |
| CSC 340 | Either CSC 231 **or** CSC 235. | `['CSC 231', 'CSC 235']` |

Same data, opposite meaning. Prerequisites are therefore stored as boolean
expression trees in a JSONB column, and the displayed graph is a *projection* of
those trees, with alternative-group edges drawn differently from required ones.

```sh
docker compose exec db psql -U coursegraph -d coursegraph -c \
  "SELECT c.course_id, jsonb_pretty(cv.prereq_expr)
     FROM course_version cv JOIN course c ON c.id = cv.course_id
    WHERE c.course_id IN ('CSC-322','CSC-340') ORDER BY c.course_id;"
```

## Catalog data

`backend/data/` holds curated fixtures for the 2025-26 catalog:
`csc_catalog_2025_26.json` (29 courses), `math_catalog_2025_26.json`
(35 courses + 5 out-of-scope stubs) and `econ_catalog_2025_26.json`
(36 courses + 1 stub) — 100 courses across three departments. The ECON file
was transcribed for Checkpoint 2 and is marked in its `provenance` field as
not yet verified line by line. Prerequisites are already expression
trees; the CSC file's `conventions` block is the reference for the node
vocabulary.

Each fixture declares its own `catalog_year`, and that is what the loader
files it under — never a server default. Loading fixtures that disagree on the
year is refused, so a 2026-27 catalog can be added alongside this one without
either overwriting the other.

The CSC and MATH data was verified line by line against
`depauw-university-2025-2026-catalog.pdf`. These prerequisite sentences are
genuinely ambiguous **in the catalog itself** and are flagged in the fixtures'
`notes` for departmental confirmation:

- MATH 331 — "ECON 100 and MATH 136 or MATH 151 or ECON 375"
- MATH 367 — "MATH 270 and CSC 121 or permission of instructor"
- ECON 420 — "ECON 294 and ECON 295 or permission of instructor"
- ECON 450 — "ECON 350, MATH 141, MATH 240, MATH 247 or permission of
  instructor. MATH 151 or the equivalent." (MATH 240 appears nowhere else in
  the catalog and is kept as a stub)

MATH 341 cites BIO 275 and MATH 348 cites BIO 375 for what appears to be the
same slot; both are recorded as written.

Ingestion refuses to load a fixture set with unresolvable prerequisite
references or a prerequisite cycle, so bad data fails loudly at seed time
rather than silently producing wrong answers later:

```sh
docker compose exec backend python -m scripts.seed
```

`--check` runs the same validation without ever opening a database session,
which is how the deliberately corrupted fixtures in `backend/data/corrupt/` are
demonstrated against a live stack:

```sh
docker compose exec backend python -m scripts.seed --check \
  data/corrupt/csc_cycle_via_renumber.json \
  data/math_catalog_2025_26.json data/econ_catalog_2025_26.json
# refusing to load:
# 1 problem(s) found:
#   prerequisite cycle: CSC-235 -> CSC-236 (cited as CSC-233) -> CSC-235
```

Each corrupted file carries a `corruption` note saying what was changed.
`csc_or_loop.json` is the control case: its loop runs only through an "or"
branch, so it is accepted.

### Renumbering

The catalog renumbered the CS core, and MATH 323 still cites the old
`CSC-233`, and prints "formerly CSC 122 / 232 / 233" against the new numbers.
Rather than rewrite the curated text, retired ids keep an identity
row and `course_equivalence` maps them forward, so the graph draws the edge
from `CSC-236` and labels it `via CSC-233`.

| from | to | relation |
|---|---|---|
| CSC-122 | CSC-235 | renumber |
| CSC-232 | CSC-125 | renumber |
| CSC-233 | CSC-236 | renumber |
| MATH-136 | MATH-151 | satisfies (additive) |

This matters beyond the graph: a transcript predating the renumbering is in old
numbers, so evaluating it against this catalog goes through the same table.

## Tests

```sh
docker compose exec backend pytest -q
```
