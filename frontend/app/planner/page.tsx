"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CircleDot,
  CircleHelp,
  GripVertical,
  MessageSquare,
  Plus,
  ShieldCheck,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { SignInPrompt } from "@/components/SignInPrompt";
import {
  ApiError,
  addComment,
  checkPlacement,
  fetchAllCourses,
  fetchComments,
  fetchPlan,
  placeCourse,
  removeTerm,
  replyToComment,
  resolveComment,
  restoreTerm,
  startDemoSession,
  unplanCourse,
  type CourseSummary,
  type PlacementCheck,
  type PlacementView,
  type PlanComment,
  type PlanView,
  type TakenView,
} from "@/lib/api";
import { DEMO_STUDENT, saveDemo } from "@/lib/session";
import { useStudent } from "@/lib/useStudent";

const MAX_LOAD_KEY = "coursegraph:max-load";
const DEFAULT_MAX_LOAD = 4.5;

const fmt = (n: number) => (Number.isInteger(n) ? `${n}` : n.toFixed(1));
const TERM_NAME: Record<string, string> = { FA: "Fall", WI: "Winter Term", SP: "Spring", MY: "May Term", SU: "Summer" };
const termName = (t: string) => `${TERM_NAME[t.slice(4)] ?? t.slice(4)} ${t.slice(0, 4)}`;
// Calendar order, as the API's term_order: a summer after its spring, a
// Winter Term after the fall before it.
const ORDER: Record<string, number> = { WI: 0, SP: 1, MY: 2, SU: 3, FA: 4 };
const termIndex = (t: string) => +t.slice(0, 4) * 5 + (ORDER[t.slice(4)] ?? 5);
// The planner's terms: fall, Winter Term, spring, May Term.
const nextTerm = (t: string) => {
  const y = +t.slice(0, 4);
  const k = t.slice(4);
  return k === "FA" ? `${y + 1}WI` : k === "WI" ? `${y}SP` : k === "SP" ? `${y}MY` : `${y}FA`;
};
// Winter and May Term take Extended Studies courses only, at most half a credit.
const isShort = (t: string) => t.endsWith("WI") || t.endsWith("MY");
// An academic year opens with its fall: Spring 2026 is in 2025–26.
const academicYear = (t: string) => +t.slice(0, 4) - (t.endsWith("FA") ? 0 : 1);
const yearName = (y: number) => `${y}–${String(y + 1).slice(2)}`;
const KIND: Record<string, string> = {
  required: "Required",
  chosen: "Assumed choice",
  prerequisite: "Prerequisite",
};

type Dragged = { course_id: string; label: string; from: string | null };
type Rejection = { check: PlacementCheck; course: Dragged; note: string };
type Notice = { tone: "ok" | "warn" | "error"; text: string };

export default function PlannerPage() {
  const viewer = useStudent();
  const session = viewer?.session ?? null;
  const student = viewer?.student ?? null;
  const [plan, setPlan] = useState<PlanView | null>(null);
  const [comments, setComments] = useState<PlanComment[]>([]);
  const [catalog, setCatalog] = useState<CourseSummary[]>([]);
  const [maxLoad, setMaxLoad] = useState(DEFAULT_MAX_LOAD);
  const [extraTerms, setExtraTerms] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [rejection, setRejection] = useState<Rejection | null>(null);
  const [dragging, setDragging] = useState<Dragged | null>(null);
  // Tap-to-place, for touch screens and keyboards: pick a course, then a term.
  const [picked, setPicked] = useState<Dragged | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const [verdicts, setVerdicts] = useState<Record<string, PlacementCheck>>({});
  const [detail, setDetail] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    try {
      const saved = Number(localStorage.getItem(MAX_LOAD_KEY));
      if (saved > 0 && saved <= 6) setMaxLoad(saved);
    } catch {}
    fetchAllCourses().then(setCatalog).catch(() => {});
  }, []);

  // Whose plan it is comes from the login (useStudent); only an advisor's
  // URL names the student, since only an advisor has more than one.
  const load = useCallback(() => {
    if (!student) return;
    fetchPlan(student, maxLoad)
      .then((p) => {
        setPlan(p);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    fetchComments(student)
      .then(setComments)
      .catch(() => setComments([]));
    // The session decides which copy of the plan comes back (a demo session's
    // or the database's), so a login or a new demo session reloads it.
  }, [student, maxLoad, session]);

  useEffect(load, [load]);
  // A placement's verdict depends on the rest of the plan; any change voids them.
  useEffect(() => setVerdicts({}), [plan]);

  const advisor = session?.account?.role === "advisor";
  // The student, logged in, on their own plan (not a demo session).
  const own = !!session?.account && session.account.student_key === student;
  const editable = !!plan?.editable;
  // The terms courses can still go in; the tray's "earliest" counts these.
  const terms = useMemo(() => {
    const all = [...(plan?.terms ?? [])];
    for (const t of extraTerms) if (!all.includes(t)) all.push(t);
    return all;
  }, [plan, extraTerms]);
  // Every academic year of the degree, one row each: the terms gone through
  // (the record, read-only) and the ones still to plan.
  const years = useMemo(() => {
    const all = new Set([
      ...(plan?.past_terms ?? []),
      ...(plan?.taken ?? []).map((t) => t.term),
      ...terms,
      ...(plan?.removed_terms ?? []),
    ]);
    const rows = new Map<number, string[]>();
    for (const t of [...all].sort((a, b) => termIndex(a) - termIndex(b))) {
      const y = academicYear(t);
      rows.set(y, [...(rows.get(y) ?? []), t]);
    }
    return [...rows.entries()];
  }, [plan, terms]);
  const takenByTerm = useMemo(() => {
    const m: Record<string, TakenView[]> = {};
    for (const t of plan?.taken ?? []) (m[t.term] ??= []).push(t);
    return m;
  }, [plan]);
  const byTerm = useMemo(() => {
    const m: Record<string, PlacementView[]> = {};
    for (const p of plan?.placements ?? []) (m[p.term] ??= []).push(p);
    return m;
  }, [plan]);
  const planned = useMemo(() => new Set(plan?.placements.map((p) => p.course_id)), [plan]);

  async function place(course: Dragged, term: string, override?: string) {
    if (!student || busy) return;
    if (course.from === term && !override) return;
    setBusy(true);
    setNotice(null);
    try {
      const next = await placeCourse(student, course.course_id, term, override, maxLoad);
      setPlan(next);
      setRejection(null);
      setPicked(null);
      const load = next.loads[term] ?? 0;
      setNotice(
        next.overloaded.includes(term)
          ? {
              tone: "warn",
              text: `${course.label} placed in ${termName(term)}, which now holds ${fmt(load)} credits, over the ${fmt(maxLoad)} limit.`,
            }
          : {
              tone: "ok",
              text: override
                ? `${course.label} recorded in ${termName(term)} with your note.`
                : `${course.label} placed in ${termName(term)}.`,
            },
      );
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setRejection({ check: e.detail as PlacementCheck, course, note: "" });
      } else {
        setNotice({ tone: "error", text: e instanceof Error ? e.message : String(e) });
      }
    } finally {
      setBusy(false);
    }
  }

  // A term the student added past graduation lives only on this page; any
  // other future term is taken out (or put back) on the stored plan.
  async function dropTerm(term: string) {
    if (!student || !plan) return;
    if (!plan.terms.includes(term)) {
      setExtraTerms((x) => x.filter((t) => t !== term));
      return;
    }
    try {
      setPlan(await removeTerm(student, term, maxLoad));
      setNotice({ tone: "ok", text: `${termName(term)} taken out of the plan. Add it back any time.` });
    } catch (e) {
      setNotice({ tone: "error", text: e instanceof Error ? e.message : String(e) });
    }
  }

  async function addBack(term: string) {
    if (!student) return;
    try {
      setPlan(await restoreTerm(student, term, maxLoad));
    } catch (e) {
      setNotice({ tone: "error", text: e instanceof Error ? e.message : String(e) });
    }
  }

  async function remove(p: PlacementView) {
    if (!student) return;
    try {
      setPlan(await unplanCourse(student, p.course_id, maxLoad));
      setNotice({ tone: "ok", text: `${p.label} taken out of the plan.` });
    } catch (e) {
      setNotice({ tone: "error", text: e instanceof Error ? e.message : String(e) });
    }
  }

  // While dragging, ask once per course and term whether it would fit, so the
  // column can say so before the drop.
  const asked = useRef(new Set<string>());
  function preview(term: string) {
    setOver(term);
    if (!dragging || !student) return;
    const k = `${dragging.course_id}@${term}`;
    if (asked.current.has(k)) return;
    asked.current.add(k);
    checkPlacement(student, dragging.course_id, term, maxLoad)
      .then((c) => setVerdicts((v) => ({ ...v, [k]: c })))
      .catch(() => {});
  }
  useEffect(() => {
    asked.current.clear();
  }, [plan]);

  const startDrag = (course: Dragged) => (e: React.DragEvent) => {
    e.dataTransfer.setData("text/plain", course.course_id);
    e.dataTransfer.effectAllowed = "move";
    setDragging(course);
  };

  const detailPlacement = plan?.placements.find((p) => p.course_id === detail) ?? null;

  return (
    <AppShell
      title="Semester planner"
      subtitle="Drag courses into terms. Every placement is checked against its prerequisites as they will stand by then."
      aside={
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <label className="flex items-center gap-2">
            <span className="text-muted-foreground">Overload above</span>
            <input
              type="number"
              min={1}
              max={6}
              step={0.5}
              value={maxLoad}
              onChange={(e) => {
                const v = Number(e.target.value);
                if (v > 0 && v <= 6) {
                  setMaxLoad(v);
                  try {
                    localStorage.setItem(MAX_LOAD_KEY, String(v));
                  } catch {}
                }
              }}
              className="w-16 rounded-md border border-border bg-surface px-2 py-1"
            />
            <span className="text-muted-foreground">credits</span>
          </label>
        </div>
      }
    >
      {viewer && !student ? <SignInPrompt advisor={viewer.advisor} to="/planner" /> : null}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {plan ? (
        <div className="flex flex-col gap-4">
          <Summary plan={plan} />

          {!editable ? <ReadOnlyBanner plan={plan} advisor={advisor} /> : null}

          {notice ? (
            <div
              role="status"
              className={`flex items-start justify-between gap-3 rounded-md border px-3 py-2 text-sm ${
                notice.tone === "ok"
                  ? "border-[var(--status-completed)] bg-[var(--status-completed-soft)]"
                  : notice.tone === "warn"
                    ? "border-warning bg-warning-soft"
                    : "border-destructive text-destructive"
              }`}
            >
              <span>{notice.text}</span>
              <button aria-label="Dismiss" onClick={() => setNotice(null)}>
                <X className="size-4" />
              </button>
            </div>
          ) : null}

          {rejection ? (
            <RejectionPanel
              rejection={rejection}
              busy={busy}
              onNote={(note) => setRejection({ ...rejection, note })}
              onCancel={() => setRejection(null)}
              onOverride={() => place(rejection.course, rejection.check.term, rejection.note)}
            />
          ) : null}

          {/* Every advisor comment, so a student sees what came in without
              opening each card; each one says which placement it is about. */}
          <CommentsBlock
            title={advisor ? "Comments and replies" : "Messages with your advisor"}
            comments={comments}
            student={plan.student_key}
            me={session?.account?.key ?? null}
            canWrite={advisor || own}
            canResolve={own}
            advisor={advisor}
            onChange={load}
          />

          <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
            {editable ? (
              <Tray
                plan={plan}
                terms={terms}
                catalog={catalog}
                planned={planned}
                picked={picked}
                onPick={(c) => setPicked(picked?.course_id === c.course_id ? null : c)}
                onDragStart={startDrag}
                onDragEnd={() => {
                  setDragging(null);
                  setOver(null);
                }}
              />
            ) : null}

            <div className={editable ? "" : "lg:col-span-2"}>
              {picked ? (
                <p className="mb-2 rounded-md bg-accent px-3 py-2 text-sm">
                  Choose a term for <b>{picked.label}</b>.{" "}
                  <button className="underline" onClick={() => setPicked(null)}>
                    Cancel
                  </button>
                </p>
              ) : null}
              <div className="flex flex-col gap-5">
                {years.map(([year, yearTerms], i) => (
                  <section key={year} aria-label={`Academic year ${yearName(year)}`}>
                    <h2 className="mb-2 text-sm font-medium text-muted-foreground">{yearName(year)}</h2>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                      {yearTerms.map((term) => {
                        const verdict = dragging ? verdicts[`${dragging.course_id}@${term}`] : undefined;
                        // A term gone through shows the record, and nothing goes in it.
                        const past = !terms.includes(term);
                        const taken = takenByTerm[term] ?? [];
                        if (plan.removed_terms.includes(term))
                          return <RemovedTerm key={term} term={term} editable={editable} onAddBack={() => addBack(term)} />;
                        return (
                          <TermColumn
                            key={term}
                            term={term}
                            graduation={plan.expected_graduation}
                            placements={byTerm[term] ?? []}
                            taken={taken}
                            past={past}
                            load={(plan.loads[term] ?? 0) + taken.reduce((n, t) => n + t.credits, 0)}
                            maxLoad={isShort(term) ? plan.short_max_load : plan.max_load}
                            overloaded={plan.overloaded.includes(term)}
                            editable={editable && !past}
                            active={over === term && !!dragging}
                            verdict={verdict}
                            picked={picked}
                            onPlaceHere={() => picked && place(picked, term)}
                            onDragOver={(e) => {
                              if (!editable || past || !dragging) return;
                              e.preventDefault();
                              if (over !== term) preview(term);
                            }}
                            onDragLeave={() => setOver((o) => (o === term ? null : o))}
                            onDrop={(e) => {
                              e.preventDefault();
                              const d = dragging;
                              setDragging(null);
                              setOver(null);
                              if (d) place(d, term);
                            }}
                            onCardDragStart={startDrag}
                            onCardDragEnd={() => {
                              setDragging(null);
                              setOver(null);
                            }}
                            onCardPick={(c) => setPicked(picked?.course_id === c.course_id ? null : c)}
                            onRemove={remove}
                            onOpen={(p) => setDetail(p.course_id)}
                            selected={detail}
                            // Any future term can be taken out once it is empty: a
                            // semester away, an internship, a May Term skipped.
                            onDeleteTerm={editable && !past ? () => dropTerm(term) : undefined}
                          />
                        );
                      })}
                      {editable && i === years.length - 1 ? (
                        <button
                          onClick={() => setExtraTerms((x) => [...x, nextTerm(terms[terms.length - 1] ?? plan.expected_graduation)])}
                          className="flex min-h-24 items-center justify-center gap-2 rounded-lg border border-dashed border-border text-sm text-muted-foreground hover:bg-secondary"
                        >
                          <Plus className="size-4" /> Add a term after {termName(terms[terms.length - 1] ?? plan.expected_graduation)}
                        </button>
                      ) : null}
                    </div>
                  </section>
                ))}
              </div>
            </div>
          </div>

          {detailPlacement ? (
            <DetailPanel
              placement={detailPlacement}
              comments={comments.filter((c) => c.course_id === detailPlacement.course_id)}
              student={plan.student_key}
              me={session?.account?.key ?? null}
              canWrite={advisor || own}
              canResolve={own}
              advisor={advisor}
              onChange={load}
              onClose={() => setDetail(null)}
            />
          ) : null}
        </div>
      ) : student && !error ? (
        <p className="text-sm text-muted-foreground">Loading the plan…</p>
      ) : null}
    </AppShell>
  );
}

function Summary({ plan }: { plan: PlanView }) {
  const total = plan.placements.reduce((s, p) => s + p.credits, 0);
  return (
    <section className="panel flex flex-wrap items-baseline gap-x-6 gap-y-2 p-4 text-sm">
      <div>
        <span className="text-xl">{plan.name}</span>
        <span className="ml-2 text-muted-foreground">
          {plan.demo ? "demo copy · " : ""}now in {plan.current_term ? termName(plan.current_term) : "—"} · graduating{" "}
          {termName(plan.expected_graduation)}
        </span>
      </div>
      <span>
        <b>{plan.placements.length}</b> courses planned, {fmt(total)} credits
      </span>
      <span className={plan.problems ? "text-destructive" : "text-muted-foreground"}>
        {plan.problems ? `${plan.problems} placement${plan.problems > 1 ? "s" : ""} with unmet prerequisites` : "No prerequisite problems"}
      </span>
      {plan.overloaded.length ? (
        <span className="text-warning">Overloaded: {plan.overloaded.map(termName).join(", ")}</span>
      ) : null}
    </section>
  );
}

function ReadOnlyBanner({ plan, advisor }: { plan: PlanView; advisor: boolean }) {
  const [busy, setBusy] = useState(false);
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-secondary px-3 py-2 text-sm">
      <span>{plan.read_only_reason ?? "This plan is read-only."}</span>
      {!advisor ? (
        <>
          <Link href="/login" className="underline underline-offset-4">
            Log in
          </Link>
          {plan.student_key === DEMO_STUDENT ? (
            <button
              disabled={busy}
              className="rounded-md bg-primary px-3 py-1 text-primary-foreground hover:opacity-90"
              onClick={async () => {
                setBusy(true);
                const { token } = await startDemoSession();
                saveDemo(token);
              }}
            >
              Try it in demo mode
            </button>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function RejectionPanel({
  rejection,
  busy,
  onNote,
  onCancel,
  onOverride,
}: {
  rejection: Rejection;
  busy: boolean;
  onNote: (s: string) => void;
  onCancel: () => void;
  onOverride: () => void;
}) {
  const { check } = rejection;
  return (
    <section role="alert" className="rounded-lg border-2 border-destructive bg-surface p-4">
      <div className="flex items-start gap-3">
        <XCircle className="mt-0.5 size-5 shrink-0 text-destructive" />
        <div className="flex-1">
          <h2 className="font-medium">
            {check.label} can&apos;t go in {termName(check.term)}
          </h2>
          {check.unmet.length ? (
            <ul className="mt-1 list-disc pl-5 text-sm">
              {check.unmet.map((u) => (
                <li key={u}>
                  Needs <b>{u}</b> first
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-sm">{check.message}</p>
          )}
          {check.overridable ? (
            <form
              className="mt-3 flex flex-col gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (rejection.note.trim()) onOverride();
              }}
            >
              <label className="text-sm text-muted-foreground" htmlFor="override-note">
                Have instructor consent or a waiver? Record it anyway with a justification.
              </label>
              <textarea
                id="override-note"
                value={rejection.note}
                onChange={(e) => onNote(e.target.value)}
                rows={2}
                placeholder="e.g. Prof. Smith agreed to waive CSC 231 (email, 14 Nov)"
                className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
              />
              <div className="flex gap-2">
                <button
                  disabled={busy || !rejection.note.trim()}
                  className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:opacity-90 disabled:opacity-50"
                >
                  <ShieldCheck className="size-4" /> Record with override
                </button>
                <button type="button" onClick={onCancel} className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-secondary">
                  Cancel
                </button>
              </div>
            </form>
          ) : (
            <button onClick={onCancel} className="mt-3 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-secondary">
              OK
            </button>
          )}
        </div>
      </div>
    </section>
  );
}

function Tray({
  plan,
  terms,
  catalog,
  planned,
  picked,
  onPick,
  onDragStart,
  onDragEnd,
}: {
  plan: PlanView;
  terms: string[];
  catalog: CourseSummary[];
  planned: Set<string>;
  picked: Dragged | null;
  onPick: (c: Dragged) => void;
  onDragStart: (c: Dragged) => (e: React.DragEvent) => void;
  onDragEnd: () => void;
}) {
  const [q, setQ] = useState("");
  // The estimate's rounds are semesters, so "earliest" names a fall or spring.
  const semesters = terms.filter((t) => t.endsWith("FA") || t.endsWith("SP"));
  // Below lg the tray sits above the terms; folded, it keeps them in reach.
  const [open, setOpen] = useState(false);
  const query = q.trim().toLowerCase();
  const found = query
    ? catalog
        .filter(
          (c) =>
            !c.retired &&
            !planned.has(c.course_id) &&
            (c.label.toLowerCase().includes(query) || c.title.toLowerCase().includes(query) || c.course_id.toLowerCase().includes(query)),
        )
        .slice(0, 12)
    : [];
  const item = (c: { course_id: string; label: string; title: string; credits?: number | null }, hint?: string) => {
    const d: Dragged = { course_id: c.course_id, label: c.label, from: null };
    return (
      <li
        key={c.course_id}
        draggable
        onDragStart={onDragStart(d)}
        onDragEnd={onDragEnd}
        className={`flex cursor-grab items-start gap-2 rounded-md border bg-surface p-2 text-sm active:cursor-grabbing ${
          picked?.course_id === c.course_id ? "border-ring ring-2 ring-ring" : "border-border"
        }`}
      >
        <GripVertical className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
        <button
          className="min-w-0 flex-1 text-left"
          onClick={() => {
            onPick(d);
            setOpen(false);
          }}
          aria-pressed={picked?.course_id === c.course_id}
        >
          <span className="font-mono font-medium">{c.label}</span>
          <span className="block truncate text-xs text-muted-foreground">{c.title}</span>
          {hint ? <span className="block text-[11px] text-muted-foreground">{hint}</span> : null}
        </button>
      </li>
    );
  };
  return (
    <aside className="panel flex flex-col gap-3 self-start p-3 lg:sticky lg:top-4">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex items-center justify-between text-sm font-medium lg:hidden"
      >
        Add courses ({plan.suggestions.length} still needed)
        <Plus className={`size-4 transition-transform ${open ? "rotate-45" : ""}`} />
      </button>
      <div className={`${open ? "flex" : "hidden"} flex-col gap-3 lg:flex`}>
      <div>
        <h2 className="text-sm font-medium">Still needed</h2>
        <p className="text-xs text-muted-foreground">From the semester estimate, not yet in the plan. Drag one into a term, or tap it and then a term.</p>
      </div>
      {plan.suggestions.length ? (
        <ul className="flex max-h-[45vh] flex-col gap-1.5 overflow-y-auto">
          {plan.suggestions.map((s) =>
            item(s, `${KIND[s.kind] ?? s.kind}${semesters[s.round - 1] ? ` · earliest ${termName(semesters[s.round - 1])}` : ""}`),
          )}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">Nothing the estimate needs is missing from the plan.</p>
      )}
      <div className="border-t border-border pt-3">
        <label className="text-sm font-medium" htmlFor="course-search">
          Any course
        </label>
        <input
          id="course-search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="CSC 440, statistics…"
          className="mt-1 w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm"
        />
        {found.length ? <ul className="mt-2 flex flex-col gap-1.5">{found.map((c) => item({ ...c, credits: c.credits_max }))}</ul> : null}
      </div>
      </div>
    </aside>
  );
}

function TermColumn(props: {
  term: string;
  graduation: string;
  placements: PlacementView[];
  taken: TakenView[];
  past: boolean;
  load: number;
  maxLoad: number;
  overloaded: boolean;
  editable: boolean;
  active: boolean;
  verdict?: PlacementCheck;
  picked: Dragged | null;
  selected: string | null;
  onPlaceHere: () => void;
  onDragOver: (e: React.DragEvent) => void;
  onDragLeave: () => void;
  onDrop: (e: React.DragEvent) => void;
  onCardDragStart: (c: Dragged) => (e: React.DragEvent) => void;
  onCardDragEnd: () => void;
  onCardPick: (c: Dragged) => void;
  onRemove: (p: PlacementView) => void;
  onOpen: (p: PlacementView) => void;
  onDeleteTerm?: () => void;
}) {
  const { term, verdict, active } = props;
  const after = termIndex(term) > termIndex(props.graduation);
  const ring = active
    ? verdict
      ? verdict.ok
        ? "border-[var(--status-completed)] ring-2 ring-[var(--status-completed)]"
        : "border-destructive ring-2 ring-destructive"
      : "border-ring ring-2 ring-ring"
    : props.overloaded
      ? "border-warning"
      : "border-border";
  return (
    <section
      onDragOver={props.onDragOver}
      onDragLeave={props.onDragLeave}
      onDrop={props.onDrop}
      aria-label={termName(term)}
      className={`flex min-h-40 flex-col rounded-lg border bg-surface transition-shadow ${ring}`}
    >
      <header className={`flex items-baseline justify-between gap-2 border-b px-3 py-2 ${props.overloaded ? "border-warning bg-warning-soft" : "border-border"}`}>
        <h3 className="font-medium">
          {termName(term)}
          {after ? <span className="ml-1 text-xs font-normal text-muted-foreground">after graduation</span> : null}
          {isShort(term) && !props.past ? <span className="block text-xs font-normal text-muted-foreground">Extended Studies only</span> : null}
        </h3>
        <span className="flex items-center gap-2">
          <span className={`text-xs tabular-nums ${props.overloaded ? "font-medium text-warning" : "text-muted-foreground"}`}>
            {props.past ? `${fmt(props.load)} cr` : `${fmt(props.load)} / ${fmt(props.maxLoad)} cr`}
          </span>
          {props.onDeleteTerm ? (
            <button
              onClick={props.onDeleteTerm}
              disabled={props.placements.length > 0}
              aria-label={`Remove ${termName(term)}`}
              title={props.placements.length ? "Move or remove its courses first" : `Remove ${termName(term)}`}
              className="text-muted-foreground hover:text-destructive disabled:opacity-30 disabled:hover:text-muted-foreground"
            >
              <Trash2 className="size-3.5" />
            </button>
          ) : null}
        </span>
      </header>
      {props.overloaded ? (
        <p className="flex items-center gap-1.5 bg-warning-soft px-3 pb-2 text-xs text-warning">
          <AlertTriangle className="size-3.5" /> Over the {fmt(props.maxLoad)}-credit limit
        </p>
      ) : null}
      {active && verdict ? (
        <p className={`px-3 pt-2 text-xs ${verdict.ok ? "text-[var(--status-completed)]" : "text-destructive"}`}>
          {verdict.ok
            ? verdict.overloaded
              ? `Fits, but makes ${fmt(verdict.load)} credits`
              : "Prerequisites met by then"
            : verdict.unmet.length
              ? `Needs ${verdict.unmet.join("; ")}`
              : verdict.message}
        </p>
      ) : null}
      <ul className="flex flex-1 flex-col gap-2 p-2">
        {props.taken.map((t) => (
          <TakenCard key={t.course_id} t={t} />
        ))}
        {props.placements.map((p) => (
          <Card
            key={p.course_id}
            p={p}
            editable={props.editable}
            selected={props.selected === p.course_id}
            picked={props.picked?.course_id === p.course_id}
            onDragStart={props.onCardDragStart({ course_id: p.course_id, label: p.label, from: term })}
            onDragEnd={props.onCardDragEnd}
            onPick={() => props.onCardPick({ course_id: p.course_id, label: p.label, from: term })}
            onRemove={() => props.onRemove(p)}
            onOpen={() => props.onOpen(p)}
          />
        ))}
        {!props.placements.length && !props.taken.length && !props.picked ? (
          <li className="flex flex-1 items-center justify-center rounded-md border border-dashed border-border p-3 text-center text-xs text-muted-foreground">
            {props.past ? "No courses" : props.editable ? "Drop a course here" : "Nothing planned"}
          </li>
        ) : null}
      </ul>
      {props.picked && props.editable && props.picked.from !== term ? (
        <button onClick={props.onPlaceHere} className="m-2 mt-0 rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:opacity-90">
          Place {props.picked.label} here
        </button>
      ) : null}
    </section>
  );
}

// A term taken out of the plan keeps its place in the year, so it is easy to
// see what was skipped and to put it back.
function RemovedTerm({ term, editable, onAddBack }: { term: string; editable: boolean; onAddBack: () => void }) {
  return (
    <section
      aria-label={`${termName(term)}, removed`}
      className="flex min-h-24 flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-border p-3 text-center text-sm text-muted-foreground"
    >
      <span>
        <span className="line-through">{termName(term)}</span> · not taking courses
      </span>
      {editable ? (
        <button onClick={onAddBack} className="inline-flex items-center gap-1 text-xs underline underline-offset-4 hover:text-foreground">
          <Plus className="size-3.5" /> Add it back
        </button>
      ) : null}
    </section>
  );
}

// A course from the record: done or under way, so it neither moves nor goes.
function TakenCard({ t }: { t: TakenView }) {
  const done = t.status === "completed";
  const Icon = done ? CheckCircle2 : CircleDot;
  const tone = done ? "text-[var(--status-completed)]" : "text-[var(--status-planned)]";
  return (
    <li className={`rounded-md border border-l-4 bg-secondary/40 p-2 text-sm ${done ? "border-l-[var(--status-completed)]" : "border-l-[var(--status-planned)]"}`}>
      <div className="flex items-baseline gap-1.5">
        <Icon className={`size-3.5 shrink-0 self-center ${tone}`} aria-hidden />
        <span className="font-mono font-medium">{t.label}</span>
        <span className="text-xs text-muted-foreground">{fmt(t.credits)} cr</span>
      </div>
      <p className="truncate text-xs text-muted-foreground">{t.title}</p>
      <p className={`text-xs ${tone}`}>{done ? "Completed" : "In progress"}</p>
    </li>
  );
}

function Card({
  p,
  editable,
  selected,
  picked,
  onDragStart,
  onDragEnd,
  onPick,
  onRemove,
  onOpen,
}: {
  p: PlacementView;
  editable: boolean;
  selected: boolean;
  picked: boolean;
  onDragStart: (e: React.DragEvent) => void;
  onDragEnd: () => void;
  onPick: () => void;
  onRemove: () => void;
  onOpen: () => void;
}) {
  const state = p.ok ? (p.confirm.length ? "confirm" : "ok") : p.override ? "override" : "problem";
  const edge = {
    ok: "border-l-[var(--status-planned)]",
    confirm: "border-l-[var(--status-eligible)]",
    override: "border-l-warning",
    problem: "border-l-destructive",
  }[state];
  const Icon = { ok: CheckCircle2, confirm: CircleHelp, override: ShieldCheck, problem: XCircle }[state];
  const tone = {
    ok: "text-[var(--status-planned)]",
    confirm: "text-[var(--status-eligible)]",
    override: "text-warning",
    problem: "text-destructive",
  }[state];
  return (
    <li
      draggable={editable}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      className={`rounded-md border border-l-4 bg-background p-2 text-sm ${edge} ${
        selected || picked ? "border-ring ring-2 ring-ring" : "border-border"
      } ${editable ? "cursor-grab active:cursor-grabbing" : ""}`}
    >
      <div className="flex items-start gap-2">
        <Icon className={`mt-0.5 size-4 shrink-0 ${tone}`} aria-label={state} />
        <button onClick={onOpen} className="min-w-0 flex-1 text-left">
          <span className="font-mono font-medium">{p.label}</span>
          <span className="ml-1 text-xs text-muted-foreground">{fmt(p.credits)} cr</span>
          <span className="block truncate text-xs text-muted-foreground">{p.title}</span>
        </button>
        {p.open_comments ? (
          <span className="inline-flex items-center gap-0.5 rounded bg-accent px-1 text-xs" title="Open advisor comments">
            <MessageSquare className="size-3" />
            {p.open_comments}
          </span>
        ) : null}
        {editable ? (
          <button onClick={onRemove} aria-label={`Remove ${p.label}`} className="text-muted-foreground hover:text-destructive">
            <X className="size-4" />
          </button>
        ) : null}
      </div>
      {state === "problem" ? <p className="mt-1 text-xs text-destructive">Needs {p.unmet.join("; ")}</p> : null}
      {state === "override" ? <p className="mt-1 text-xs text-warning">Override: {p.override}</p> : null}
      {state === "confirm" ? <p className="mt-1 text-xs text-muted-foreground">To confirm: {p.confirm.join("; ")}</p> : null}
      {editable ? (
        <button onClick={onPick} className="mt-1 text-xs text-muted-foreground underline-offset-2 hover:underline">
          {picked ? "Cancel move" : "Move…"}
        </button>
      ) : null}
    </li>
  );
}

function DetailPanel({
  placement: p,
  comments,
  student,
  me,
  canWrite,
  canResolve,
  advisor,
  onChange,
  onClose,
}: {
  placement: PlacementView;
  comments: PlanComment[];
  student: string;
  me: string | null;
  canWrite: boolean;
  canResolve: boolean;
  advisor: boolean;
  onChange: () => void;
  onClose: () => void;
}) {
  return (
    <section className="panel p-4" aria-label={`${p.label} details`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg">
            <span className="font-mono">{p.label}</span> {p.title}
          </h2>
          <p className="text-sm text-muted-foreground">
            {termName(p.term)} · {fmt(p.credits)} credit{p.credits === 1 ? "" : "s"} ·{" "}
            <Link href={`/courses/${p.course_id}`} className="underline underline-offset-2">
              catalog entry
            </Link>
          </p>
        </div>
        <button onClick={onClose} aria-label="Close">
          <X className="size-4" />
        </button>
      </div>
      <p className="mt-2 text-sm">
        {p.ok
          ? p.confirm.length
            ? `Prerequisites met, pending: ${p.confirm.join("; ")}.`
            : "Prerequisites met by this term."
          : p.message}
      </p>
      {p.override ? <p className="mt-1 text-sm text-warning">Recorded with override: “{p.override}”</p> : null}
      <CommentsBlock
        title={`Comments on ${p.label}`}
        comments={comments}
        student={student}
        courseId={p.course_id}
        me={me}
        canWrite={canWrite}
        canResolve={canResolve}
        advisor={advisor}
        onChange={onChange}
        always
      />
    </section>
  );
}

// Each comment opens a conversation; the student and their advisor both
// answer in it, and the student marks it resolved.
function CommentsBlock({
  title,
  comments,
  student,
  courseId,
  me,
  canWrite,
  canResolve,
  advisor,
  onChange,
  always = false,
}: {
  title: string;
  comments: PlanComment[];
  student: string;
  courseId?: string;
  me: string | null;
  canWrite: boolean;
  canResolve: boolean;
  advisor: boolean;
  onChange: () => void;
  always?: boolean;
}) {
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const roots = comments.filter((c) => c.parent_id === null);
  const answers = (id: number) => comments.filter((c) => c.parent_id === id);
  if (!comments.length && !canWrite && !always) return null;
  return (
    <section className={always ? "mt-4 border-t border-border pt-3" : "panel p-4"}>
      <h2 className="flex items-center gap-2 text-sm font-medium">
        <MessageSquare className="size-4" /> {title}
      </h2>
      {roots.length ? (
        <ul className="mt-2 flex flex-col gap-2">
          {roots.map((c) => (
            <Conversation
              key={c.id}
              root={c}
              answers={answers(c.id)}
              me={me}
              canWrite={canWrite}
              canResolve={canResolve}
              onChange={onChange}
            />
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-sm text-muted-foreground">No messages yet.</p>
      )}
      {canWrite ? (
        <form
          className="mt-3 flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            addComment(student, body, courseId).then(
              () => {
                setBody("");
                setError(null);
                onChange();
              },
              (e) => setError(e instanceof Error ? e.message : String(e)),
            );
          }}
        >
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={2}
            aria-label={advisor ? "New comment" : "New message to your advisor"}
            placeholder={
              advisor
                ? courseId
                  ? "Comment on this placement…"
                  : "Comment on the plan as a whole…"
                : courseId
                  ? "Ask your advisor about this placement…"
                  : "Message your advisor…"
            }
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
          />
          <button disabled={!body.trim()} className="self-start rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:opacity-90 disabled:opacity-50">
            {advisor ? "Add comment" : "Send"}
          </button>
        </form>
      ) : null}
      {error ? <p className="mt-1 text-sm text-destructive">{error}</p> : null}
    </section>
  );
}

function Conversation({
  root,
  answers,
  me,
  canWrite,
  canResolve,
  onChange,
}: {
  root: PlanComment;
  answers: PlanComment[];
  me: string | null;
  canWrite: boolean;
  canResolve: boolean;
  onChange: () => void;
}) {
  const [reply, setReply] = useState("");
  const [error, setError] = useState<string | null>(null);
  const who = (c: PlanComment) => (c.author === me ? "You" : c.author_name);
  return (
    <li className={`rounded-md border border-border p-2 text-sm ${root.resolved ? "opacity-60" : ""}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-medium">{who(root)}</span>
        <span className="text-xs text-muted-foreground">
          {new Date(root.created).toLocaleString()}
          {root.term ? ` · on ${root.label} in ${termName(root.term)}` : ""}
        </span>
      </div>
      <p className="mt-1 whitespace-pre-wrap">{root.body}</p>
      {answers.length ? (
        <ul className="mt-2 flex flex-col gap-1.5 border-l-2 border-border pl-3">
          {answers.map((a) => (
            <li key={a.id}>
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="font-medium">{who(a)}</span>
                <span className="text-xs text-muted-foreground">{new Date(a.created).toLocaleString()}</span>
              </div>
              <p className="whitespace-pre-wrap">{a.body}</p>
            </li>
          ))}
        </ul>
      ) : null}
      {root.resolved ? (
        <p className="mt-1 text-xs text-muted-foreground">Resolved</p>
      ) : (
        <div className="mt-2 flex flex-col gap-1.5">
          {canWrite ? (
            <form
              className="flex flex-wrap items-start gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                replyToComment(root.id, reply).then(
                  () => {
                    setReply("");
                    setError(null);
                    onChange();
                  },
                  (err) => setError(err instanceof Error ? err.message : String(err)),
                );
              }}
            >
              <input
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                placeholder="Reply…"
                aria-label={`Reply to ${who(root)}`}
                className="min-w-0 flex-1 rounded-md border border-border bg-surface px-2.5 py-1 text-sm"
              />
              <button disabled={!reply.trim()} className="rounded-md border border-border px-2.5 py-1 text-sm hover:bg-secondary disabled:opacity-50">
                Reply
              </button>
            </form>
          ) : null}
          {canResolve ? (
            <button
              className="self-start text-xs underline underline-offset-2"
              onClick={() => resolveComment(root.id).then(onChange, (err) => setError(String(err)))}
            >
              Mark resolved
            </button>
          ) : null}
        </div>
      )}
      {error ? <p className="mt-1 text-xs text-destructive">{error}</p> : null}
    </li>
  );
}
