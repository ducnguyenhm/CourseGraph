"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { PrereqTree } from "@/components/PrereqTree";
import {
  credits,
  fetchChain,
  fetchCourse,
  fetchGraph,
  fetchProgramOrder,
  fetchPrograms,
  type Chain,
  type ChainCourse,
  type CourseDetail,
  type GraphPayload,
  type ProgramOrder,
  type ProgramSummary,
  type Status,
} from "@/lib/api";
import { useStudent } from "@/lib/useStudent";

const NODE_W = 150;
const NODE_H = 52;
const COL_GAP = 110;
const ROW_GAP = 22;
const SUBCOL_GAP = 16;
const MAX_ROWS = 12;

const DEPARTMENTS = ["CSC", "MATH", "ECON"];

// Colour is never the only signal: each status also has its own border style
// and icon, as the proposal's accessibility requirement asks.
const STATUS: Record<
  Status,
  { label: string; fill: string; stroke: string; dash?: string; width: number; icon: string }
> = {
  completed: {
    label: "Completed",
    fill: "var(--status-completed-soft)",
    stroke: "var(--status-completed)",
    width: 2.5,
    icon: "✓",
  },
  planned: {
    label: "Planned or in progress",
    fill: "var(--status-planned-soft)",
    stroke: "var(--status-planned)",
    dash: "6 3",
    width: 2,
    icon: "◷",
  },
  eligible: {
    label: "Eligible now",
    fill: "var(--status-eligible-soft)",
    stroke: "var(--status-eligible)",
    width: 2,
    icon: "○",
  },
  locked: {
    label: "Locked",
    fill: "var(--status-locked-soft)",
    stroke: "var(--status-locked)",
    dash: "2 3",
    width: 1.5,
    icon: "lock",
  },
};

function StatusIcon({ status, x, y }: { status: Status; x: number; y: number }) {
  const s = STATUS[status];
  if (s.icon === "lock")
    return (
      <g transform={`translate(${x - 5} ${y - 10})`} aria-hidden>
        <rect x="0" y="5" width="10" height="7" rx="1.5" fill={s.stroke} />
        <path d="M2.5 5 V3.5 a2.5 2.5 0 0 1 5 0 V5" fill="none" stroke={s.stroke} strokeWidth="1.4" />
      </g>
    );
  return (
    <text x={x} y={y} textAnchor="middle" className="text-[12px] font-semibold" fill={s.stroke} aria-hidden>
      {s.icon}
    </text>
  );
}

export default function GraphPage() {
  // Starts empty: nothing is drawn until departments are chosen.
  const [subjects, setSubjects] = useState<string[]>([]);
  const [program, setProgram] = useState("");
  const [programs, setPrograms] = useState<ProgramSummary[]>([]);
  // The catalog graph is public; statuses are the logged-in student's own.
  const viewer = useStudent();
  const student = viewer?.student ?? null;
  const viewerReady = viewer !== null;
  const [withStudent, setWithStudent] = useState(true);
  const [showOrder, setShowOrder] = useState(false);
  const [order, setOrder] = useState<ProgramOrder | null>(null);
  // The view lives in the address bar (?program=MAJOR-CSC&order=1&course=CSC-340),
  // so a demo can open straight into it and a reload does not lose it.
  const [ready, setReady] = useState(false);
  const pendingCourse = useRef<string | null>(null);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const [payload, setPayload] = useState<GraphPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [chain, setChain] = useState<Chain | null>(null);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  // Below md a pannable SVG of a hundred courses is unusable; the page swaps
  // it for a list by prerequisite depth that keeps status and the chain.
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 767px)");
    const update = () => setNarrow(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const depts = q.get("dept")?.split(",").filter((d) => DEPARTMENTS.includes(d));
    if (depts?.length) setSubjects(DEPARTMENTS.filter((d) => depts.includes(d)));
    if (q.get("program")) setProgram(q.get("program")!.toUpperCase());
    if (q.get("order") === "1") setShowOrder(true);
    if (q.get("progress") === "0") setWithStudent(false);
    pendingCourse.current = q.get("course")?.toUpperCase() ?? null;
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    const q = new URLSearchParams();
    if (subjects.length) q.set("dept", subjects.join(","));
    if (program) q.set("program", program);
    if (program && showOrder) q.set("order", "1");
    if (viewer?.advisor && viewer.student) q.set("student", viewer.student);
    if (!withStudent) q.set("progress", "0");
    if (selected) q.set("course", selected);
    const qs = q.toString();
    window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
  }, [ready, subjects, program, showOrder, withStudent, selected, viewer?.advisor, viewer?.student]);

  useEffect(() => {
    if (!ready || !viewerReady) return;
    setPayload(null);
    setSelected(null);
    if (!subjects.length) return;
    fetchGraph({
      // All departments ticked means no filter, which also keeps stubs out.
      subjects: subjects.length === DEPARTMENTS.length ? undefined : subjects,
      program: program || undefined,
      student: (withStudent && student) || undefined,
    })
      .then((p) => {
        setPayload(p);
        const wanted = pendingCourse.current;
        pendingCourse.current = null;
        if (wanted && p.nodes.some((n) => n.id === wanted)) setSelected(wanted);
      })
      .catch((e) => setError(String(e)));
  }, [ready, subjects, program, withStudent, student, viewerReady]);

  useEffect(() => {
    // The degree requirements name no courses, so there is nothing to draw.
    fetchPrograms()
      .then((ps) => setPrograms(ps.filter((p) => p.kind !== "degree")))
      .catch(() => setPrograms([]));
  }, []);

  useEffect(() => {
    setOrder(null);
    if (!program || !showOrder) return;
    fetchProgramOrder(program).then(setOrder).catch(() => setOrder(null));
  }, [program, showOrder]);

  // Course -> the term ("round") the program order puts it in.
  const roundOf = useMemo(() => {
    const m = new Map<string, number>();
    order?.rounds.forEach((r, i) => r.forEach((c) => m.set(c.course_id, i + 1)));
    return m;
  }, [order]);

  // Prerequisites that exist but sit outside the current filter.
  const externalIn = useMemo(() => {
    const m = new Map<string, string[]>();
    for (const e of payload?.edges ?? []) {
      if (e.external) m.set(e.target, [...(m.get(e.target) ?? []), e.source.replace("-", " ")]);
    }
    return m;
  }, [payload]);

  useEffect(() => {
    setChain(null);
    if (!selected) return setCourse(null);
    fetchCourse(selected).then(setCourse).catch(() => setCourse(null));
    fetchChain(selected).then(setChain).catch(() => setChain(null));
  }, [selected]);

  // Layer comes from the backend's longest-path computation, so dependency
  // flows strictly left to right and prerequisite depth is readable by column.
  const layout = useMemo(() => {
    if (!payload) return null;
    const byLayer = new Map<number, string[]>();
    [...payload.nodes]
      .sort((a, b) => a.id.localeCompare(b.id))
      .forEach((n) => byLayer.set(n.layer, [...(byLayer.get(n.layer) ?? []), n.id]));

    // Half the catalog has no prerequisite, so layer 0 would be one column
    // ~30 deep and squash the rest. Tall layers wrap into sub-columns; depth
    // still increases left to right because layers never interleave.
    const pos: Record<string, { x: number; y: number }> = {};
    const bands: { layer: number; x: number; w: number }[] = [];
    let x = 0;
    for (const layer of [...byLayer.keys()].sort((a, b) => a - b)) {
      const ids = byLayer.get(layer)!;
      const cols = Math.ceil(ids.length / MAX_ROWS);
      ids.forEach((id, i) => {
        pos[id] = {
          x: x + Math.floor(i / MAX_ROWS) * (NODE_W + SUBCOL_GAP),
          y: (i % MAX_ROWS) * (NODE_H + ROW_GAP),
        };
      });
      const w = cols * NODE_W + (cols - 1) * SUBCOL_GAP;
      bands.push({ layer, x, w });
      x += w + COL_GAP;
    }
    return {
      pos,
      bands,
      width: Math.max(x - COL_GAP, NODE_W),
      height: Math.min(MAX_ROWS, Math.max(0, ...[...byLayer.values()].map((v) => v.length))) *
        (NODE_H + ROW_GAP),
    };
  }, [payload]);

  // The chain comes from the server, computed over the whole catalog year, so
  // it is right under any filter and splits "must come first" from "one of
  // these": CSC 340 needs 121 and 125, plus either 231 or 235.
  const focus = useMemo(() => {
    if (!selected || !chain || chain.course_id !== selected) return null;

    const required = new Set<string>();
    const alternative = new Set<string>();
    for (const c of chain.upstream) {
      (c.necessity === "required" ? required : alternative).add(c.course_id);
    }
    const downstream = new Set(chain.downstream.map((c) => c.course_id));

    const before = new Set([selected, ...required, ...alternative]);
    const after = new Set([selected, ...downstream]);
    const edges = new Map<string, "up" | "down">();
    for (const e of payload?.edges ?? []) {
      // An edge belongs to the chain only when both ends do; one leaving the
      // chain sideways is not part of any path through the selected course.
      if (before.has(e.source) && before.has(e.target)) edges.set(e.id, "up");
      else if (after.has(e.source) && after.has(e.target)) edges.set(e.id, "down");
    }

    const role = (id: string) =>
      id === selected
        ? "selected"
        : required.has(id)
          ? "required"
          : alternative.has(id)
            ? "alternative"
            : downstream.has(id)
              ? "downstream"
              : null;

    return { required, alternative, downstream, edges, role };
  }, [selected, chain, payload]);

  // 64 courses do not fit at 1:1, so frame the whole graph on load rather
  // than dropping the viewer at the top-left corner of it.
  const fit = useCallback(() => {
    const box = svgRef.current?.getBoundingClientRect();
    if (!box || !layout) return;
    const pad = 48;
    const top = 96; // clears the filter bar and leaves room for depth labels
    const k = Math.min(
      1,
      (box.width - pad * 2) / layout.width,
      (box.height - top - pad) / layout.height,
    );
    setView({ x: pad, y: top, k });
  }, [layout]);

  useEffect(fit, [fit]);

  // Searching for a course that happens to be off-screen would otherwise
  // highlight it invisibly, so a hit is brought to the middle of the canvas.
  const centreOn = useCallback(
    (id: string) => {
      const box = svgRef.current?.getBoundingClientRect();
      const pos = layout?.pos[id];
      if (!box || !pos) return;
      setView((v) => ({
        ...v,
        x: box.width / 2 - (pos.x + NODE_W / 2) * v.k,
        y: box.height / 2 - (pos.y + NODE_H / 2) * v.k,
      }));
    },
    [layout],
  );

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || !payload) return [];
    const norm = q.replace(/[\s-]/g, "");
    return payload.nodes
      .filter(
        (n) =>
          n.id.toLowerCase().replace(/-/g, "").includes(norm) ||
          n.title.toLowerCase().includes(q),
      )
      .slice(0, 8);
  }, [query, payload]);

  const visible = useMemo(
    () => new Set(payload?.nodes.map((n) => n.id) ?? []),
    [payload],
  );
  const selectedNode = payload?.nodes.find((n) => n.id === selected) ?? null;

  const choose = (id: string) => {
    setSelected(id);
    centreOn(id);
    setQuery("");
    setCursor(0);
  };

  if (error)
    return (
      <AppShell title="Prerequisite Graph">
        <pre className="text-sm text-destructive">{error}</pre>
      </AppShell>
    );

  return (
    <AppShell
      title="Prerequisite Graph"
      subtitle="Courses are laid out by prerequisite depth; dependency flows left to right."
      bleed
      aside={
        payload ? (
          <div className="text-xs text-muted-foreground">
            {focus
              ? `${selected?.replace("-", " ")}: ${focus.required.size} required${
                  focus.alternative.size ? ` + ${focus.alternative.size} alternatives` : ""
                } before · opens ${focus.downstream.size} after`
              : [
                  `${payload.nodes.length} courses`,
                  `${payload.edges.filter((e) => !e.external).length} edges`,
                  ...(payload.nodes.some((n) => n.status)
                    ? (Object.keys(STATUS) as Status[]).map(
                        (st) => `${payload.nodes.filter((n) => n.status === st).length} ${st}`,
                      )
                    : []),
                ].join(" · ")}
          </div>
        ) : null
      }
    >
      <div className="flex min-h-0 md:h-[calc(100vh-81px)]">
        <div className="relative min-w-0 flex-1 bg-surface-strong md:overflow-hidden">
          <div className="z-10 flex flex-wrap items-start gap-2 p-3 md:absolute md:left-4 md:top-4 md:p-0">
            <div className="relative">
              <input
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setCursor(0);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Escape") return setQuery("");
                  if (!matches.length) return;
                  if (e.key === "Enter") {
                    e.preventDefault();
                    choose(matches[Math.min(cursor, matches.length - 1)].id);
                  } else if (e.key === "ArrowDown") {
                    e.preventDefault();
                    setCursor((c) => (c + 1) % matches.length);
                  } else if (e.key === "ArrowUp") {
                    e.preventDefault();
                    setCursor((c) => (c - 1 + matches.length) % matches.length);
                  }
                }}
                placeholder="Search courses…"
                aria-label="Search courses"
                role="combobox"
                aria-expanded={matches.length > 0}
                className="w-56 rounded-md border border-border bg-surface px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-ring"
              />
              {query.trim() ? (
                <ul
                  role="listbox"
                  className="panel absolute left-0 top-full z-20 mt-1 w-72 overflow-hidden py-1 text-sm shadow-lg"
                >
                  {matches.length ? (
                    matches.map((m, i) => (
                      <li key={m.id}>
                        <button
                          role="option"
                          aria-selected={i === cursor}
                          onMouseEnter={() => setCursor(i)}
                          onClick={() => choose(m.id)}
                          className={`flex w-full items-baseline gap-2 px-3 py-1.5 text-left ${
                            i === cursor ? "bg-secondary" : ""
                          }`}
                        >
                          <span className="font-mono text-xs font-medium">{m.label}</span>
                          <span className="truncate text-muted-foreground">{m.title}</span>
                        </button>
                      </li>
                    ))
                  ) : (
                    <li className="px-3 py-1.5 text-muted-foreground">
                      No course matches “{query.trim()}”
                    </li>
                  )}
                </ul>
              ) : null}
            </div>
            <DepartmentPicker value={subjects} onChange={setSubjects} />
            <select
              value={program}
              onChange={(e) => {
                setProgram(e.target.value);
                if (!e.target.value) setShowOrder(false);
              }}
              aria-label="Program"
              className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm"
            >
              <option value="">All programs</option>
              {programs.map((p) => (
                <option key={p.program_id} value={p.program_id}>
                  {p.name} {p.kind}
                </option>
              ))}
            </select>
            {program ? (
              <label className="flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={showOrder}
                  onChange={(e) => setShowOrder(e.target.checked)}
                />
                Show order
              </label>
            ) : null}
            {student ? (
              <label className="flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={withStudent}
                  onChange={(e) => setWithStudent(e.target.checked)}
                />
                {viewer?.advisor ? `${student}'s progress` : "My progress"}
              </label>
            ) : null}
            <button
              onClick={fit}
              className="hidden rounded-md border border-border bg-surface px-3 py-1.5 text-sm hover:bg-secondary md:inline-block"
            >
              Fit to view
            </button>
          </div>

          {/* The narrow list spells status out in words, so the legend is for the SVG only. */}
          <div className="absolute bottom-4 left-4 z-10 hidden panel p-3 text-xs md:block">
            <div className="mb-2 font-medium uppercase tracking-wider text-muted-foreground">
              Legend
            </div>
            <div className="grid gap-1.5">
              {payload?.nodes.some((n) => n.status)
                ? (Object.keys(STATUS) as Status[]).map((st) => (
                    <div key={st} className="flex items-center gap-2">
                      <svg width="26" height="16" aria-hidden>
                        <rect
                          x="1"
                          y="1"
                          width="24"
                          height="14"
                          rx="3"
                          fill={STATUS[st].fill}
                          stroke={STATUS[st].stroke}
                          strokeWidth={Math.min(STATUS[st].width, 2)}
                          strokeDasharray={STATUS[st].dash}
                        />
                        <StatusIcon status={st} x={13} y={12} />
                      </svg>
                      {STATUS[st].label}
                    </div>
                  ))
                : null}
              {payload?.nodes.some((n) => n.status) ? (
                <div className="mt-1 border-t border-border pt-2 font-medium uppercase tracking-wider text-muted-foreground">
                  Edges
                </div>
              ) : null}
              {[
                { label: "Required prerequisite", dash: undefined, color: "var(--border)" },
                { label: "Alternative group (or)", dash: "5 4", color: "var(--primary)" },
                { label: "Corequisite", dash: "2 3", color: "var(--warning)" },
              ].map((l) => (
                <div key={l.label} className="flex items-center gap-2">
                  <svg width="26" height="6">
                    <line
                      x1="0"
                      y1="3"
                      x2="26"
                      y2="3"
                      stroke={l.color}
                      strokeWidth="1.5"
                      strokeDasharray={l.dash}
                    />
                  </svg>
                  {l.label}
                </div>
              ))}
              <div className="flex items-center gap-2">
                <span className="inline-flex size-4 items-center justify-center rounded border border-dashed border-warning text-[9px] text-warning">
                  ◆
                </span>
                Consent / standing condition
              </div>
              {order ? (
                <div className="flex items-center gap-2">
                  <svg width="26" height="18" aria-hidden>
                    <circle cx="9" cy="9" r="8" fill="var(--primary)" />
                    <text x="9" y="12.5" textAnchor="middle" className="text-[10px] font-semibold" fill="var(--primary-foreground)">
                      3
                    </text>
                  </svg>
                  Term in the program order
                </div>
              ) : null}
              <div className="mt-1 border-t border-border pt-2 font-medium uppercase tracking-wider text-muted-foreground">
                When a course is selected
              </div>
              {[
                { label: "Must come first", style: { borderColor: "var(--chain-up)" } },
                { label: "One of a choice", style: { borderColor: "var(--chain-up)", borderStyle: "dashed" } },
                { label: "Opens up", style: { borderColor: "var(--chain-down)" } },
              ].map((l) => (
                <div key={l.label} className="flex items-center gap-2">
                  <span className="inline-block h-3 w-5 rounded-sm border-2" style={l.style} />
                  {l.label}
                </div>
              ))}
            </div>
          </div>

          {!subjects.length ? (
            <div className="flex size-full items-center justify-center p-6">
              <p className="max-w-sm text-center text-sm text-muted-foreground">
                Choose one or more departments to draw the graph.
              </p>
            </div>
          ) : !payload ? (
            <p className="p-6 text-sm text-muted-foreground">Loading graph…</p>
          ) : !payload.nodes.length ? (
            <div className="flex size-full items-center justify-center p-6">
              <p className="max-w-sm text-center text-sm text-muted-foreground">
                No courses match these filters. Try adding a department or choosing
                another program.
              </p>
            </div>
          ) : narrow ? (
            <SimpleGraph nodes={payload.nodes} selected={selected} role={focus?.role} onPick={setSelected} />
          ) : (
            <svg
              ref={svgRef}
              className="size-full cursor-grab touch-none active:cursor-grabbing"
              onWheel={(e) =>
                setView((v) => ({
                  ...v,
                  k: Math.min(2, Math.max(0.2, v.k * (e.deltaY > 0 ? 0.92 : 1.08))),
                }))
              }
              onPointerDown={(e) => {
                drag.current = { x: e.clientX, y: e.clientY, ox: view.x, oy: view.y };
                e.currentTarget.setPointerCapture(e.pointerId);
              }}
              onPointerMove={(e) => {
                if (!drag.current) return;
                const dx = e.clientX - drag.current.x;
                const dy = e.clientY - drag.current.y;
                setView((v) => ({ ...v, x: drag.current!.ox + dx, y: drag.current!.oy + dy }));
              }}
              onPointerUp={() => {
                drag.current = null;
              }}
            >
              <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
                {layout!.bands.map((b) => (
                  <text
                    key={b.layer}
                    x={b.x}
                    y={-14}
                    className="text-[10px] uppercase tracking-wider"
                    fill="var(--muted-foreground)"
                  >
                    depth {b.layer}
                  </text>
                ))}
                {payload.edges.map((edge) => {
                  const a = layout!.pos[edge.source];
                  const b = layout!.pos[edge.target];
                  if (!a || !b) return null;
                  const x1 = a.x + NODE_W;
                  const y1 = a.y + NODE_H / 2;
                  const x2 = b.x;
                  const y2 = b.y + NODE_H / 2;
                  const mid = (x1 + x2) / 2;
                  const dir = focus?.edges.get(edge.id);
                  const inChain = dir !== undefined;
                  const stroke =
                    dir === "down"
                      ? "var(--chain-down)"
                      : dir === "up"
                        ? "var(--chain-up)"
                        : edge.kind === "alternative"
                          ? "var(--primary)"
                          : edge.kind === "coreq"
                            ? "var(--warning)"
                            : "var(--border)";
                  return (
                    <path
                      key={edge.id}
                      d={`M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`}
                      fill="none"
                      stroke={stroke}
                      strokeWidth={inChain ? 2.2 : 1.3}
                      opacity={focus && !inChain ? 0.12 : 1}
                      strokeDasharray={
                        edge.kind === "alternative"
                          ? "5 4"
                          : edge.kind === "coreq"
                            ? "2 3"
                            : undefined
                      }
                    />
                  );
                })}

                {payload.nodes.map((n) => {
                  const pos = layout!.pos[n.id];
                  const isSelected = n.id === selected;
                  // Unrelated courses dim rather than disappear, so the
                  // chain is read in the context of the whole catalog.
                  const role = focus?.role(n.id) ?? null;
                  const inChain = role !== null;
                  const st = n.status ? STATUS[n.status] : null;
                  const round = roundOf.get(n.id);
                  const outside = externalIn.get(n.id);
                  // Status owns the node's fill and border; the selected
                  // chain is drawn as a halo around it, so both stay legible.
                  const halo = isSelected
                    ? "var(--foreground)"
                    : role === "required" || role === "alternative"
                      ? "var(--chain-up)"
                      : role === "downstream"
                        ? "var(--chain-down)"
                        : null;
                  const dimmed = focus ? !inChain : order ? round === undefined : false;
                  return (
                    <g
                      key={n.id}
                      transform={`translate(${pos.x} ${pos.y})`}
                      className="cursor-pointer"
                      opacity={dimmed ? 0.18 : 1}
                      onPointerDown={(e) => {
                        e.stopPropagation();
                        setSelected(isSelected ? null : n.id);
                      }}
                    >
                      <title>
                        {[
                          `${n.label} — ${n.title}`,
                          st ? st.label + (n.conditional ? " (needs confirming)" : "") : null,
                          n.unmet?.length ? `Still needs: ${n.unmet.join("; ")}` : null,
                          outside ? `Also needs (outside this filter): ${outside.join(", ")}` : null,
                        ]
                          .filter(Boolean)
                          .join("\n")}
                      </title>
                      {halo ? (
                        <rect
                          x="-5"
                          y="-5"
                          width={NODE_W + 10}
                          height={NODE_H + 10}
                          rx="12"
                          fill="none"
                          stroke={halo}
                          strokeWidth={isSelected ? 3 : 2.2}
                          strokeDasharray={role === "alternative" ? "6 4" : undefined}
                        />
                      ) : null}
                      <rect
                        width={NODE_W}
                        height={NODE_H}
                        rx="8"
                        fill={st?.fill ?? "var(--surface)"}
                        stroke={st?.stroke ?? "var(--border)"}
                        strokeWidth={st?.width ?? 1.5}
                        strokeDasharray={st ? st.dash : n.badges.length ? "5 3" : undefined}
                      />
                      {st ? <StatusIcon status={n.status!} x={NODE_W - 13} y={19} /> : null}
                      <text
                        x="10"
                        y="21"
                        className="font-mono text-[12px] font-medium"
                        fill="var(--foreground)"
                      >
                        {n.label}
                        {n.badges.length || n.conditional ? " ◆" : ""}
                      </text>
                      <text x="10" y="38" className="text-[10px]" fill="var(--muted-foreground)">
                        {n.title.length > 22 ? `${n.title.slice(0, 21)}…` : n.title}
                      </text>
                      {round !== undefined ? (
                        <g transform="translate(0 0)">
                          <circle r="10" fill="var(--primary)" />
                          <text y="3.5" textAnchor="middle" className="text-[10px] font-semibold" fill="var(--primary-foreground)">
                            {round}
                          </text>
                        </g>
                      ) : null}
                      {outside ? (
                        <text
                          x="-6"
                          y={NODE_H / 2 + 3}
                          textAnchor="end"
                          className="font-mono text-[9px]"
                          fill="var(--muted-foreground)"
                        >
                          {outside[0]}
                          {outside.length > 1 ? ` +${outside.length - 1}` : ""} →
                        </text>
                      ) : null}
                    </g>
                  );
                })}
              </g>
            </svg>
          )}
        </div>

        {/* Beside the graph from lg; below it, a bottom sheet while a course is selected. */}
        <aside
          className={`${course ? "block" : "hidden"} fixed inset-x-0 bottom-0 z-40 max-h-[60vh] overflow-y-auto border-t border-border bg-surface p-5 shadow-lg lg:static lg:block lg:max-h-none lg:w-80 lg:shrink-0 lg:border-l lg:border-t-0 lg:shadow-none`}
        >
          {course ? (
            <div className="space-y-4 text-sm">
              <button
                onClick={() => setSelected(null)}
                className="float-right rounded-md border border-border px-2 py-1 text-xs hover:bg-secondary lg:hidden"
              >
                Close
              </button>
              <div>
                <div className="font-display text-2xl">{course.label}</div>
                <div className="text-muted-foreground">{course.title}</div>
              </div>

              {selectedNode?.status ? (
                <div
                  className="rounded-md border-2 p-2.5 text-xs"
                  style={{
                    borderColor: STATUS[selectedNode.status].stroke,
                    borderStyle: STATUS[selectedNode.status].dash ? "dashed" : "solid",
                    background: STATUS[selectedNode.status].fill,
                  }}
                >
                  <div className="font-medium">
                    {STATUS[selectedNode.status].label}
                    {selectedNode.conditional ? " — needs confirming" : ""}
                  </div>
                  {selectedNode.unmet?.length && selectedNode.status !== "completed" ? (
                    <div className="mt-1 text-muted-foreground">
                      {selectedNode.status === "locked" ? "Still needs: " : "Depends on: "}
                      {selectedNode.unmet.join("; ")}
                    </div>
                  ) : null}
                </div>
              ) : null}

              <div className="flex flex-wrap gap-1">
                {[course.distribution, ...course.competence_variants, ...course.attributes]
                  .filter(Boolean)
                  .map((t) => (
                    <span key={t} className="rounded bg-secondary px-1.5 py-0.5 text-xs">
                      {t}
                    </span>
                  ))}
              </div>

              <dl className="space-y-3">
                <div>
                  <dt className="text-xs uppercase tracking-wider text-muted-foreground">
                    Credits
                  </dt>
                  <dd>{credits(course.credits_min, course.credits_max)}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wider text-muted-foreground">
                    Prerequisite expression
                  </dt>
                  <dd className="mt-1 text-xs">
                    <PrereqTree node={course.prereq_expr} />
                  </dd>
                </div>
                {course.prereq_raw ? (
                  <div>
                    <dt className="text-xs uppercase tracking-wider text-muted-foreground">
                      Catalog text
                    </dt>
                    <dd className="mt-1 text-xs italic text-muted-foreground">
                      {course.prereq_raw}
                    </dd>
                  </div>
                ) : null}
              </dl>

              {chain && chain.course_id === course.course_id ? (
                <div className="space-y-3">
                  <ChainList
                    title="Must come first"
                    items={chain.upstream.filter((c) => c.necessity === "required")}
                    empty="Nothing — no required prerequisites."
                    visible={visible}
                    onPick={choose}
                  />
                  <ChainList
                    title="One of a choice"
                    items={chain.upstream.filter((c) => c.necessity === "alternative")}
                    visible={visible}
                    onPick={choose}
                  />
                  <ChainList
                    title="Opens up"
                    items={chain.downstream}
                    empty="Nothing in this catalog depends on it."
                    visible={visible}
                    onPick={choose}
                  />
                </div>
              ) : null}

              <Link
                href={`/courses/${course.course_id}`}
                className="inline-block text-xs underline underline-offset-2"
              >
                Open full course page →
              </Link>
            </div>
          ) : (
            <div className="space-y-4 text-sm">
              {order ? (
                <div className="space-y-3">
                  <div>
                    <div className="font-display text-2xl">
                      {programs.find((p) => p.program_id === order.program_id)?.name ?? order.program_id}{" "}
                      order
                    </div>
                    <p className="text-xs text-muted-foreground">{order.note}</p>
                  </div>
                  <ol className="space-y-1.5">
                    {order.rounds.map((r, i) => (
                      <li key={i} className="flex gap-2">
                        <span className="inline-flex size-5 shrink-0 items-center justify-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground">
                          {i + 1}
                        </span>
                        <span className="flex flex-wrap gap-1">
                          {r.length ? (
                            r.map((c) => (
                              <button
                                key={c.course_id}
                                onClick={() => visible.has(c.course_id) && choose(c.course_id)}
                                title={c.in_program ? c.title : `${c.title} — needed as a prerequisite`}
                                className={`rounded px-1.5 py-0.5 font-mono text-xs ${
                                  c.in_program ? "bg-secondary" : "border border-dashed border-border text-muted-foreground"
                                }`}
                              >
                                {c.label}
                              </button>
                            ))
                          ) : (
                            <span className="text-xs italic text-muted-foreground">waiting</span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ol>
                  {order.assumed.length ? (
                    <div>
                      <div className="text-xs uppercase tracking-wider text-muted-foreground">
                        Assumed
                      </div>
                      <ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-muted-foreground">
                        {order.assumed.map((a) => (
                          <li key={a}>{a}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              ) : null}
              <p className="text-muted-foreground">
                Select a course to see its prerequisite expression beside the catalog
                wording it was read from.
              </p>
            </div>
          )}
        </aside>
      </div>
    </AppShell>
  );
}

// Courses outside the current filter are listed but not clickable: the chain
// is computed over the whole catalog, so it can name courses not on screen.
// The narrow-screen graph: the same courses, depth columns turned into
// sections, status as an icon and a word (never colour alone), and the
// selected course's chain marked so "what comes first" still reads.
function SimpleGraph({
  nodes,
  selected,
  role,
  onPick,
}: {
  nodes: GraphPayload["nodes"];
  selected: string | null;
  role?: (id: string) => string | null;
  onPick: (id: string) => void;
}) {
  const layers = new Map<number, GraphPayload["nodes"]>();
  for (const n of [...nodes].sort((a, b) => a.id.localeCompare(b.id))) {
    if (!layers.has(n.layer)) layers.set(n.layer, []);
    layers.get(n.layer)!.push(n);
  }
  const ROLE: Record<string, { text: string; style: React.CSSProperties }> = {
    selected: { text: "selected", style: { borderColor: "var(--ring)", borderWidth: 2 } },
    required: { text: "must come first", style: { borderColor: "var(--chain-up)", borderWidth: 2 } },
    alternative: { text: "one of a choice", style: { borderColor: "var(--chain-up)", borderWidth: 2, borderStyle: "dashed" } },
    downstream: { text: "opens up", style: { borderColor: "var(--chain-down)", borderWidth: 2 } },
  };
  return (
    <div className="flex flex-col gap-4 p-3 pb-24">
      {[...layers.entries()]
        .sort(([a], [b]) => a - b)
        .map(([layer, list]) => (
          <section key={layer}>
            <h2 className="mb-1.5 text-xs uppercase tracking-wider text-muted-foreground">
              {layer === 0 ? "No prerequisites" : `Depth ${layer}`}
            </h2>
            <ul className="grid gap-1.5 sm:grid-cols-2">
              {list.map((n) => {
                const r = role?.(n.id) ?? (n.id === selected ? "selected" : null);
                const st = n.status ? STATUS[n.status] : null;
                return (
                  <li key={n.id}>
                    <button
                      onClick={() => onPick(n.id)}
                      aria-pressed={n.id === selected}
                      className="flex w-full items-start gap-2 rounded-md border border-border bg-surface p-2 text-left text-sm"
                      style={r ? ROLE[r].style : undefined}
                    >
                      {st ? (
                        <span
                          className="mt-1 size-3 shrink-0 rounded-full border-2"
                          style={{ background: st.fill, borderColor: st.stroke, borderStyle: st.dash ? "dashed" : "solid" }}
                          aria-hidden
                        />
                      ) : null}
                      <span className="min-w-0 flex-1">
                        <span className="font-mono font-medium">{n.label}</span>
                        <span className="block truncate text-xs text-muted-foreground">{n.title}</span>
                        <span className="block text-[11px] text-muted-foreground">
                          {[st?.label, r && r !== "selected" ? ROLE[r].text : null].filter(Boolean).join(" · ")}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
    </div>
  );
}

function ChainList({
  title,
  items,
  empty,
  visible,
  onPick,
}: {
  title: string;
  items: ChainCourse[];
  empty?: string;
  visible: Set<string>;
  onPick: (id: string) => void;
}) {
  if (!items.length && !empty) return null;
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-muted-foreground">
        {title} {items.length ? `(${items.length})` : ""}
      </div>
      {items.length ? (
        <ul className="mt-1 flex flex-wrap gap-1">
          {items.map((c) => (
            <li key={c.course_id}>
              {visible.has(c.course_id) ? (
                <button
                  onClick={() => onPick(c.course_id)}
                  title={c.title}
                  className="rounded bg-secondary px-1.5 py-0.5 font-mono text-xs hover:bg-accent"
                >
                  {c.label}
                </button>
              ) : (
                <span
                  title={`${c.title} — not in the current filter`}
                  className="rounded border border-dashed border-border px-1.5 py-0.5 font-mono text-xs text-muted-foreground"
                >
                  {c.label}
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-xs text-muted-foreground">{empty}</p>
      )}
    </div>
  );
}

// Looks like the program menu, but several departments can be ticked at once.
// None ticked is allowed, and is how the page starts: an empty canvas.
function DepartmentPicker({
  value,
  onChange,
}: {
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: PointerEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const all = value.length === DEPARTMENTS.length;
  const label = all
    ? "All departments"
    : !value.length
      ? "Choose departments"
      : value.length === 1
        ? `${value[0]} only`
        : value.join(" + ");

  const toggle = (d: string) => {
    const next = value.includes(d) ? value.filter((x) => x !== d) : [...value, d];
    onChange(DEPARTMENTS.filter((x) => next.includes(x)));
  };

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={`Departments: ${label}`}
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-1.5 text-sm"
      >
        {label}
        <ChevronDown className="size-4 text-muted-foreground" />
      </button>
      {open ? (
        <div
          role="group"
          aria-label="Departments"
          className="panel absolute left-0 top-full z-20 mt-1 w-56 py-1 text-sm shadow-lg"
        >
          <button
            type="button"
            onClick={() => onChange(DEPARTMENTS)}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-secondary"
          >
            <Check className={`size-4 ${all ? "" : "invisible"}`} />
            All departments
          </button>
          <button
            type="button"
            onClick={() => onChange([])}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-secondary"
          >
            <Check className={`size-4 ${value.length ? "invisible" : ""}`} />
            None
          </button>
          <div className="my-1 border-t border-border" />
          {DEPARTMENTS.map((d) => {
            const on = value.includes(d);
            return (
              <label
                key={d}
                className="flex cursor-pointer items-center gap-2 px-3 py-1.5 hover:bg-secondary"
              >
                <input type="checkbox" checked={on} onChange={() => toggle(d)} />
                {d}
              </label>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
