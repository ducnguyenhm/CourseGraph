"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Check, CircleAlert, CircleCheck, Repeat2, Search, TriangleAlert } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { StateBadge } from "@/components/RequirementAudit";
import { Bound } from "@/components/SemesterEstimate";
import { SignInPrompt } from "@/components/SignInPrompt";
import {
  fetchExplore,
  fetchPrograms,
  fetchStudent,
  type Exploration,
  type ProgramImpact,
  type ProgramSummary,
  type RequirementLine,
  type SemesterNeed,
  type StudentDetail,
} from "@/lib/api";
import { useStudent } from "@/lib/useStudent";

const input = "rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm";

const termName = (t: string) =>
  `${{ FA: "Fall", SP: "Spring", WI: "Winter Term", MY: "May Term", SU: "Summer" }[t.slice(4)] ?? t.slice(4)} ${t.slice(0, 4)}`;
const terms = (n: number) => `${n} term${n === 1 ? "" : "s"}`;
const fmt = (n: number) => (Number.isInteger(n) ? `${n}` : n.toFixed(1));
const name = (c: string) => c.replace("-", " ");

export default function ExplorePage() {
  const viewer = useStudent();
  const student = viewer?.student ?? null;
  const [record, setRecord] = useState<StudentDetail | null>(null);
  const [programs, setPrograms] = useState<ProgramSummary[]>([]);
  const [added, setAdded] = useState<string[]>([]);
  const [load, setLoad] = useState(4.5);
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<Exploration | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    setAdded(q.get("add")?.split(",").filter(Boolean).map((a) => a.toUpperCase()) ?? []);
    if (q.get("load")) setLoad(Number(q.get("load")));
    fetchPrograms()
      .then((ps) => setPrograms(ps.filter((p) => p.kind !== "degree")))
      .catch(() => setPrograms([]));
    setReady(true);
  }, []);

  useEffect(() => {
    if (!student) return;
    fetchStudent(student).then(setRecord).catch(() => setRecord(null));
  }, [student]);

  // A program the student has since declared is no longer a what-if.
  const declared = useMemo(() => new Set(record?.programs ?? []), [record]);
  const what = useMemo(() => added.filter((a) => !declared.has(a)), [added, declared]);

  useEffect(() => {
    if (!ready || !student) return;
    const q = new URLSearchParams();
    if (viewer?.advisor) q.set("student", student);
    if (what.length) q.set("add", what.join(","));
    if (load !== 4.5) q.set("load", String(load));
    window.history.replaceState(null, "", `?${q}`);
    setError(null);
    if (!what.length) {
      setResult(null);
      return;
    }
    fetchExplore(student, what, load)
      .then(setResult)
      .catch((e) => {
        setResult(null);
        setError(String(e));
      });
  }, [ready, student, viewer?.advisor, what, load]);

  const shown = programs.filter((p) =>
    `${p.name} ${p.kind} ${p.program_id}`.toLowerCase().includes(query.toLowerCase()),
  );
  const toggle = (pid: string) =>
    setAdded((a) => (a.includes(pid) ? a.filter((x) => x !== pid) : [...a, pid]));

  return (
    <AppShell
      title="Major and minor explorer"
      subtitle="What would adding a program cost? Pick one or more; nothing is declared."
      aside={
        <div className="flex items-center gap-2">
          <select value={load} onChange={(e) => setLoad(Number(e.target.value))} aria-label="Credits per term" className={input}>
            <option value={4.5}>4.5 credits/term</option>
            <option value={4}>4.0 credits/term</option>
          </select>
        </div>
      }
    >
      {viewer && !student ? (
        <SignInPrompt advisor={viewer.advisor} to="/explore" />
      ) : (
      <div className="mx-auto grid max-w-6xl gap-5 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <aside className="panel flex h-fit flex-col gap-3 p-4 lg:sticky lg:top-4">
          <label className="relative">
            <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" aria-hidden />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search programs"
              aria-label="Search programs"
              className={`${input} w-full pl-8`}
            />
          </label>
          {(["major", "minor"] as const).map((kind) => (
            <div key={kind}>
              <h3 className="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">{kind}s</h3>
              <ul className="flex flex-col gap-1">
                {shown
                  .filter((p) => p.kind === kind)
                  .map((p) => {
                    const isDeclared = declared.has(p.program_id);
                    const on = what.includes(p.program_id);
                    return (
                      <li key={p.program_id}>
                        <label
                          className={`flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm ${
                            isDeclared ? "text-muted-foreground" : "cursor-pointer hover:bg-secondary"
                          } ${on ? "bg-accent font-medium" : ""}`}
                        >
                          <input type="checkbox" checked={on || isDeclared} disabled={isDeclared} onChange={() => toggle(p.program_id)} />
                          <span className="flex-1">{p.name}</span>
                          {isDeclared ? <span className="text-[10px] uppercase tracking-wide">declared</span> : null}
                        </label>
                      </li>
                    );
                  })}
              </ul>
            </div>
          ))}
          <p className="text-xs text-muted-foreground">
            Tick two to compare a second major with a minor, or both together.
          </p>
        </aside>

        <div className="flex min-w-0 flex-col gap-4">
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          {!what.length ? (
            <section className="panel p-8 text-center text-sm text-muted-foreground">
              Choose a major or minor on the left to see what it would take
              {record ? ` for ${record.name}` : ""}.
            </section>
          ) : result ? (
            <Analysis x={result} names={Object.fromEntries(programs.map((p) => [p.program_id, `${p.name} ${p.kind}`]))} />
          ) : (
            <section className="panel p-8 text-sm text-muted-foreground">Working it out…</section>
          )}
        </div>
      </div>
      )}
    </AppShell>
  );
}

function Analysis({ x, names }: { x: Exploration; names: Record<string, string> }) {
  const late = !x.combined.feasible;
  const shared = new Set([
    ...x.programs.flatMap((p) => p.shared_done.map((s) => s.course_id)),
    ...x.programs.flatMap((p) => p.shared_needed.map((s) => s.course_id)),
  ]);
  const grad = termName(x.expected_graduation);
  return (
    <>
      {/* The question the student came with, answered first. */}
      <section className="panel flex flex-col gap-4 p-5">
        <p className="text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
          Adding {x.programs.map((p) => `${p.program.name} ${p.program.kind}`).join(" + ")}
        </p>
        <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
          <h2 className="font-display text-4xl leading-none">
            {x.additional_terms > 0 ? `+${terms(x.additional_terms)}` : "No extra terms"}
          </h2>
          <span
            className="inline-flex items-center gap-1.5 pb-1 text-sm font-medium"
            style={{ color: late ? "var(--destructive)" : "var(--status-completed)" }}
          >
            {late ? <CircleAlert className="size-4" aria-hidden /> : <CircleCheck className="size-4" aria-hidden />}
            {late ? `Graduates ${terms(x.combined.extra_terms)} after ${grad}` : `Still graduates ${grad}`}
          </span>
        </div>
        <p className="text-sm text-muted-foreground">
          Minimum terms left: {x.baseline.estimate} now → <span className="font-medium text-foreground">{x.combined.estimate}</span> with{" "}
          {x.programs.length > 1 ? "these programs" : "this program"}, against {terms(x.terms_left)} before graduation
          {x.current_term ? ` (after ${termName(x.current_term)})` : ""}.
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          <Stat value={`${x.new_courses.length}`} unit={`new course${x.new_courses.length === 1 ? "" : "s"}`} detail={`${fmt(x.new_credits)} credits not already on the plan`} />
          <Stat
            value={`+${fmt(x.extra_credits_to_graduate)}`}
            unit="credits to graduate"
            detail={
              x.extra_credits_to_graduate < x.new_credits
                ? "Less than the new courses: some fill electives the degree requires anyway."
                : "Every new course adds to what is left."
            }
          />
          <Stat value={`${shared.size}`} unit={`course${shared.size === 1 ? "" : "s"} count twice`} detail="With a program already declared." />
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2">
        <Bound
          title="Prerequisite chain"
          value={x.combined.chain_bound}
          binds={x.combined.binding === "chain" || x.combined.binding === "both"}
          explain="The longest run of courses that must follow one another."
        >
          {x.combined.chain.length ? (
            <div className="flex flex-wrap items-center gap-1">
              {x.combined.chain.map((c, i) => (
                <span key={c} className="flex items-center gap-1">
                  {i ? <ArrowRight className="size-3 text-muted-foreground" aria-hidden /> : null}
                  <CourseChip id={c} />
                </span>
              ))}
            </div>
          ) : null}
        </Bound>
        <Bound
          title="Credits"
          value={x.combined.credit_bound}
          binds={x.combined.binding === "credits" || x.combined.binding === "both"}
          explain={`${x.combined.credit_basis}.`}
        >
          <p className="font-mono text-sm">
            {fmt(x.combined.remaining_credits)} ÷ {fmt(x.max_load)} → {terms(x.combined.credit_bound)}
          </p>
        </Bound>
      </section>

      {x.programs.map((p) => (
        <ProgramCard key={p.program.program_id} p={p} student={x.student_key} names={names} />
      ))}
      <p className="text-xs text-muted-foreground">{x.note}</p>
    </>
  );
}

function Stat({ value, unit, detail }: { value: string; unit: string; detail: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-3">
      <div className="flex items-baseline gap-1.5">
        <span className="font-display text-2xl">{value}</span>
        <span className="text-sm">{unit}</span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
    </div>
  );
}

function CourseChip({ id }: { id: string }) {
  return (
    <Link href={`/courses/${id}`} className="rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-[11px] hover:bg-secondary">
      {name(id)}
    </Link>
  );
}

function Line({ l }: { l: RequirementLine }) {
  const count = l.rule_type === "specific_course" ? "" : ` ${fmt(Math.min(l.have, l.need))}/${fmt(l.need)}`;
  return (
    <li className="flex items-start gap-2 py-1.5 text-sm">
      <StateBadge state={l.state} compact />
      <span className="min-w-0 flex-1">{l.label}</span>
      {count ? <span className="text-xs tabular-nums text-muted-foreground">{count}</span> : null}
      {l.applied.length && l.rule_type !== "specific_course" ? (
        <span className="flex flex-wrap gap-1">
          {l.applied.map((c) => (
            <CourseChip key={c} id={c} />
          ))}
        </span>
      ) : null}
    </li>
  );
}

function NeedRow({ n }: { n: SemesterNeed }) {
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 py-1.5 text-sm">
      {n.course_id ? <CourseChip id={n.course_id} /> : <span className="font-mono text-[11px]">—</span>}
      <span className="min-w-0 flex-1 text-muted-foreground">{n.title || "No course in the loaded catalog meets this"}</span>
      <span className="text-xs text-muted-foreground/80">
        {n.kind === "prerequisite" ? n.reasons.join(", ") : n.round > 1 ? `not before term ${n.round}` : ""}
      </span>
    </li>
  );
}

function ProgramCard({ p, student, names }: { p: ProgramImpact; student: string; names: Record<string, string> }) {
  const met = p.satisfied.length;
  const list = (ids: string[]) => ids.map((i) => names[i] ?? i).join(", ");
  const total = met + p.underway.length + p.outstanding.length;
  return (
    <section className="panel flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-baseline gap-3">
        <h3 className="text-xl">
          {p.program.name} {p.program.kind}
        </h3>
        <span className="text-sm text-muted-foreground">
          {met} of {total} requirements already met by completed courses
        </span>
        <Link href={`/audit?student=${student}&program=${p.program.program_id}`} className="ml-auto inline-flex items-center gap-1 text-sm underline-offset-2 hover:underline">
          Full audit <ArrowRight className="size-3.5" />
        </Link>
      </div>

      {p.warnings.map((w) => (
        <p key={w} className="flex gap-2 rounded-md border px-3 py-2 text-sm" style={{ borderColor: "var(--warning)", background: "var(--warning-soft)" }}>
          <TriangleAlert className="mt-0.5 size-4 shrink-0" style={{ color: "var(--warning)" }} aria-hidden />
          {w}
        </p>
      ))}

      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <h4 className="flex items-center gap-1.5 text-sm font-semibold">
            <Check className="size-4" aria-hidden /> Already satisfied {p.underway.length ? "or under way" : ""}
          </h4>
          <ul className="divide-y divide-border/60">
            {[...p.satisfied, ...p.underway].map((l, i) => (
              <Line key={i} l={l} />
            ))}
            {!met && !p.underway.length ? <li className="py-1.5 text-sm text-muted-foreground">Nothing yet.</li> : null}
          </ul>
        </div>
        <div>
          <h4 className="text-sm font-semibold">Outstanding</h4>
          <ul className="divide-y divide-border/60">
            {p.outstanding.map((l, i) => (
              <Line key={i} l={l} />
            ))}
            {!p.outstanding.length ? <li className="py-1.5 text-sm text-muted-foreground">Nothing outstanding.</li> : null}
          </ul>
        </div>
      </div>

      {p.shared_done.length || p.shared_needed.length ? (
        <div>
          <h4 className="flex items-center gap-1.5 text-sm font-semibold">
            <Repeat2 className="size-4" aria-hidden /> Counts twice
          </h4>
          <ul className="mt-1 flex flex-col gap-1 text-sm">
            {p.shared_done.map((s) => (
              <li key={s.course_id} className="flex flex-wrap items-center gap-2">
                <CourseChip id={s.course_id} />
                <span className="text-muted-foreground">on your record, already counting toward the {list(s.programs)}</span>
              </li>
            ))}
            {p.shared_needed.map((s) => (
              <li key={s.course_id} className="flex flex-wrap items-center gap-2">
                <CourseChip id={s.course_id} />
                <span className="text-muted-foreground">still to take, and would also count toward the {list(s.programs)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div>
        <h4 className="text-sm font-semibold">
          New courses for this program{" "}
          <span className="font-normal text-muted-foreground">
            ({p.new_courses.length}, {fmt(p.new_credits)} credits)
          </span>
        </h4>
        {p.new_courses.length ? (
          <ul className="divide-y divide-border/60">
            {p.new_courses.map((n, i) => (
              <NeedRow key={`${n.course_id}-${i}`} n={n} />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">None: everything it needs is already on the record or the plan.</p>
        )}
      </div>
    </section>
  );
}
