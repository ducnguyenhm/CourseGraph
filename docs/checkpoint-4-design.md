# CourseGraph — Checkpoint 4 Design

## Context

Checkpoint #4 is due **November 16–20, 2026**. It is the last checkpoint that adds features;
after it, the schedule holds only testing, usability sessions and the final report. The
proposal commits to five demonstrable items:

1. The **drag-and-drop semester planner**: a course dropped into a term that violates a
   prerequisite is rejected with a message **naming the unmet prerequisite**, then accepted in
   a valid term.
2. The **credit overload warning** for a term past the threshold, and the **override** that
   records a justified placement the system would otherwise reject.
3. The **public landing page** and a walkthrough in **demonstration mode without logging in**.
4. The **advisor dashboard**: log in as an advisor, see the advisee list, open a student's plan,
   comment on a specific course placement, then log in as that student and see the comment.
5. The **responsive layout** across desktop and tablet, with the **simplified graph
   alternative** at narrow breakpoints.

## How it was built: tests first

The service contracts were written as tests before any code (`tests/test_planner.py`,
`test_advising.py`, `test_demo_mode.py`, marker `cp4`), then implemented to them. As with
the evaluator and the requirement engine, the logic is pure Python with no database. The API
only loads rows and stores results.

| piece | where | tests |
|---|---|---|
| planner: placement checks, overload, override | `app/services/planner.py` | `test_planner.py` (45) |
| who may see, comment, reply, resolve | `app/services/advising.py` | `test_advising.py` (13) |
| demo sessions | `app/services/demo.py` | `test_demo_mode.py` (7) |
| passwords, login tokens | `app/services/auth.py` | `test_auth.py` (7) |

232 backend tests in total.

## 1. The planner

A placement is checked by the existing evaluator, run against the record **as it will stand by
the target term**. That means completed and in-progress courses, plus every course placed in an
**earlier** term. The same term doesn't count, except for a corequisite: the evaluator gained an
`alongside=` argument so that a corequisite is decided (met beside a course in the same term,
unmet otherwise) instead of being UNKNOWN. Standing is projected with the same
`STANDING_ROUNDS` rule the program order and the semester estimate use. Consent stays UNKNOWN:
the placement is accepted and listed under "to confirm".

The rejection message comes from the evaluator's own unmet list, so it names the course:
*"CSC 498 can't go in 2026SP. Still unmet by then: senior standing; 1 more CSC course(s)
numbered 300+."*

Moving or removing a course re-checks the whole plan (`review`), so a course whose prerequisite
was moved later shows up as a problem rather than silently staying "valid".

**Overload** is a warning, never a rejection: a term over `max_load` (default 4.5, the
catalog's maximum; configurable per request and in the page) is flagged on the column, in the
summary and on the advisor dashboard.

**Override** is a justification note stored on the placement (`plan_item.override_note`,
migration 0006). It covers prerequisites only. A past term, or a course already on the record,
is refused even with a note. An overridden placement counts for the courses after it, and
moving it clears the note, because the note justified that particular placement.

**Drag and drop** uses native HTML5 drag events (Chrome, Safari, iPadOS). Each card also has a
**tap-to-place** path, "Move…" and then "Place here", which serves touch screens and keyboards
too. While a course is dragged over a term, the column asks `POST …/plan/check` and shows the
verdict before the drop ("Needs ECON 220").

The tray offers the courses the semester estimate still counts on that the plan lacks, plus a
search over the whole catalog.

## 2. Logins

Logins are kept minimal on purpose. The project needs roles for the advisor walkthrough, not an
identity system. Passwords are hashed with scrypt, and a token is the account key and an expiry
signed with HMAC (standard library only, nothing new to install). Seeded accounts come from
`data/demo_accounts.json` (passwords public, printed on `/login`). Set `SECRET_KEY` anywhere
other people can reach the app.

**One student per login.** Every page shows the record the login decides (`useStudent`): a
student their own, a demo session the demo student, an advisor the advisee named in
`?student=` (opened from `/advisees`; the nav keeps it). A student's `?student=` is ignored,
and there is no student picker. Without a login the pages offer "Log in" and "Try the demo";
the catalog graph stays open, without statuses.

The API enforces the same rule (`auth.check_view`): reading a student's record, plan, audit,
estimate, explorer, progress or graph statuses needs that student's login or an advisor
assigned to them; anonymous requests get 401, everyone else 403, before any lookup, so a
refusal does not say whether the student exists. The fictional `demo` student is public, for
demo mode. Writes to a plan need one of:

- a logged-in student, on their own plan;
- a demo session, on its copy of the demo plan.

Advisors see an assigned advisee's plan read-only and comment on it.

**Records belong to their login** (2026-11-18, on request). `/record` is the logged-in
student's own record: add, change and remove courses taken or in progress, set name, standing,
start, current and graduation terms, and declared programs. A future course added there goes
through the planner (`PUT …/plan/{course}`), so it is checked like a drag. Every record write
needs that student's login (`auth.owner`); an advisor sees the whole record read-only
(dashboard → "Courses taken"), and a demo session sees the demo record read-only.

**Sign-up** (`/signup`, `POST /api/auth/signup`) creates a student account and an empty record
in one step, with an optional advisor from `GET /api/auth/advisors`; that assignment is what
puts the student on the advisor's dashboard. Only students sign up: an advisor who could create
themselves could claim any student. Re-seeding replaces only the fixture students' assignments,
so a signed-up student keeps their advisor. Records from the old `/record` (`duc`, `duke`) have
no account, so no page shows them.

The planner shows every term from the current one to graduation: fall, **Winter Term**, spring
and **May Term** (added 2026-11-18, on request; summer is on records but not planned). A May
Term course counts for the fall after it, and a fall course for the Winter Term after it
(`semesters.term_order`). Class standing still advances only with fall and spring
(`semesters_between`), so a short term does not make anyone a senior, and the minimum-semester
estimate counts fall and spring only.

Winter and May Term are **short terms**: they take only Extended Studies courses (catalog
attribute `ES`, e.g. CSC 184, ECON 183; catalog p. 23 places these in Winter or May Term), and
at most **0.5 credit** (`SHORT_MAX_LOAD`; those courses are "offered for .5 course credits or as
a co-curricular (0 credit)"). Unlike the fall/spring overload, both are refusals that no
override note excuses, since a regular course is not taught then. An Extended Studies course
may still go in a fall or spring (a semester away). The columns read "Extended Studies only ·
0 / 0.5 cr".
Moving graduation on `/record` changes the columns. A term added past graduation can be removed again
while it is empty.

**The whole degree** (2026-11-18, on request). The planner lays terms out one row per academic
year (fall through May Term, plus a summer when the record has one), from the year the student
started (`start_term`, else their earliest course; `semesters.past_terms`) through graduation.
Terms already gone through show the record's courses, Completed or In progress, read-only:
nothing is dropped into them, and the record is edited on `/record`.

**Removing terms** (2026-11-18, on request; migration 0008 adds `student.removed_terms`). Any
future term can be taken out of the plan once it is empty: a semester away, an internship, a
May Term skipped (`DELETE /api/students/{key}/plan/terms/{term}`; `PUT` puts it back). It keeps
its place in the year as "not taking courses · Add it back", and takes no course until put
back, from the planner or `/record` alike. A removed fall or spring is not counted as a term
left before graduation, so the estimate and the advisor's on time / at risk see it; standing
still projects as if the student were enrolled. A demo session keeps its removed terms in memory.

## 3. Demonstration mode

"Try the demo" on the landing page starts a session (`POST /api/demo/session`): a private,
in-memory copy of the demo student's plan, keyed by an unguessable token kept in the tab's
`sessionStorage`. Every planner call carries it as `X-Demo-Session`, and nothing under it is
written to the database. The session ends when the tab closes, on "End demo", or after two
idle hours. An expired session answers 410 and the client forgets it.

The page shows the demo student's advisor comments read-only.

## 4. Advising

Tables (migration 0006): `account` (a student account is attached to its student row),
`advisor_assignment`, and `plan_comment`. A comment is keyed by **student and course**, not by
plan row, and remembers the term the course was in when it was written, so it survives the
course being moved and the demo being re-seeded.

**Conversations** (2026-11-18, on request; migration 0007 adds `plan_comment.parent_id`). Each
comment opens a conversation that the student and their advisor both reply in, on the planner
("Messages with your advisor" for the student). A reply belongs to the conversation, not to
another reply, and carries its placement, so it shows beside the same course. A student may
also start one, to ask about a placement. Only the student resolves a conversation, as a whole.
Course badges and "open" counts count conversations, not replies.

`/advisees` lists each advisee with:
- declared programs
- credits completed, in progress and planned
- **on time / at risk**: whether the minimum-semester estimate fits before graduation
- how many needed courses are still unplanned
- plan problems, overloaded terms and open comments
- **waiting for your reply**: open conversations whose last message is the student's

A second fictional student, `demo-2` (a sophomore in MATH), is seeded so the list shows both an
on-time and an at-risk advisee.

## 5. Responsive layout

- **Below md (768px):** the sidebar becomes a top bar with a scrolling nav strip. The graph's
  pannable SVG is replaced by a list grouped by prerequisite depth. Each course shows its
  status as an icon and a word, and the selected course's chain is marked ("must come first",
  "one of a choice", "opens up"). The SVG-only legend and "Fit to view" are hidden.
- **Below lg (1024px):** the course detail panel, previously hidden at these widths, becomes a
  bottom sheet. The planner's tray folds into an "Add courses" button so the terms stay in
  reach.

The planner and graph were checked at 820px and 390px with no horizontal scroll.

## Demo script

1. `/`, then **Try the demo**. The planner opens on the demo copy.
2. Move CSC 498 to Spring 2026. It's rejected, naming senior standing and a 300-level CSC
   course. Place it in Fall 2026 and it's accepted.
3. Drag ECON 280 (search "ECON 280") into Spring 2026. It's rejected, needing ECON 220. Record
   it with an override note.
4. Add CSC 320 and CSC 330 to Spring 2026. The term reaches 5 credits and gets the overload
   warning.
5. **End demo**, then `/login` as `advisor`. Open `/advisees` and Duc Nguyen's plan, open
   CSC 322, and comment on it.
6. Log out and log in as `demo`. The comment is at the top, and CSC 322 shows a comment badge.
   Reply to it; log back in as `advisor` and the dashboard shows "1 waiting for your reply".
   Answer, then as `demo` mark it resolved.
7. Narrow the window: the nav strip, the graph's list view, and the bottom sheet.

## Known limits

- An advisor account cannot be created from the app, only from the seed fixture.
- "Not historically offered in this term" is not checked: there is no offering data yet (a
  Future Enhancement in the proposal).
- The planner assumes every course is offered every term, as the semester estimate does.
- Demo sessions live in the API process's memory, so a backend restart ends them.
