"use client";

import Link from "next/link";
import { createContext, useContext, useState } from "react";
import { CalendarClock, Check, ChevronRight, Circle, CircleDot } from "lucide-react";
import type { AuditNode, RequirementState } from "@/lib/api";

// Same rule as the graph: state is never colour alone. Each has its own
// border style and icon too.
export const STATE: Record<
  RequirementState,
  { label: string; fg: string; bg: string; border: string; Icon: typeof Check }
> = {
  complete: {
    label: "Complete",
    fg: "var(--status-completed)",
    bg: "var(--status-completed-soft)",
    border: "2px solid var(--status-completed)",
    Icon: Check,
  },
  in_progress: {
    label: "In progress",
    fg: "var(--status-planned)",
    bg: "var(--status-planned-soft)",
    border: "1px solid var(--status-planned)",
    Icon: CircleDot,
  },
  planned: {
    label: "Planned",
    fg: "var(--status-planned)",
    bg: "var(--status-planned-soft)",
    border: "1px dashed var(--status-planned)",
    Icon: CalendarClock,
  },
  outstanding: {
    label: "Outstanding",
    fg: "var(--status-locked)",
    bg: "var(--status-locked-soft)",
    border: "1px dotted var(--status-locked)",
    Icon: Circle,
  },
};

export const RULE_LABEL: Record<AuditNode["rule_type"], string> = {
  all_of: "all of",
  any_of: "one of",
  specific_course: "specific course",
  n_from_set: "n from a set",
  credit_minimum: "credit minimum",
  attribute_count: "attribute count",
};

const name = (cid: string) => cid.replace("-", " ");

/** Courses counting toward more than one program, and which program's tree
 *  is being drawn, so a course shared with another program can say so. */
export const SharedCourses = createContext<{
  shared: Record<string, string[]>;
  current?: string;
  names?: Record<string, string>;
}>({ shared: {} });
const num = (n: number) => (Number.isInteger(n) ? `${n}` : n.toFixed(1));

export function StateBadge({ state, compact = false }: { state: RequirementState; compact?: boolean }) {
  const s = STATE[state];
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium"
      style={{ color: s.fg, background: s.bg, border: s.border }}
      title={s.label}
    >
      <s.Icon className="size-3" aria-hidden />
      {compact ? <span className="sr-only">{s.label}</span> : s.label}
    </span>
  );
}

function fallbackLabel(n: AuditNode) {
  if (n.rule_type === "specific_course") return name(String(n.spec.course_id));
  if (n.rule_type === "attribute_count") return `${n.spec.n} × ${n.spec.attribute}`;
  if (n.rule_type === "credit_minimum") return `${n.spec.credits} credits`;
  return RULE_LABEL[n.rule_type];
}

function metric(n: AuditNode): string {
  if (n.children.length) {
    const used = n.rule_type === "any_of" ? n.children.filter((c) => c.chosen) : n.children;
    const met = used.filter((c) => c.state !== "outstanding").length;
    if (n.rule_type === "any_of") return met ? "one branch met" : `one of ${n.children.length}`;
    return `${met} of ${used.length} met`;
  }
  if (n.rule_type === "credit_minimum") return `${num(n.have)} / ${num(n.need)} credits`;
  if (n.rule_type === "specific_course") return "";
  return `${num(Math.min(n.have, n.need))} / ${num(n.need)}`;
}

function Courses({ ids, max = 8 }: { ids: string[]; max?: number }) {
  const [all, setAll] = useState(false);
  const { shared, current, names } = useContext(SharedCourses);
  const shown = all ? ids : ids.slice(0, max);
  return (
    <span className="flex flex-wrap items-center gap-1">
      {shown.map((c) => {
        const others = (shared[c] ?? []).filter((p) => p !== current);
        return (
          <Link
            key={c}
            href={`/courses/${c}`}
            title={others.length ? `Also counts toward ${others.map((o) => names?.[o] ?? o).join(", ")}` : undefined}
            className="inline-flex items-center gap-1 rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-[11px] hover:bg-secondary"
          >
            {name(c)}
            {others.length ? (
              <span
                className="rounded bg-gold px-1 font-sans text-[9px] font-semibold text-gold-foreground"
                aria-label={`counts toward ${others.length + 1} programs`}
              >
                ×{others.length + 1}
              </span>
            ) : null}
          </Link>
        );
      })}
      {ids.length > max ? (
        <button
          type="button"
          onClick={() => setAll(!all)}
          className="px-1 text-[11px] text-muted-foreground underline-offset-2 hover:underline"
        >
          {all ? "fewer" : max === 0 ? `${ids.length} courses · show` : `+${ids.length - max} more`}
        </button>
      ) : null}
    </span>
  );
}

function Leaf({ n }: { n: AuditNode }) {
  const { shared, current } = useContext(SharedCourses);
  const sharedHere = (c: string) => (shared[c] ?? []).some((p) => p !== current);
  const scope = n.spec.scope === "program" ? "of the courses placed above" : null;
  return (
    <div className={`flex flex-col gap-1.5 py-2.5 ${n.chosen ? "" : "opacity-55"}`}>
      <div className="flex flex-wrap items-center gap-2">
        <StateBadge state={n.state} compact />
        <span className="text-sm font-medium">{n.label || fallbackLabel(n)}</span>
        {metric(n) ? <span className="text-xs tabular-nums text-muted-foreground">{metric(n)}</span> : null}
        <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
          {RULE_LABEL[n.rule_type]}
          {n.spec.exclusive ? " · exclusive" : ""}
        </span>
        {!n.chosen ? <span className="text-[11px] italic text-muted-foreground">alternative, not used</span> : null}
      </div>
      {/* "CSC 121 — met by CSC 121" says nothing; a substitute (CSC 122 for
          CSC 235, MATH 136 for MATH 151) is worth showing. */}
      {n.applied.length &&
      !(n.rule_type === "specific_course" && n.applied[0] === n.spec.course_id && !sharedHere(n.applied[0])) ? (
        <div className="flex flex-wrap items-baseline gap-2 pl-7 text-xs text-muted-foreground">
          <span>{n.in_courses ? "met by" : `counted${scope ? ` (${scope})` : ""}`}</span>
          <Courses ids={n.applied} max={n.rule_type === "credit_minimum" && !scope ? 0 : 8} />
        </div>
      ) : null}
      {n.state === "outstanding" && n.chosen && n.rule_type !== "specific_course" ? (
        <div className="flex flex-wrap items-baseline gap-2 pl-7 text-xs text-muted-foreground">
          {n.options.length ? (
            <>
              <span>could count</span>
              <Courses ids={n.options} max={6} />
            </>
          ) : n.rule_type === "credit_minimum" && !n.spec.subject && !n.spec.attribute && !scope ? (
            <span>any {num(n.remaining)} more credits beyond the record and plan</span>
          ) : (
            <span>no course in the loaded catalog counts here</span>
          )}
        </div>
      ) : null}
      {n.notes ? <p className="pl-7 text-xs text-muted-foreground/80">{n.notes}</p> : null}
    </div>
  );
}

export function Requirement({ n, depth = 0 }: { n: AuditNode; depth?: number }) {
  const [open, setOpen] = useState(true);
  if (!n.children.length) return <Leaf n={n} />;
  return (
    <div className={n.chosen ? "" : "opacity-55"}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full flex-wrap items-center gap-2 py-2.5 text-left"
      >
        <ChevronRight className={`size-4 shrink-0 transition-transform ${open ? "rotate-90" : ""}`} aria-hidden />
        <StateBadge state={n.state} compact />
        <span className={depth === 0 ? "text-base font-semibold" : "text-sm font-semibold"}>
          {n.label || fallbackLabel(n)}
        </span>
        <span className="text-xs tabular-nums text-muted-foreground">{metric(n)}</span>
        {n.rule_type === "any_of" ? (
          <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">one of</span>
        ) : null}
      </button>
      {open ? (
        <div className="ml-2 border-l border-border pl-4">
          {n.notes ? <p className="pb-1 text-xs text-muted-foreground/80">{n.notes}</p> : null}
          <div className="divide-y divide-border/60">
            {n.children.map((c, i) => (
              <Requirement key={i} n={c} depth={depth + 1} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
