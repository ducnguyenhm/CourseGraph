# CLAUDE.md

CourseGraph: an interactive prerequisite graph and multi-major degree planner for the DePauw
catalog. It is a senior project (CSC 498S) delivered in checkpoints. `README.md` covers
running the app, the endpoints and the catalog data. This file covers how to work in the repo.

## Layout

- `backend/`: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16 (JSONB for prerequisite trees)
  - `app/services/`: the logic, as pure Python with no database. Keep new logic here.
    - `evaluator.py`: three-valued prerequisite evaluation
    - `ordering.py`: topological rounds
    - `requirements.py`: the requirement engine
    - `semesters.py`: the minimum-semester estimate
    - `explore.py`: the program explorer
    - `planner.py`: the semester planner
    - `advising.py`, `demo.py`, `auth.py`: comment rules, demo sessions, logins
  - `app/api/`: thin FastAPI routers. `queries.py` loads database rows into what the services need.
    `auth.py` provides the `current_account`/`require_account` dependencies and `check_view`:
    a student's record is readable only by that student, their advisor, or anyone for the
    public `demo` student. Record writes need `owner` (that student, logged in); plan writes
    go through `plans._access`. `signup.py` creates a student account with its record.
  - `app/models/`, `app/schemas/`: ORM models and Pydantic schemas. `schemas/prereq.py` defines
    the prerequisite tree node types.
  - `alembic/versions/`: numbered migrations (`0001_…`, `0002_…`). Add a new one and never edit an old one.
  - `data/`: curated 2025-26 fixtures, loaded by `scripts/seed.py`.
  - `tests/`: pytest. `conftest.py` builds the demo student over the real fixtures.
- `frontend/`: Next.js 15 (App Router), React 19, TypeScript, Tailwind 4. The graph is custom
  SVG, not React Flow. Every API call goes through `lib/api.ts`, which adds the login token and,
  for the demo student, the demo-session token (`lib/session.ts`). Pages get their student from
  `useStudent()` (the login decides it); never add a student picker.
- `docs/checkpoint-N-design.md`: the design note for each checkpoint, covering scope, decisions
  and gaps. The checkpoint deliverables come from the Timeline section of the project proposal.

## Commands

```sh
docker compose up --build                       # db + backend :8000 + frontend :3000; migrates and seeds
cd backend && python3 -m pytest -q              # backend tests run on the host, no database needed
cd backend && python3 -m pytest -q -m "not cp4" # leave out the Checkpoint 4 tests
docker compose exec backend alembic upgrade head
docker compose exec backend python -m scripts.seed          # re-seed
docker compose exec backend python -m scripts.seed --check <fixtures…>  # validate only
docker compose exec -T frontend npx --no-install tsc --noEmit -p .      # frontend type-check
docker compose exec db psql -U coursegraph -d coursegraph
```

The host has no psycopg, so run anything that touches the database (seed, alembic) through
`docker compose exec backend`. Postgres has no host port, on purpose.

## Conventions

- **Course ids** are `SUBJECT-NUMBER` with the competence suffix stripped (`CSC 235Q` becomes `CSC-235`).
  `label()` turns them back into `CSC 235` for display.
- **Prerequisites are boolean trees**, never flat lists. The node types are
  `and/or/course/coreq/standing/course_level/consent/placement/program`.
  Consent and placement tests evaluate to UNKNOWN, never true or false.
- **Renumbered courses** resolve through `course_equivalence` with `validation.resolve()`.
  Don't rewrite curated text to use the new numbers.
- **Terms** are strings like `2026SP`. Estimates and standing count fall and spring only
  (`next_primary`, `term_index`, `terms_between`, `semesters_between`). The planner also has
  Winter Term and May Term (`PLAN_KINDS`, `next_plan_term`, ordered by `term_order`); those short
  terms take Extended Studies (`ES`) courses only, up to `SHORT_MAX_LOAD = 0.5`. A semester's
  maximum load is `MAX_LOAD = 4.5`.
- **Standing** is projected with `STANDING_ROUNDS` and `terms_elapsed`, the same way in
  `ordering.py`, `semesters.py` and `planner.py`. Keep those three consistent.
- **Comments and docstrings** explain why the code does something, often citing the catalog
  case behind it (CSC-340's "or", MATH-323's old id). Match that.
- **Tests** sit next to each service (`test_<service>.py`) and use small synthetic catalogs,
  plus a few checks on the real demo student. Checkpoint 4 tests carry the `cp4` marker; they
  were written before their code, as its contract.
- **Responsive:** pages work from 390px wide. Below md, `AppShell` shows a top nav strip and the
  graph swaps its SVG for a list. Status is never shown by colour alone.

## Data rules

- **Catalog fixtures** record catalog text as written. Put ambiguities and deviations in the
  fixture's `notes`, never fix them silently. Seeding refuses dangling references and cycles,
  so keep it that way.
- **Real student records** (signed-up accounts, `duc`/`duke` from before logins, or the
  user's own transcript) live only in the database. Never write them into `backend/data/`, the tests or a commit.
- **`docs/demo-db.sql`** belongs to the user and stays untracked.
- **Demo logins** in `data/demo_accounts.json` are public on purpose (printed on `/login`). The
  `demo` student and `demo-2` are fixture-owned and re-seeded freely; any other student row is
  a real record.

## Git

Work goes on a `checkpoint-N` branch. Commit or push only when asked.
