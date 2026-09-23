# CourseGraph — Checkpoint 1 Design

## Context

Checkpoint #1 is due **September 21–25, 2026** (this week), budgeted at 20–30 hours in the
proposal. It is the foundation checkpoint: no product features, but every later checkpoint
builds on the schema and the prerequisite representation chosen here. Getting the expression
tree format and the versioned catalog schema right now is what prevents rework at
Checkpoints 2–4.

The proposal commits to five demonstrable items:

1. `docker compose up` brings up Next.js + FastAPI + PostgreSQL together; health endpoint
   confirms the DB connection.
2. Schema created in PostgreSQL; live SQL returning course rows with prerequisite
   expression trees stored as JSONB.
3. ~40 curated courses loaded, including **≥3 with an alternative group** and **≥1 requiring
   instructor consent**; stored tree shown beside the original catalog text.
4. A REST endpoint returning a course and its prerequisite tree, called live from the browser.
5. A deliberately unstyled prerequisite graph rendered in the browser from live API data.

Nothing else. No auth, no student records, no requirement engine, no layout algorithm —
those are Checkpoints 2–4.

## Starting state

Curated fixtures (`backend/data/csc_catalog_2025_26.json`,
`math_catalog_2025_26.json`) are the source of truth. They publish
prerequisites already in expression-tree form, and the CSC file's `conventions`
block defines the node vocabulary the backend implements.

The earlier scrape at `/Users/ducnguyen/coursegraph-seed-data/` is retained only
as a cross-check. It is not loadable: `and` and `or` both collapse to the same
flat list, CSC 125/233/235/236 are missing entirely, 738/1183 prerequisite
strings are the literal word `"Credits"`, and MATH 348 silently drops MATH 141.

Two things the curated data forced into the Checkpoint 1 schema that the
original plan deferred:

- **`course_equivalence` is no longer optional.** The 2025-26 catalog renumbered
  the CS core (CSC-122→235, CSC-232→125, CSC-233→236) and MATH-323 still cites
  the retired `CSC-233`. Without equivalence resolution that reference dangles
  and ingestion rejects the catalog.
- **Two new node types.** `course_level` (CSC-498 needs one CSC course numbered
  300+) and `program` (MATH-495 is senior Math majors only). Neither appears in
  the proposal's original list.

One semantic change worth carrying into Checkpoint 3: the fixtures define
`consent` as evaluating to **UNKNOWN**, not false. The proposal said consent
"always evaluates to false automatically." Three-valued logic means a plan
needing instructor consent gets *flagged for confirmation* rather than rejected
outright, which is the better behaviour but a different evaluator.

## Scope decision

**RESOLVED.** Hand-curated fixtures arrived for both subjects, so Checkpoint 1
loads CSC **and** MATH: 64 real courses plus 10 out-of-scope stubs (ECON, PSY,
BIO, BUSA, FIN) that exist only so cross-subject references resolve. Loading
both was not optional — CSC-380 requires MATH-141, and MATH-323 requires a CSC
course — and it clears both checkpoint bars with room to spare.

| bar | required | actual |
|---|---|---|
| courses | ~40 | 74 rows (64 real) |
| alternative-group courses | ≥3 | 18 |
| instructor-consent courses | ≥1 | 9 |

The earlier worry that CSC alone yields only 2 alternative groups was correct;
MATH is what resolves it.

## Architecture

Three containers, one network. Next.js talks to FastAPI over JSON REST; FastAPI owns the only
database connection.

```
browser ──> next.js (3000) ──> fastapi (8000) ──> postgres 16 (5432)
```

Backend is organised into the four services the proposal names, but only two exist at
Checkpoint 1: **catalog ingestion** (seed + validation) and **graph** (projection). Requirement
evaluation and scheduling are stubs-not-written until Checkpoints 3–4.

## Repository layout

New repo `coursegraph/` (private GitHub, per proposal).

```
docker-compose.yml
.env.example
README.md
docs/
  checkpoint-1-design.md   # this document, moved here and committed
backend/
  Dockerfile
  pyproject.toml
  alembic.ini
  alembic/versions/
  app/
    main.py            # FastAPI app, CORS, router mounting
    config.py          # pydantic-settings, reads env
    db.py              # engine, session dependency
    models/catalog.py  # SQLAlchemy: CatalogYear, Course, CourseVersion
    schemas/prereq.py  # Pydantic discriminated union for the expression tree
    schemas/course.py  # response models
    api/health.py
    api/courses.py
    api/graph.py
    services/projection.py   # tree -> nodes/edges
    services/validation.py   # dangling refs, cycles
  data/csc_2026_2027.json    # the curated fixture (committed)
  scripts/seed.py
  tests/
frontend/
  Dockerfile
  package.json
  app/layout.tsx
  app/graph/page.tsx         # React Flow canvas
  app/courses/[code]/page.tsx# tree beside raw text
  lib/api.ts
```

## Database schema

The central decision from the proposal: **course identity is separate from year-specific
definition**, and catalog data is append-only.

| table | columns |
|---|---|
| `catalog_year` | `id PK`, `label UNIQUE` (`'2025-2026'`), `starts_on`, `published_at NULL` |
| `course` | `id PK`, `subject`, `number`, `code UNIQUE` (`'CSC 340'`) — identity only, no title |
| `course_version` | `id PK`, `course_id FK`, `catalog_year_id FK`, `title`, `credits NUMERIC(3,2) NULL`, `credits_raw TEXT`, `description TEXT`, `prereq_raw TEXT`, `prereq_expr JSONB NOT NULL`, `attributes JSONB NOT NULL DEFAULT '[]'`, `UNIQUE(course_id, catalog_year_id)` |

Notes:

- `credits` is nullable with `credits_raw` alongside it because 60 scraped courses are
  `"variable"` and 3 are `0.5`. Do not force variable-credit courses into a number.
- `prereq_expr` is `NOT NULL`; a course with no prerequisite stores `{"type":"none"}` rather
  than SQL `NULL`, so the evaluator never branches on nullness.
- `attributes` is a JSONB array (`["SM","Q"]`), ready for the distribution/competence
  requirements at Checkpoint 3 even though CSC populates it sparsely.
- Index `course_version(catalog_year_id, course_id)` and a GIN index on `prereq_expr` —
  the GIN index is not needed at this scale but makes a good talking point and costs one line.

**Deferred to later checkpoints** (do not create yet): `program`, `program_version`,
`requirement`, `student`, `enrollment`, `plan`, `plan_item`, `advisor`, `comment`.
`course_equivalence` is optional — add it only if the renumbering mapping surfaces during
curation and there is time.

**Use Alembic from the first commit.** The schema grows every checkpoint, and retrofitting
migrations once seed data exists is painful. One initial migration, ~1 hour, and the migration
run becomes part of the `docker compose up` demo.

## Prerequisite expression tree

Stored in `prereq_expr` JSONB. Modelled in Pydantic as a discriminated union on `type`
(Pydantic v2 `Field(discriminator="type")`), which gives validation and OpenAPI docs for free.

```jsonc
{"type": "none"}
{"type": "course",  "code": "CSC 231", "min_grade": "C-"}   // min_grade optional
{"type": "and",     "children": [ ... ]}
{"type": "or",      "children": [ ... ]}
{"type": "consent", "of": "instructor"}    // always evaluates false; override-only
{"type": "standing","level": "sophomore"}
{"type": "placement","test": "MATH", "min_score": 4}
{"type": "coreq",   "code": "CSC 121"}     // may be taken in the same term
```

Worked examples, straight from the two courses that expose the flat-list bug:

```jsonc
// CSC 322 — "CSC 231 and CSC 235."
{"type":"and","children":[{"type":"course","code":"CSC 231"},
                          {"type":"course","code":"CSC 235"}]}

// CSC 340 — "Either CSC 231 or CSC 235."
{"type":"or", "children":[{"type":"course","code":"CSC 231"},
                          {"type":"course","code":"CSC 235"}]}

// CSC 428 — "CSC 231 and CSC 236, or consent of instructor."  (pending real text)
{"type":"or","children":[
   {"type":"and","children":[{"type":"course","code":"CSC 231"},
                             {"type":"course","code":"CSC 236"}]},
   {"type":"consent","of":"instructor"}]}
```

`and`/`or` take `children` (2+), not a fixed pair, so `A and B and C` stays one flat node.

Evaluation against a completed-course set is a recursive walk, linear in tree size — but the
evaluator itself is **Checkpoint 3 work**. Checkpoint 1 only needs to *store, validate, return,
and project* the tree.

## Graph projection

`services/projection.py` turns trees into the node/edge list React Flow consumes. The proposal
requires alternative-group edges to be visually distinguishable from strictly required ones.

DFS each course's tree carrying a flag for whether the current position sits under any `or`
node, plus a group id minted at each `or`:

- Course leaf reached through `and` nodes only → edge `kind: "required"`, `group: null`.
- Course leaf reached under any `or` → edge `kind: "alternative"`, `group: "<or-node-id>"`,
  so the UI can bracket siblings that are alternatives to each other.
- `consent` / `standing` / `placement` leaves produce **no edge** — they are node badges, not
  graph edges. Return them on the node so the UI can mark the course.
- `coreq` leaves produce an edge with `kind: "coreq"`.

Edge direction is prerequisite → dependent course, so the DAG flows in the direction a student
progresses.

## API surface

Four endpoints. No auth — authentication is Checkpoint 4.

| method | path | purpose |
|---|---|---|
| `GET` | `/health` | `{status, database: "connected", catalog_year}` — deliverable 1 |
| `GET` | `/api/courses?subject=CSC&catalog_year=2025-2026` | list: code, title, credits |
| `GET` | `/api/courses/{code}` | full course incl. **both** `prereq_expr` and `prereq_raw` — deliverables 3 + 4 |
| `GET` | `/api/graph?subject=CSC&catalog_year=2025-2026` | `{nodes:[...], edges:[...]}` — deliverable 5 |

`GET /api/courses/{code}` returning the tree and the original text in the same payload is what
makes the "tree beside catalog text" demo a single request rather than a manual comparison.

`/health` must actually execute `SELECT 1` against the database — not just return 200 — since
the deliverable is specifically a *confirmed database connection*.

FastAPI's generated `/docs` is itself a demo artifact and is referenced again in the final
report.

## Frontend

Deliberately unstyled, per the proposal. Tailwind is installed but barely used this week.

- `/graph` — React Flow canvas fed by `/api/graph`. Required-edge vs alternative-edge styling
  is the one visual distinction worth making now (solid vs dashed); everything else stays
  default.
- `/courses/[code]` — the tree rendered as an indented list beside `prereq_raw` verbatim.

Two React Flow pitfalls that account for most "nothing renders" reports:

1. The component must be a client component (`'use client'`) — App Router defaults to server.
2. The container needs an **explicit height** (e.g. `style={{width:'100%', height:'100vh'}}`).
   A parent with no height renders an empty canvas with no error.

Node placement: a deterministic grid keyed on course number. **Do not build a layered layout
this week** — that is a named Checkpoint 2 deliverable.

## Docker Compose

```yaml
services:
  db:        # postgres:16, named volume, healthcheck: pg_isready
  backend:   # depends_on: db (condition: service_healthy)
  frontend:  # depends_on: backend
```

Three details that decide whether the one-command demo works:

- **Healthcheck gating.** `depends_on: {db: {condition: service_healthy}}` with a `pg_isready`
  healthcheck. Without it the backend races Postgres and exits on first boot — the single most
  common cause of a failed `docker compose up` demo.
- **Browser-side API URL.** Frontend JS runs in the *browser*, not the container, so it must
  call `http://localhost:8000`, **not** `http://backend:8000`. Set
  `NEXT_PUBLIC_API_URL=http://localhost:8000`. The service-name URL only works for
  server-side fetches.
- **Entrypoint does migrate + seed.** Backend entrypoint runs `alembic upgrade head` then
  `python -m scripts.seed --if-empty`. This is what makes deliverable 1 literally one command.

Enable CORS on FastAPI for `http://localhost:3000`.

## Data pipeline

`backend/data/csc_2026_2027.json`, committed to git, one object per course:

```jsonc
{
  "code": "CSC 340",
  "title": "Web Programming and Cybersecurity",
  "credits": 1,
  "credits_raw": "1",
  "description": "...",
  "prereq_raw": "Either CSC 231 or CSC 235.",
  "prereq_expr": { "type": "or", "children": [ ... ] },
  "attributes": []
}
```

`scripts/seed.py` runs three validations before writing anything, and **fails loudly** rather
than importing bad data:

1. **Schema** — every tree parses against the Pydantic union.
2. **Referential** — every `course`/`coreq` leaf resolves to a course in the same catalog year.
   This is what catches the CSC 125/233/235/236 class of bug that made the scrape unusable.
3. **Acyclicity** — DFS over required edges; reject a catalog containing a prerequisite cycle.
   Cheap to write now (~15 lines) and the seed script needs it anyway; the *corrupted-fixture
   demo* of this is a Checkpoint 2 deliverable.

Seeding is idempotent: upsert `catalog_year` and `course`, insert `course_version` keyed on
`(course_id, catalog_year_id)`.

## Build order

Sequenced so the highest-risk item is proven first. The proposal itself flags React Flow as the
author's least-familiar component and commits to prototyping it before Checkpoint 1.

| # | Task | Hours |
|---|---|---|
| 1 | **React Flow spike** — throwaway page, hardcoded 5-node JSON, no backend | 2–3 |
| 2 | Repo skeleton, Dockerfiles, compose, `/health` hitting `SELECT 1`; commit this document to `docs/checkpoint-1-design.md` | 4–5 |
| 3 | SQLAlchemy models + initial Alembic migration | 3–4 |
| 4 | Pydantic prereq union + validation + projection + tests | 4–5 |
| 5 | Convert curated CSC list → `csc_2026_2027.json`; seed script | 4–6 |
| 6 | Three `/api` endpoints | 2–3 |
| 7 | Wire `/graph` and `/courses/[code]` to live API | 3–4 |
| 8 | Rehearse demo, record screen capture fallback | 2–3 |
|   | **Total** | **24–33** |

Step 1 before step 2 is deliberate: it de-risks the unfamiliar library against zero
infrastructure, so a React Flow surprise costs hours rather than the checkpoint.

Steps 2–4 do not depend on the curated data and can proceed while the list is still being
transcribed.

## Risks

- **Curation is the critical path.** Steps 5–7 are blocked on the CSC list. If it slips, seed
  from a partial list and load the rest incrementally — a 15-course graph still demos every
  deliverable.
- **CSC may miss the ≥3 alternative / ≥1 consent bars.** Mitigation is the MATH top-up above.
  Decide the moment the real text is in hand, not on demo day.
- **Docker on the demo machine.** The proposal's fallbacks already cover this: clone to a
  Room 260 machine, or a pre-built image on external storage, plus a screen capture recorded
  in advance.

## Verification

End-to-end, from a clean clone:

1. `docker compose up` — all three services reach healthy, migrations and seed run in the logs.
2. `curl localhost:8000/health` → `{"status":"ok","database":"connected","catalog_year":"2025-2026"}`.
3. `psql` into the container and run a live query returning `code, prereq_raw, prereq_expr` —
   shows the tree as native JSONB. *Demo beat:* select CSC 322 and CSC 340 side by side. The
   raw text differs by one word, the trees differ by `and` vs `or`, and the old flat
   representation collapsed both to the same list.
4. Browser → `localhost:8000/docs`, execute `GET /api/courses/CSC 340` live.
5. Browser → `localhost:3000/graph`, graph renders from live data; dashed edges mark
   alternative groups.
6. Browser → `localhost:3000/courses/CSC 428`, tree beside verbatim catalog text.
7. `pytest` — projection and validation tests pass.
8. Confirm the loaded set contains ≥3 alternative-group courses and ≥1 consent course; if not,
   apply the MATH top-up.
