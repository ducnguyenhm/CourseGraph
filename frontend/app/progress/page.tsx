"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowRight } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Requirement, SharedCourses, STATE, StateBadge } from "@/components/RequirementAudit";
import { SignInPrompt } from "@/components/SignInPrompt";
import { fetchProgress, type CreditTotals, type Progress, type RequirementState } from "@/lib/api";
import { useStudent } from "@/lib/useStudent";

const STATES: RequirementState[] = ["complete", "in_progress", "planned", "outstanding"];
const STANDING: Record<string, string> = {
  first_year: "First year",
  sophomore: "Sophomore",
  junior: "Junior",
  senior: "Senior",
};

const fmt = (n: number) => (Number.isInteger(n) ? `${n}` : n.toFixed(1));
const termName = (t: string) => `${{ FA: "Fall", SP: "Spring" }[t.slice(4)] ?? t.slice(4)} ${t.slice(0, 4)}`;

export default function ProgressPage() {
  const viewer = useStudent();
  const student = viewer?.student ?? null;
  const [data, setData] = useState<Progress | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!student) return;
    setError(null);
    fetchProgress(student)
      .then(setData)
      .catch((e) => setError(String(e)));
  }, [student]);

  const names = useMemo(
    () => Object.fromEntries(data?.programs.map((p) => [p.audit.program.program_id, `${p.audit.program.name} ${p.audit.program.kind}`]) ?? []),
    [data],
  );
  const sharedCount = Object.keys(data?.shared ?? {}).length;

  return (
    <AppShell
      title="Degree progress"
      subtitle="Every declared program and the degree requirements, side by side."
    >
      {viewer && !student ? <SignInPrompt advisor={viewer.advisor} to="/progress" /> : null}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {data ? (
        <div className="mx-auto flex max-w-5xl flex-col gap-4">
          <section className="panel flex flex-col gap-3 p-5">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h2 className="text-2xl">{data.name}</h2>
              <span className="text-sm text-muted-foreground">
                {STANDING[data.class_standing]} · graduating {termName(data.expected_graduation)} · catalog {data.catalog_year}
              </span>
              <span className="ml-auto flex gap-3 text-sm">
                <Link href={`/explore?student=${data.student_key}`} className="inline-flex items-center gap-1 underline-offset-2 hover:underline">
                  Explore a program <ArrowRight className="size-3.5" />
                </Link>
                <Link href={`/planner?student=${data.student_key}`} className="inline-flex items-center gap-1 underline-offset-2 hover:underline">
                  Open the plan <ArrowRight className="size-3.5" />
                </Link>
              </span>
            </div>
            <CreditBar credits={data.credits} required={data.credits_required} label="toward the degree" />
            <div className="flex flex-wrap gap-2">
              {data.programs.map((p) => (
                <a
                  key={p.audit.program.program_id}
                  href={`#${p.audit.program.program_id}`}
                  className="flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs hover:bg-secondary"
                >
                  <StateBadge state={p.audit.root.state} compact />
                  {p.audit.program.kind === "degree" ? "B.A. degree" : names[p.audit.program.program_id]}
                </a>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              {sharedCount
                ? `${sharedCount} course${sharedCount === 1 ? "" : "s"} count toward more than one of your programs, marked ×2 below.`
                : "No course counts toward more than one of your majors and minors yet."}
            </p>
          </section>

          {data.programs.map((p) => {
            const pid = p.audit.program.program_id;
            const isDegree = p.audit.program.kind === "degree";
            const s = p.audit.summary;
            const total = s.complete + s.in_progress + s.planned + s.outstanding;
            return (
              <SharedCourses.Provider key={pid} value={{ shared: data.shared, current: pid, names }}>
                <section id={pid} className="panel flex scroll-mt-4 flex-col gap-3 p-5">
                  <div className="flex flex-wrap items-center gap-3">
                    <StateBadge state={p.audit.root.state} />
                    <h3 className="text-xl">{isDegree ? "Bachelor of Arts degree requirements" : names[pid]}</h3>
                    <Link href={`/audit?student=${data.student_key}&program=${pid}`} className="ml-auto inline-flex items-center gap-1 text-sm underline-offset-2 hover:underline">
                      Full audit <ArrowRight className="size-3.5" />
                    </Link>
                  </div>
                  <div className="flex h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
                    {STATES.map((st) =>
                      s[st] ? (
                        <div key={st} style={{ width: `${(s[st] / total) * 100}%`, background: STATE[st].fg, opacity: st === "outstanding" ? 0.3 : 1 }} />
                      ) : null,
                    )}
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                    {STATES.map((st) => (
                      <span key={st} className="flex items-center gap-1.5">
                        <StateBadge state={st} compact />
                        <span className="font-medium tabular-nums">{s[st]}</span>
                        <span className="text-muted-foreground">{STATE[st].label.toLowerCase()}</span>
                      </span>
                    ))}
                    <span className="text-muted-foreground">
                      of {total} requirements
                      {!isDegree && p.courses_open ? ` · ${p.courses_open} course${p.courses_open === 1 ? "" : "s"} still to place` : ""}
                    </span>
                  </div>
                  {!isDegree ? <Credits c={p.credits} /> : null}
                  <div className="divide-y divide-border/60 border-t border-border pt-1">
                    {p.audit.root.children.map((c, i) => (
                      <Requirement key={i} n={c} />
                    ))}
                  </div>
                </section>
              </SharedCourses.Provider>
            );
          })}
        </div>
      ) : student && !error ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : null}
    </AppShell>
  );
}

function Credits({ c }: { c: CreditTotals }) {
  return (
    <p className="text-sm text-muted-foreground">
      Credits counted here: <span className="font-medium text-foreground">{fmt(c.completed)}</span> completed
      {c.in_progress ? ` · ${fmt(c.in_progress)} in progress` : ""}
      {c.planned ? ` · ${fmt(c.planned)} planned` : ""}
    </p>
  );
}

function CreditBar({ credits, required, label }: { credits: CreditTotals; required: number; label: string }) {
  const parts: { key: RequirementState; value: number }[] = [
    { key: "complete", value: credits.completed },
    { key: "in_progress", value: credits.in_progress },
    { key: "planned", value: credits.planned },
  ];
  const max = Math.max(required, credits.completed + credits.in_progress + credits.planned);
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
        <span className="font-display text-2xl">{fmt(credits.completed)}</span>
        <span>
          of {fmt(required)} credits {label}
        </span>
        <span className="text-muted-foreground">
          {credits.in_progress ? `· ${fmt(credits.in_progress)} in progress ` : ""}
          {credits.planned ? `· ${fmt(credits.planned)} planned` : ""}
        </span>
      </div>
      <div className="flex h-3 overflow-hidden rounded-full bg-muted" role="img" aria-label={`${fmt(credits.completed)} of ${fmt(required)} credits completed`}>
        {parts.map((p) =>
          p.value ? (
            <div
              key={p.key}
              style={{
                width: `${(p.value / max) * 100}%`,
                background: STATE[p.key].fg,
                opacity: p.key === "planned" ? 0.45 : 1,
              }}
            />
          ) : null,
        )}
      </div>
    </div>
  );
}
