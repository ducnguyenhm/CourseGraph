"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { PrereqTree } from "@/components/PrereqTree";
import {
  credits,
  fetchCourse,
  fetchGraph,
  type CourseDetail,
  type GraphPayload,
} from "@/lib/api";

const NODE_W = 150;
const NODE_H = 52;
const COL_GAP = 110;
const ROW_GAP = 22;
const SUBCOL_GAP = 16;
const MAX_ROWS = 12;

const SUBJECTS = [
  { value: "", label: "CSC + MATH" },
  { value: "CSC", label: "CSC only" },
  { value: "MATH", label: "MATH only" },
];

export default function GraphPage() {
  const [subject, setSubject] = useState("");
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const [payload, setPayload] = useState<GraphPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    setPayload(null);
    setSelected(null);
    fetchGraph(subject || undefined)
      .then(setPayload)
      .catch((e) => setError(String(e)));
  }, [subject]);

  useEffect(() => {
    if (!selected) return setCourse(null);
    fetchCourse(selected).then(setCourse).catch(() => setCourse(null));
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
      height: Math.min(MAX_ROWS, Math.max(...[...byLayer.values()].map((v) => v.length))) *
        (NODE_H + ROW_GAP),
    };
  }, [payload]);

  // Every course that must be taken before the selected one — the transitive
  // closure over incoming edges, not just its direct prerequisites. This is
  // the question the graph exists to answer: what does this course actually
  // cost me?
  const focus = useMemo(() => {
    if (!selected || !payload) return null;

    const incoming = new Map<string, string[]>();
    for (const e of payload.edges) {
      incoming.set(e.target, [...(incoming.get(e.target) ?? []), e.source]);
    }

    const chain = new Set<string>([selected]);
    const queue = [selected];
    while (queue.length) {
      for (const prereq of incoming.get(queue.pop()!) ?? []) {
        if (!chain.has(prereq)) {
          chain.add(prereq);
          queue.push(prereq);
        }
      }
    }

    // An edge belongs to the chain only when both ends do; an edge leaving the
    // chain sideways is not part of any path to the selected course.
    const edges = new Set(
      payload.edges
        .filter((e) => chain.has(e.source) && chain.has(e.target))
        .map((e) => e.id),
    );
    return { nodes: chain, edges, upstream: chain.size - 1 };
  }, [selected, payload]);

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
              ? `${focus.upstream} prerequisite ${focus.upstream === 1 ? "course" : "courses"} upstream of ${selected?.replace("-", " ")}`
              : `${payload.nodes.length} courses · ${payload.edges.length} edges`}
          </div>
        ) : null
      }
    >
      <div className="flex h-[calc(100vh-81px)] min-h-0">
        <div className="relative min-w-0 flex-1 overflow-hidden bg-surface-strong">
          <div className="absolute left-4 top-4 z-10 flex flex-wrap items-start gap-2">
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
            <select
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm"
            >
              {SUBJECTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
            <button
              onClick={fit}
              className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm hover:bg-secondary"
            >
              Fit to view
            </button>
          </div>

          <div className="absolute bottom-4 left-4 z-10 panel p-3 text-xs">
            <div className="mb-2 font-medium uppercase tracking-wider text-muted-foreground">
              Legend
            </div>
            <div className="grid gap-1.5">
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
            </div>
          </div>

          {!payload ? (
            <p className="p-6 text-sm text-muted-foreground">Loading graph…</p>
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
                  const inChain = focus?.edges.has(edge.id) ?? false;
                  const stroke =
                    edge.kind === "alternative"
                      ? "var(--primary)"
                      : edge.kind === "coreq"
                        ? "var(--warning)"
                        : inChain
                          ? "var(--primary)"
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
                  const inChain = focus?.nodes.has(n.id) ?? false;
                  return (
                    <g
                      key={n.id}
                      transform={`translate(${pos.x} ${pos.y})`}
                      className="cursor-pointer"
                      opacity={focus && !inChain ? 0.18 : 1}
                      onPointerDown={(e) => {
                        e.stopPropagation();
                        setSelected(isSelected ? null : n.id);
                      }}
                    >
                      <rect
                        width={NODE_W}
                        height={NODE_H}
                        rx="8"
                        fill={inChain && !isSelected ? "var(--accent)" : "var(--surface)"}
                        stroke={
                          isSelected || inChain ? "var(--primary)" : "var(--border)"
                        }
                        strokeWidth={isSelected ? 2.5 : inChain ? 2 : 1.5}
                        strokeDasharray={n.badges.length ? "5 3" : undefined}
                      />
                      <text
                        x="10"
                        y="21"
                        className="font-mono text-[12px] font-medium"
                        fill="var(--foreground)"
                      >
                        {n.label}
                        {n.badges.length ? " ◆" : ""}
                      </text>
                      <text x="10" y="38" className="text-[10px]" fill="var(--muted-foreground)">
                        {n.title.length > 24 ? `${n.title.slice(0, 23)}…` : n.title}
                      </text>
                    </g>
                  );
                })}
              </g>
            </svg>
          )}
        </div>

        <aside className="hidden w-80 shrink-0 overflow-y-auto border-l border-border bg-surface p-5 lg:block">
          {course ? (
            <div className="space-y-4 text-sm">
              <div>
                <div className="font-display text-2xl">{course.label}</div>
                <div className="text-muted-foreground">{course.title}</div>
              </div>

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
                      Curator&apos;s note
                    </dt>
                    <dd className="mt-1 text-xs italic text-muted-foreground">
                      {course.prereq_raw}
                    </dd>
                  </div>
                ) : null}
              </dl>

              <Link
                href={`/courses/${course.course_id}`}
                className="inline-block text-xs underline underline-offset-2"
              >
                Open full course page →
              </Link>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Select a course to see its prerequisite expression beside the catalog
              wording it was read from.
            </p>
          )}
        </aside>
      </div>
    </AppShell>
  );
}
