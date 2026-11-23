"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, CircleAlert, CircleCheck } from "lucide-react";
import { fetchSemesters, type SemesterEstimate as Estimate, type SemesterNeed } from "@/lib/api";

const LOADS = [
  { value: 4.5, label: "4.5 (maximum)" },
  { value: 4, label: "4.0 (normal)" },
];
const KIND: Record<SemesterNeed["kind"], string> = {
  planned: "planned",
  required: "required",
  chosen: "assumed choice",
  prerequisite: "prerequisite",
  unnamed: "no loaded course",
};

const termName = (t: string) =>
  `${{ FA: "Fall", SP: "Spring", WI: "Winter Term", MY: "May Term", SU: "Summer" }[t.slice(4)] ?? t.slice(4)} ${t.slice(0, 4)}`;
const terms = (n: number) => `${n} term${n === 1 ? "" : "s"}`;
const moreTerms = (n: number) => `${n} more term${n === 1 ? "" : "s"}`;
const fmt = (n: number) => (Number.isInteger(n) ? `${n}` : n.toFixed(1));

/** The minimum-semester estimate for a student's declared programs plus
 *  the degree (and any `add`ed programs): both bounds, and the greater. */
export function SemesterEstimate({ student, add = [] }: { student: string; add?: string[] }) {
  const [load, setLoad] = useState(4.5);
  const [est, setEst] = useState<Estimate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const addKey = add.join(",");

  useEffect(() => {
    setError(null);
    fetchSemesters(student, { add: addKey ? addKey.split(",") : [], maxLoad: load })
      .then(setEst)
      .catch((e) => setError(String(e)));
  }, [student, addKey, load]);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!est) return <section className="panel p-5 text-sm text-muted-foreground">Estimating…</section>;

  const ok = est.feasible;
  // What lengthens the chain beyond its courses: standing waits and the
  // branch choices made along it.
  const chainNames = new Set(est.chain.map((c) => c.replace("-", " ")));
  const why = est.assumed.filter((a) => chainNames.has(a.split(":")[0]));
  const rounds = new Map<number, SemesterNeed[]>();
  est.needs.forEach((n) => rounds.set(n.round, [...(rounds.get(n.round) ?? []), n]));

  return (
    <section className="panel flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
            Minimum terms to finish · {est.programs.join(" + ")}
          </p>
          <h2 className="mt-1 flex flex-wrap items-baseline gap-x-3 font-display text-3xl">
            {est.estimate === 0 ? "Nothing left" : moreTerms(est.estimate)}
            <span
              className="inline-flex items-center gap-1 font-sans text-sm font-medium"
              style={{ color: ok ? "var(--status-completed)" : "var(--destructive)" }}
            >
              {ok ? <CircleCheck className="size-4" aria-hidden /> : <CircleAlert className="size-4" aria-hidden />}
              {ok
                ? `on time for ${termName(est.expected_graduation)}`
                : `${terms(est.extra_terms)} past ${termName(est.expected_graduation)}`}
            </span>
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {est.current_term ? `After ${termName(est.current_term)}: ` : ""}
            {terms(est.terms_left)} left before graduation.
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm">
          Credits per term
          <select
            value={load}
            onChange={(e) => setLoad(Number(e.target.value))}
            className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm"
          >
            {LOADS.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Bound
          title="Prerequisite chain"
          value={est.chain_bound}
          binds={est.binding === "chain" || est.binding === "both"}
          explain="The longest run of courses that must be taken one after another, however many credits a term holds."
        >
          {est.chain.length ? (
            <div className="flex flex-wrap items-center gap-1">
              {est.chain.map((c, i) => (
                <span key={c} className="flex items-center gap-1">
                  {i ? <ArrowRight className="size-3 text-muted-foreground" aria-hidden /> : null}
                  <Link href={`/courses/${c}`} className="rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-[11px] hover:bg-secondary">
                    {c.replace("-", " ")}
                  </Link>
                </span>
              ))}
            </div>
          ) : null}
          {why.length ? (
            <ul className="text-xs text-muted-foreground">
              {why.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          ) : null}
        </Bound>
        <Bound
          title="Credits"
          value={est.credit_bound}
          binds={est.binding === "credits" || est.binding === "both"}
          explain={`${est.credit_basis}.`}
        >
          <p className="font-mono text-sm">
            {fmt(est.remaining_credits)} ÷ {fmt(est.max_load)} = {fmt(est.remaining_credits / est.max_load)} → {terms(est.credit_bound)}
          </p>
        </Bound>
      </div>
      <p className="text-xs text-muted-foreground">
        The estimate is the greater of the two, because a plan has to satisfy both. {est.note}
      </p>

      {est.needs.length ? (
        <div>
          <button
            type="button"
            onClick={() => setShowAll(!showAll)}
            className="text-sm font-medium underline-offset-2 hover:underline"
            aria-expanded={showAll}
          >
            {showAll ? "Hide" : "Show"} what is left ({est.needs.length} courses)
          </button>
          {showAll ? (
            <div className="mt-2 flex flex-col gap-3">
              {[...rounds.entries()]
                .sort((a, b) => a[0] - b[0])
                .map(([r, list]) => (
                  <div key={r}>
                    <h4 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                      {r === 1 ? "Could be taken next term" : `Not before term ${r}`}
                    </h4>
                    <ul className="mt-1 divide-y divide-border/60">
                      {list.map((n, i) => (
                        <li key={`${n.course_id}-${i}`} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-1.5 text-sm">
                          <span className="w-20 font-mono font-medium">{n.label === "Not in the loaded catalog" ? "—" : n.label}</span>
                          <span className="min-w-0 flex-1 text-muted-foreground">
                            {n.title || (n.course_id ? "" : "No course in the loaded catalog meets this")}
                          </span>
                          <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">{KIND[n.kind]}</span>
                          <span className="w-full pl-[5.75rem] text-xs text-muted-foreground/80">{n.reasons.join(" · ")}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              {est.assumed.length ? (
                <details className="text-xs text-muted-foreground">
                  <summary className="cursor-pointer">Assumptions behind the chain ({est.assumed.length})</summary>
                  <ul className="mt-1 list-disc pl-5">
                    {est.assumed.map((a) => (
                      <li key={a}>{a}</li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export function Bound({
  title,
  value,
  binds,
  explain,
  children,
}: {
  title: string;
  value: number;
  binds: boolean;
  explain: string;
  children?: React.ReactNode;
}) {
  return (
    <div
      className="flex flex-col gap-2 rounded-lg p-4"
      style={{
        border: binds ? "2px solid var(--gold)" : "1px solid var(--border)",
        background: binds ? "var(--accent)" : "var(--surface)",
      }}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-medium">{title}</span>
        {binds ? (
          <span className="rounded-full bg-gold px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gold-foreground">
            sets the estimate
          </span>
        ) : null}
      </div>
      <span className="font-display text-3xl">{terms(value)}</span>
      {children}
      <p className="text-xs text-muted-foreground">{explain}</p>
    </div>
  );
}
