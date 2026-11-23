"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { RULE_LABEL, Requirement, STATE, StateBadge } from "@/components/RequirementAudit";
import { SemesterEstimate } from "@/components/SemesterEstimate";
import { SignInPrompt } from "@/components/SignInPrompt";
import {
  fetchAudit,
  fetchPrograms,
  type Audit,
  type AuditNode,
  type ProgramSummary,
  type RequirementState,
} from "@/lib/api";
import { DEMO_STUDENT } from "@/lib/session";
import { useStudent } from "@/lib/useStudent";

const DEFAULT_PROGRAM = "MAJOR-CSC";
const KIND_ORDER = { major: 0, minor: 1, degree: 2 } as const;

export default function AuditPage() {
  const [programs, setPrograms] = useState<ProgramSummary[]>([]);
  const [program, setProgram] = useState<string | null>(null);
  const viewer = useStudent();
  const student = viewer?.student ?? null;
  const [audit, setAudit] = useState<Audit | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    setProgram(q.get("program")?.toUpperCase() ?? DEFAULT_PROGRAM);
    fetchPrograms()
      .then((ps) => setPrograms([...ps].sort((a, b) => KIND_ORDER[a.kind] - KIND_ORDER[b.kind])))
      .catch(() => setPrograms([]));
  }, []);

  useEffect(() => {
    if (!program || !student) return;
    const q = new URLSearchParams({ program });
    if (viewer?.advisor) q.set("student", student);
    window.history.replaceState(null, "", `?${q}`);
    setError(null);
    fetchAudit(student, program)
      .then(setAudit)
      .catch((e) => {
        setAudit(null);
        setError(String(e));
      });
  }, [program, student, viewer?.advisor]);

  return (
    <AppShell
      title="Requirement audit"
      subtitle={
        audit
          ? `${audit.student_key === DEMO_STUDENT ? "Demo student" : audit.student_key} · ${audit.program.name} ${audit.program.kind} · catalog ${audit.catalog_year}`
          : ""
      }
      aside={
        <div className="flex items-center gap-2">
        <select
          value={program ?? ""}
          onChange={(e) => setProgram(e.target.value)}
          aria-label="Program"
          className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm"
        >
          {programs.map((p) => (
            <option key={p.program_id} value={p.program_id}>
              {p.kind === "degree" ? `${p.name} degree requirements` : `${p.name} ${p.kind}`}
            </option>
          ))}
        </select>
        </div>
      }
    >
      {viewer && !student ? <SignInPrompt advisor={viewer.advisor} to="/audit" /> : null}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {audit ? (
        <div className="mx-auto flex max-w-4xl flex-col gap-4">
          {/* Student-wide: every declared program plus the degree. */}
          <SemesterEstimate student={audit.student_key} />
          <Summary audit={audit} />
          <section className="panel px-5 py-2">
            <div className="divide-y divide-border/60">
              {audit.root.children.map((c, i) => (
                <Requirement key={i} n={c} />
              ))}
            </div>
          </section>
        </div>
      ) : student && !error ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : null}
    </AppShell>
  );
}

function leafRuleTypes(n: AuditNode, out = new Set<string>()) {
  if (!n.children.length) out.add(n.rule_type);
  n.children.forEach((c) => leafRuleTypes(c, out));
  return out;
}

function Summary({ audit }: { audit: Audit }) {
  const { summary, root } = audit;
  const total = summary.complete + summary.in_progress + summary.planned + summary.outstanding;
  const ruleTypes = leafRuleTypes(root);
  return (
    <section className="panel flex flex-col gap-3 p-5">
      <div className="flex flex-wrap items-center gap-3">
        <StateBadge state={root.state} />
        <h2 className="text-xl">{root.label}</h2>
        <span
          className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground"
          title="Declared programs are on the student's record; others are evaluated as if added."
        >
          {audit.program.kind === "degree"
            ? "applies to every B.A. student"
            : audit.declared
              ? "declared"
              : "not declared · what-if"}
        </span>
      </div>

      {/* One bar per requirement, in state order, so the split reads at a glance. */}
      <div className="flex h-2.5 overflow-hidden rounded-full bg-muted" aria-hidden>
        {(["complete", "in_progress", "planned", "outstanding"] as RequirementState[]).map((st) =>
          summary[st] ? (
            <div
              key={st}
              style={{ width: `${(summary[st] / total) * 100}%`, background: STATE[st].fg, opacity: st === "outstanding" ? 0.35 : 1 }}
            />
          ) : null,
        )}
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
        {(["complete", "in_progress", "planned", "outstanding"] as RequirementState[]).map((st) => (
          <span key={st} className="flex items-center gap-1.5">
            <StateBadge state={st} compact />
            <span className="tabular-nums font-medium">{summary[st]}</span>
            <span className="text-muted-foreground">{STATE[st].label.toLowerCase()}</span>
          </span>
        ))}
        <span className="text-muted-foreground">of {total} requirements</span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <span>Rule types here:</span>
        {(["specific_course", "n_from_set", "credit_minimum", "attribute_count"] as const).map((r) => (
          <span
            key={r}
            className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${
              ruleTypes.has(r) ? "bg-secondary text-foreground" : "bg-muted text-muted-foreground/50 line-through"
            }`}
          >
            {RULE_LABEL[r]}
          </span>
        ))}
      </div>
    </section>
  );
}
