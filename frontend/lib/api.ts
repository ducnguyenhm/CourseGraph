export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type PrereqNode =
  | { type: "none" }
  | { type: "course"; course_id: string; min_grade?: string | null }
  | { type: "coreq"; course_id: string }
  | { type: "consent"; by: string }
  | { type: "standing"; min_level?: string | null; max_level?: string | null }
  | { type: "course_level"; subject: string; min_number: number; count: number }
  | { type: "program"; program_id: string }
  | { type: "placement"; test: string; min_score?: number | null }
  | { type: "and"; children: PrereqNode[] }
  | { type: "or"; children: PrereqNode[] };

export type CourseDetail = {
  course_id: string;
  label: string;
  title: string;
  credits_min: number | null;
  credits_max: number | null;
  distribution: string | null;
  competence_variants: string[];
  attributes: string[];
  stub: boolean;
  retired: boolean;
  catalog_year: string;
  prereq_expr: PrereqNode;
  prereq_raw: string;
  extra: Record<string, unknown>;
};

export type GraphPayload = {
  nodes: {
    id: string;
    course_id: string;
    label: string;
    title: string;
    credits_min: number | null;
    credits_max: number | null;
    badges: string[];
    layer: number;
    // Present when the graph is fetched for a program.
    in_program?: "required" | "elective" | null;
    // Present when the graph is fetched for a student.
    status?: Status;
    conditional?: boolean; // eligible only if someone confirms (consent)
    unmet?: string[];
  }[];
  edges: {
    id: string;
    source: string;
    target: string;
    kind: "required" | "alternative" | "coreq";
    group: string | null;
    via: string | null;
    // The source is outside the current filter; the edge is kept so the view
    // can say a prerequisite exists rather than silently losing it.
    external: boolean;
  }[];
};

export type Status = "completed" | "planned" | "eligible" | "locked";

export type ProgramSummary = {
  program_id: string;
  kind: "major" | "minor";
  name: string;
  department: string;
};

export type ProgramOrder = {
  program_id: string;
  catalog_year: string;
  rounds: { course_id: string; label: string; title: string; in_program: boolean }[][];
  order: string[];
  assumed: string[];
  note: string;
};

export type ChainCourse = {
  course_id: string;
  label: string;
  title: string;
  necessity: "required" | "alternative";
  stub: boolean;
};

export type Chain = {
  course_id: string;
  catalog_year: string;
  upstream: ChainCourse[];
  downstream: ChainCourse[];
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${path}`);
  return res.json();
}

export const fetchGraph = (opts: {
  subjects?: string[];
  program?: string;
  student?: string;
}) => {
  const q = new URLSearchParams();
  opts.subjects?.forEach((s) => q.append("subject", s));
  if (opts.program) q.set("program", opts.program);
  if (opts.student) q.set("student", opts.student);
  const qs = q.toString();
  return get<GraphPayload>(`/api/graph${qs ? `?${qs}` : ""}`);
};

export const fetchPrograms = () => get<ProgramSummary[]>("/api/programs");

export const fetchProgramOrder = (programId: string) =>
  get<ProgramOrder>(`/api/programs/${encodeURIComponent(programId)}/order`);

export const fetchChain = (courseId: string) =>
  get<Chain>(`/api/graph/chain/${encodeURIComponent(courseId)}`);

export const fetchCourse = (courseId: string) =>
  get<CourseDetail>(`/api/courses/${encodeURIComponent(courseId)}`);

export const credits = (lo: number | null, hi: number | null) =>
  lo === null && hi === null ? "" : lo === hi ? `${lo}` : `${lo}–${hi}`;
