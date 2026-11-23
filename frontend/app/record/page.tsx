"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, Plus, Trash2 } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { input, OptionalTerm, ProgramPicker, STANDINGS, TermPicker, TERMS } from "@/components/RecordFields";
import { SignInPrompt } from "@/components/SignInPrompt";
import {
  AREA_NAME,
  AREAS,
  addEnrollment,
  areasOf,
  deleteEnrollment,
  fetchAllCourses,
  fetchAudit,
  fetchPrograms,
  fetchStudent,
  placeCourse,
  unplanCourse,
  updateEnrollment,
  updateStudent,
  type Area,
  type AuditNode,
  type Competence,
  type CourseSummary,
  type Enrollment,
  type ProgramSummary,
  type Standing,
  type StudentDetail,
} from "@/lib/api";
import { DEMO_STUDENT, saveLogin } from "@/lib/session";
import { useStudent } from "@/lib/useStudent";

const TERM_ORDER: Record<string, number> = { WI: 0, SP: 1, MY: 2, SU: 3, FA: 4 };
const PLAN_KINDS = ["FA", "WI", "SP", "MY"];

const termLabel = (t: string) => `${TERMS.find((x) => x.value === t.slice(4))?.label ?? t.slice(4)} ${t.slice(0, 4)}`;
const termKey = (t: string) => Number(t.slice(0, 4)) * 10 + (TERM_ORDER[t.slice(4)] ?? 5);
const firstTerm = (s: StudentDetail) => s.enrollments.map((e) => e.term).sort((a, b) => termKey(a) - termKey(b))[0];

type Apply = (w: () => Promise<unknown>) => Promise<boolean>;

export default function RecordPage() {
  const viewer = useStudent();
  const key = viewer?.student ?? null;
  const session = viewer?.session ?? null;
  // Only the student edits their own record. An advisor reads it; a demo
  // session plans in memory and never changes the stored record.
  const editable = !!session?.account && session.account.role === "student" && session.account.student_key === key;
  const [student, setStudent] = useState<StudentDetail | null>(null);
  const [programs, setPrograms] = useState<ProgramSummary[]>([]);
  const [courses, setCourses] = useState<CourseSummary[]>([]);
  // course id -> the Foundations area the engine is currently counting it toward.
  const [placed, setPlaced] = useState<Map<string, Area>>(new Map());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchPrograms().then(setPrograms).catch(() => setPrograms([]));
    fetchAllCourses().then(setCourses).catch(() => setCourses([]));
  }, []);

  const refreshPlacement = useCallback((k: string) => {
    fetchAudit(k, "DEGREE-BA")
      .then((a) => {
        const m = new Map<string, Area>();
        const walk = (n: AuditNode) => {
          if (n.rule_type === "attribute_count" && n.spec.exclusive)
            n.applied.forEach((c) => m.set(c, n.spec.attribute as Area));
          n.children.forEach(walk);
        };
        walk(a.root);
        setPlaced(m);
      })
      .catch(() => setPlaced(new Map()));
  }, []);

  useEffect(() => {
    if (!key) return;
    fetchStudent(key).then(setStudent).catch((e) => setError(String(e)));
    refreshPlacement(key);
  }, [key, refreshPlacement]);

  // Record writes return the whole record, so the page swaps it in; plan
  // writes return the plan, so the page re-reads the record after them.
  const apply = useCallback<Apply>(
    async (write) => {
      if (!key) return false;
      setError(null);
      try {
        const next = await write();
        const record = next && typeof next === "object" && "enrollments" in next ? (next as StudentDetail) : await fetchStudent(key);
        setStudent(record);
        refreshPlacement(key);
        // A new name shows in the account box too.
        if (session?.token && session.account && session.account.name !== record.name)
          saveLogin(session.token, { ...session.account, name: record.name });
        return true;
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        return false;
      }
    },
    [key, refreshPlacement, session],
  );

  const terms = useMemo(() => {
    const by = new Map<string, Enrollment[]>();
    student?.enrollments.forEach((e) => by.set(e.term, [...(by.get(e.term) ?? []), e]));
    return [...by.entries()].sort((a, b) => termKey(a[0]) - termKey(b[0]));
  }, [student]);

  const credits = (status: string) =>
    student?.enrollments.filter((e) => e.status === status).reduce((s, e) => s + (e.credits ?? 0), 0) ?? 0;

  return (
    <AppShell
      title="Course record"
      subtitle={
        editable
          ? "Your courses so far and your years at DePauw. The audit, progress and planner all use this record."
          : "Every course on the record, completed, in progress and planned."
      }
    >
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {viewer && !key ? <SignInPrompt advisor={viewer.advisor} to="/record" /> : null}
        {error ? (
          <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        ) : null}

        {student ? (
          <>
            {!editable ? (
              <p className="rounded-md border border-border bg-secondary px-3 py-2 text-sm">
                {viewer?.advisor
                  ? `You are viewing ${student.name}'s record. Only ${student.name} can change it; comment on the plan instead.`
                  : "Demo mode shows this record read-only. Log in as demo to change it."}
              </p>
            ) : null}
            <StudentCard
              student={student}
              programs={programs}
              apply={apply}
              editable={editable}
              credits={{ done: credits("completed"), doing: credits("in_progress") }}
            />
            {editable ? <AddCourse student={student} courses={courses} apply={apply} /> : null}
            <section className="panel overflow-hidden">
              {terms.length ? (
                terms.map(([term, list]) => (
                  <div key={term} className="border-b border-border last:border-b-0">
                    <h3 className="bg-surface-strong px-4 py-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                      {termLabel(term)}
                    </h3>
                    <div className="divide-y divide-border/60">
                      {list.map((e) => (
                        <CourseRow key={e.id} e={e} placed={placed.get(e.course_id)} student={student} apply={apply} editable={editable} />
                      ))}
                    </div>
                  </div>
                ))
              ) : (
                <p className="p-4 text-sm text-muted-foreground">
                  {editable ? "No courses yet. Add the first one above." : "No courses on the record yet."}
                </p>
              )}
            </section>
            <section className="panel p-4">
              <div className="flex flex-wrap items-baseline gap-3">
                <h3 className="text-sm font-semibold">Planned</h3>
                <Link
                  href={`/planner${viewer?.advisor ? `?student=${encodeURIComponent(student.student_key)}` : ""}`}
                  className="ml-auto inline-flex items-center gap-1 text-sm underline-offset-2 hover:underline"
                >
                  {editable ? "Plan by term in the planner" : "Open the plan"} <ArrowRight className="size-3.5" />
                </Link>
              </div>
              {student.plan.length ? (
                <ul className="mt-2 flex flex-wrap gap-2">
                  {[...student.plan]
                    .sort((a, b) => termKey(a.term) - termKey(b.term))
                    .map((p) => (
                      <li key={p.id} className="flex items-center gap-1.5 rounded border border-dashed border-border px-2 py-1 text-xs">
                        <span className="font-mono">{p.label}</span>
                        <span className="text-muted-foreground">{termLabel(p.term)}</span>
                        {editable ? (
                          <button
                            type="button"
                            aria-label={`Remove ${p.label} from the plan`}
                            onClick={() => apply(() => unplanCourse(student.student_key, p.course_id))}
                            className="text-muted-foreground hover:text-destructive"
                          >
                            <Trash2 className="size-3.5" />
                          </button>
                        ) : null}
                      </li>
                    ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-muted-foreground">Nothing planned yet.</p>
              )}
            </section>
          </>
        ) : null}
      </div>
    </AppShell>
  );
}

function StudentCard({
  student,
  programs,
  apply,
  editable,
  credits,
}: {
  student: StudentDetail;
  programs: ProgramSummary[];
  apply: Apply;
  editable: boolean;
  credits: { done: number; doing: number };
}) {
  const k = student.student_key;
  const names = Object.fromEntries(programs.map((p) => [p.program_id, `${p.name} ${p.kind}`]));
  const standing = STANDINGS.find((s) => s.value === student.class_standing)?.label ?? student.class_standing;
  return (
    <section className="panel flex flex-col gap-3 p-5">
      <div className="flex flex-wrap items-center gap-3">
        {editable ? (
          <input
            key={student.name}
            defaultValue={student.name}
            aria-label="Name"
            maxLength={128}
            onBlur={(e) => {
              const name = e.target.value.trim();
              if (name && name !== student.name) apply(() => updateStudent(k, { name }));
            }}
            className="min-w-0 rounded-md border border-transparent bg-transparent px-1 text-xl hover:border-border focus:border-border"
          />
        ) : (
          <h2 className="text-xl">{student.name}</h2>
        )}
        <span className="text-sm text-muted-foreground">
          {credits.done} credits completed{credits.doing ? ` · ${credits.doing} in progress` : ""} · catalog {student.catalog_year}
        </span>
        <Link href={`/audit${editable ? "" : `?student=${k}`}`} className="ml-auto inline-flex items-center gap-1 text-sm underline-offset-2 hover:underline">
          Open the audit <ArrowRight className="size-3.5" />
        </Link>
      </div>
      {k === DEMO_STUDENT && editable ? (
        <p className="text-xs text-muted-foreground">The fictional demo record. Re-seeding the database puts it back as it was.</p>
      ) : null}
      {editable ? (
        <>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <label className="flex items-center gap-2">
              Standing
              <select value={student.class_standing} onChange={(e) => apply(() => updateStudent(k, { class_standing: e.target.value as Standing }))} className={input}>
                {STANDINGS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2">
              Started
              <OptionalTerm
                value={student.start_term}
                fallback={firstTerm(student) ?? "2024FA"}
                unset="Not set"
                onChange={(t) => apply(() => updateStudent(k, { start_term: t }))}
              />
            </label>
            <label className="flex items-center gap-2">
              Graduating
              <TermPicker value={student.expected_graduation} onChange={(t) => apply(() => updateStudent(k, { expected_graduation: t }))} only={["SP", "FA"]} />
            </label>
            <label className="flex items-center gap-2">
              Current semester
              <OptionalTerm
                value={student.current_term}
                fallback={student.current_term_auto ?? "2026FA"}
                unset={student.current_term_auto ? `From my courses (${termLabel(student.current_term_auto)})` : "From my courses"}
                onChange={(t) => apply(() => updateStudent(k, { current_term: t }))}
              />
            </label>
          </div>
          <ProgramPicker programs={programs} value={student.programs} onChange={(p) => apply(() => updateStudent(k, { programs: p }))} />
        </>
      ) : (
        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <div className="flex gap-1.5"><dt className="text-muted-foreground">Standing</dt><dd>{standing}</dd></div>
          <div className="flex gap-1.5"><dt className="text-muted-foreground">Started</dt><dd>{student.start_term ? termLabel(student.start_term) : "not set"}</dd></div>
          <div className="flex gap-1.5"><dt className="text-muted-foreground">Graduating</dt><dd>{termLabel(student.expected_graduation)}</dd></div>
          <div className="flex gap-1.5">
            <dt className="text-muted-foreground">Programs</dt>
            <dd>{student.programs.map((p) => names[p] ?? p).join(", ") || "none declared"}</dd>
          </div>
        </dl>
      )}
    </section>
  );
}

const EMPTY_NEW = { title: "", credits: "1", areas: [] as Area[], fys: false, es: false };

function AddCourse({
  student,
  courses,
  apply,
}: {
  student: StudentDetail;
  courses: CourseSummary[];
  apply: Apply;
}) {
  const [code, setCode] = useState("");
  const [term, setTerm] = useState(() => student.enrollments.at(-1)?.term ?? student.start_term ?? "2024FA");
  const [status, setStatus] = useState<"completed" | "in_progress" | "planned">("completed");
  const [grade, setGrade] = useState("");
  const [competence, setCompetence] = useState<Competence | "">("");
  const [area, setArea] = useState<Area | "">("");
  const [nc, setNc] = useState(EMPTY_NEW);

  const id = normalize(code);
  const known = id ? courses.find((c) => c.course_id === id) : undefined;
  const isNew = Boolean(id) && !known;
  const areas: Area[] = known ? areasOf(known) : nc.areas;
  const compOptions: Competence[] = known
    ? (["W", "Q", "S"] as Competence[]).filter((c) => known.competence_variants.includes(c) || known.attributes.includes(c))
    : ["W", "Q", "S"];

  return (
    <form
      className="panel flex flex-col gap-3 p-5"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!id) return;
        // A future course is placed by the planner, so its prerequisites are
        // checked the same way as a drag on the planner page.
        const ok = await apply(() =>
          status === "planned"
            ? placeCourse(student.student_key, id, term)
            : addEnrollment(student.student_key, {
            course_id: id,
            term,
            status,
            grade: grade || null,
            competence: competence || null,
            area_choice: area || null,
            new_course: isNew
              ? {
                  title: nc.title,
                  credits: Number(nc.credits),
                  areas: nc.areas,
                  attributes: [...(nc.fys ? (["FYS"] as const) : []), ...(nc.es ? (["ES"] as const) : [])],
                  competence_variants: [],
                }
              : undefined,
          }),
        );
        if (ok) {
          setCode("");
          setGrade("");
          setCompetence("");
          setArea("");
          setNc(EMPTY_NEW);
        }
      }}
    >
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <Plus className="size-4" /> Add a course
      </h3>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Course
          <input
            list="catalog-courses"
            required
            placeholder="CSC 231"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className={`${input} w-36 font-mono`}
          />
          <datalist id="catalog-courses">
            {courses.map((c) => (
              <option key={c.course_id} value={c.label}>
                {c.title}
              </option>
            ))}
          </datalist>
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Term
          <TermPicker value={term} onChange={setTerm} only={status === "planned" ? PLAN_KINDS : undefined} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Status
          <select
            value={status}
            onChange={(e) => {
              const next = e.target.value as typeof status;
              setStatus(next);
              // The planner has fall, Winter Term, spring and May Term; no summer.
              if (next === "planned" && !PLAN_KINDS.includes(term.slice(4))) setTerm(`${term.slice(0, 4)}FA`);
            }}
            className={input}
          >
            <option value="completed">Completed</option>
            <option value="in_progress">In progress</option>
            <option value="planned">Planned (checked)</option>
          </select>
        </label>
        {status !== "planned" ? (
          <>
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              Grade
              <input value={grade} onChange={(e) => setGrade(e.target.value.toUpperCase())} maxLength={4} placeholder="A-" className={`${input} w-16`} />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              Competence
              <select value={competence} onChange={(e) => setCompetence(e.target.value as Competence | "")} className={input} disabled={!compOptions.length}>
                <option value="">none</option>
                {compOptions.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
          </>
        ) : null}
        {areas.length > 1 && status !== "planned" ? (
          <label className="flex flex-col gap-1 text-xs text-muted-foreground">
            Counts toward
            <select value={area} onChange={(e) => setArea(e.target.value as Area | "")} className={input}>
              <option value="">Auto: let the audit choose</option>
              {areas.map((a) => (
                <option key={a} value={a}>
                  {AREA_NAME[a]}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <button type="submit" disabled={!id || (isNew && (!nc.title || status === "planned"))} className="rounded-md bg-primary px-4 py-1.5 text-sm text-primary-foreground hover:opacity-90 disabled:opacity-40">
          Add
        </button>
      </div>
      {known ? (
        <p className="text-xs text-muted-foreground">
          {known.label}: {known.title}
          {areas.length ? ` · ${areas.join(" or ")}` : ""}
          {known.retired ? " · retired number" : ""}
        </p>
      ) : code && !id ? (
        <p className="text-xs text-destructive">Use the form SUBJ 123, e.g. HIST 101.</p>
      ) : null}
      {isNew && status === "planned" ? (
        <p className="text-xs text-muted-foreground">Only catalog courses can be planned; the planner checks their prerequisites.</p>
      ) : isNew ? (
        <div className="flex flex-col gap-2 rounded-md border border-dashed border-border p-3">
          <p className="text-xs text-muted-foreground">
            {id.replace("-", " ")} isn&apos;t in the loaded catalog. Describe it as your transcript or the catalog lists it.
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              Title
              <input required value={nc.title} onChange={(e) => setNc({ ...nc, title: e.target.value })} className={`${input} w-64`} />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              Credits
              <input type="number" min={0} max={2} step={0.25} value={nc.credits} onChange={(e) => setNc({ ...nc, credits: e.target.value })} className={`${input} w-20`} />
            </label>
          </div>
          <fieldset className="flex flex-wrap items-center gap-2 text-xs">
            <legend className="mb-1 text-muted-foreground">Areas (pick two for an &ldquo;X-or-Y&rdquo; course)</legend>
            {AREAS.map((a) => (
              <label key={a} className="flex items-center gap-1 rounded border border-border px-2 py-1">
                <input
                  type="checkbox"
                  checked={nc.areas.includes(a)}
                  disabled={!nc.areas.includes(a) && nc.areas.length >= 2}
                  onChange={(e) => setNc({ ...nc, areas: e.target.checked ? [...nc.areas, a] : nc.areas.filter((x) => x !== a) })}
                />
                {AREA_NAME[a]}
              </label>
            ))}
            <label className="flex items-center gap-1 rounded border border-border px-2 py-1">
              <input type="checkbox" checked={nc.fys} onChange={(e) => setNc({ ...nc, fys: e.target.checked })} />
              First-Year Seminar
            </label>
            <label className="flex items-center gap-1 rounded border border-border px-2 py-1">
              <input type="checkbox" checked={nc.es} onChange={(e) => setNc({ ...nc, es: e.target.checked })} />
              Extended Studies
            </label>
          </fieldset>
        </div>
      ) : null}
    </form>
  );
}

function CourseRow({
  e,
  placed,
  student,
  apply,
  editable,
}: {
  e: Enrollment;
  placed: Area | undefined;
  student: StudentDetail;
  apply: Apply;
  editable: boolean;
}) {
  const [confirm, setConfirm] = useState(false);
  const k = student.student_key;
  const patch = (body: Parameters<typeof updateEnrollment>[2]) => apply(() => updateEnrollment(k, e.id, body));
  if (!editable) {
    return (
      <div className="grid grid-cols-2 items-center gap-x-3 gap-y-1 px-4 py-2 text-sm sm:grid-cols-[5rem_minmax(0,1fr)_3rem_7rem_3rem_3rem_4rem]">
        <Link href={`/courses/${e.course_id}`} className="font-mono font-medium hover:underline">
          {e.label}
        </Link>
        <span className="truncate text-muted-foreground" title={e.title}>
          {e.title}
        </span>
        <span className="text-right tabular-nums text-muted-foreground">{e.credits ?? "–"} cr</span>
        <span>{e.status === "completed" ? "Completed" : "In progress"}</span>
        <span className="text-muted-foreground">{e.grade ?? ""}</span>
        <span className="text-muted-foreground">{e.competence ?? ""}</span>
        <span className="text-xs text-muted-foreground">{(e.area_choice ? [e.area_choice] : e.areas).join(" or ")}</span>
      </div>
    );
  }
  return (
    // Fixed columns from sm up, so every row's controls line up.
    <div className="grid grid-cols-2 items-center gap-x-3 gap-y-1.5 px-4 py-2 text-sm sm:grid-cols-[5rem_minmax(0,1fr)_3rem_8rem_4.5rem_6.5rem_11rem_auto]">
      <Link href={`/courses/${e.course_id}`} className="w-20 font-mono font-medium hover:underline">
        {e.label}
      </Link>
      <span className="truncate text-muted-foreground" title={e.title}>
        {e.title}
        {e.added_by_student ? <span className="ml-1.5 text-[10px] uppercase tracking-wide">· entered by you</span> : null}
        {e.counts_as.length ? <span className="ml-1.5 text-xs">· counts as {e.counts_as.map((c) => c.replace("-", " ")).join(", ")}</span> : null}
      </span>
      <span className="w-14 text-right tabular-nums text-muted-foreground">{e.credits ?? "–"} cr</span>
      <select value={e.status} onChange={(ev) => patch({ status: ev.target.value as Enrollment["status"] })} className={input} aria-label="Status">
        <option value="completed">Completed</option>
        <option value="in_progress">In progress</option>
      </select>
      <input
        defaultValue={e.grade ?? ""}
        onBlur={(ev) => {
          const g = ev.target.value.trim().toUpperCase() || null;
          if (g !== e.grade) patch({ grade: g });
        }}
        placeholder="grade"
        maxLength={4}
        className={`${input} w-16`}
        aria-label="Grade"
      />
      <select
        value={e.competence ?? ""}
        onChange={(ev) => patch({ competence: (ev.target.value || null) as Competence | null })}
        className={input}
        aria-label="Competence"
        disabled={!e.competence_options.length}
        title={e.competence_options.length ? "Competence earned in this section" : "Not offered with a competence"}
      >
        <option value="">no W/Q/S</option>
        {e.competence_options.map((c) => (
          <option key={c}>{c}</option>
        ))}
      </select>
      {e.areas.length > 1 ? (
        <select
          value={e.area_choice ?? ""}
          onChange={(ev) => patch({ area_choice: (ev.target.value || null) as Area | null })}
          className={`${input} w-full border-gold`}
          aria-label="Counts toward"
          title="This course is printed as one area or another; it can fill only one."
        >
          <option value="">Auto{placed ? `: ${placed}` : ": unused"}</option>
          {e.areas.map((a) => (
            <option key={a} value={a}>
              {a}: {AREA_NAME[a]}
            </option>
          ))}
        </select>
      ) : e.areas.length === 1 ? (
        <span className="justify-self-start rounded bg-muted px-2 py-1 text-xs text-muted-foreground" title={AREA_NAME[e.areas[0]]}>
          {e.areas[0]}
        </span>
      ) : (
        <span />
      )}
      {confirm ? (
        <span className="flex items-center gap-1 text-xs">
          Remove?
          <button type="button" onClick={() => apply(() => deleteEnrollment(k, e.id))} className="rounded bg-destructive px-2 py-1 text-destructive-foreground">
            Yes
          </button>
          <button type="button" onClick={() => setConfirm(false)} className="rounded border border-border px-2 py-1">
            No
          </button>
        </span>
      ) : (
        <button type="button" aria-label={`Remove ${e.label}`} onClick={() => setConfirm(true)} className="text-muted-foreground hover:text-destructive">
          <Trash2 className="size-4" />
        </button>
      )}
    </div>
  );
}

/** "hist101", "HIST 101", "HIST-101Q" -> "HIST-101"; anything else -> "". */
function normalize(v: string): string {
  const m = v.trim().match(/^([A-Za-z]{2,5})[\s-]*(\d{3})[A-Za-z]?$/);
  return m ? `${m[1].toUpperCase()}-${m[2]}` : "";
}
