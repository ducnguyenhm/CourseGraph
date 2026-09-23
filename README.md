# CourseGraph

Interactive prerequisite graph and multi-major degree planner for the DePauw
catalog. Senior project, CSC 498S.

Design for the current checkpoint: [`docs/checkpoint-1-design.md`](docs/checkpoint-1-design.md).

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

`backend/data/` holds hand-curated fixtures for the 2025-26 catalog:
`csc_catalog_2025_26.json` (29 courses) and `math_catalog_2025_26.json`
(35 courses + 10 out-of-scope stubs). Prerequisites are already expression
trees; the CSC file's `conventions` block is the reference for the node
vocabulary.

Each fixture declares its own `catalog_year`, and that is what the loader
files it under — never a server default. Loading fixtures that disagree on the
year is refused, so a 2026-27 catalog can be added alongside this one without
either overwriting the other.

The data was verified line by line against `depauw-university-2025-2026-catalog.pdf`.
Two prerequisite sentences remain genuinely ambiguous **in the catalog itself**
and are flagged in the fixtures' `notes` for departmental confirmation:

- MATH 331 — "ECON 100 and MATH 136 or MATH 151 or ECON 375"
- MATH 367 — "MATH 270 and CSC 121 or permission of instructor"

MATH 341 cites BIO 275 and MATH 348 cites BIO 375 for what appears to be the
same slot; both are recorded as written.

Ingestion refuses to load a fixture set with unresolvable prerequisite
references or a prerequisite cycle, so bad data fails loudly at seed time
rather than silently producing wrong answers later:

```sh
docker compose exec backend python -m scripts.seed
```

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
