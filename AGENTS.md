# AGENTS.md

Read `CLAUDE.md` first. It is the canonical guide to this repo (layout, commands,
conventions, data rules, git rules), and everything in it applies to Codex too.
This file adds how agents check their own work and track it.

## Verify before you report a change as done

- **Backend:** `cd backend && python3 -m pytest -q`. Add or update the `test_<service>.py`
  next to any service you change.
- **Frontend type-check:** `docker compose exec -T frontend npx --no-install tsc --noEmit -p .`
- **Frontend behaviour:** with `docker compose up` running, use the Playwright MCP tools:
  1. Open http://localhost:3000/login and log in as `demo` / `student-demo`
     (`advisor` / `advisor-demo` for advisor pages).
  2. Open the page you changed and do the thing the change is for (drag a course in
     `/planner`, add a program in `/explore`, and so on).
  3. Check it at 390px wide as well as desktop width; below md the graph is a list.
  4. Read the browser console and report any errors.
  5. Say what you checked and what you saw. "It compiles" is not verification.
- Never log in as, or change, any student other than `demo` and `demo-2`; other rows are real records.

## Linear

When a task comes from a Linear issue, mention its id (e.g. `CG-12`) in the branch
work and commit message, move it to In Progress when you start, and leave a comment
with what you verified when you finish. Don't create or close issues unless asked.
