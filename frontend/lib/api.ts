import { DEMO_STUDENT, endDemoLocally, readSession } from "@/lib/session";

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
  kind: "major" | "minor" | "degree";
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

// Carries the status and the API's structured detail, so the planner can
// read a 409's check (what is unmet, whether an override note can excuse it).
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail: unknown,
  ) {
    super(message);
  }
}

// The login token, and a demo session's token for the demo student's plan.
// Every request carries the login; the demo token only goes where it means
// something, since the API refuses it for any other student.
function headers(path: string, json: boolean): HeadersInit {
  const h: Record<string, string> = {};
  if (json) h["Content-Type"] = "application/json";
  const s = readSession();
  if (s.token) h.Authorization = `Bearer ${s.token}`;
  if (s.demo && path.startsWith(`/api/students/${DEMO_STUDENT}/`)) h["X-Demo-Session"] = s.demo;
  return h;
}

async function failure(res: Response, path: string): Promise<ApiError> {
  let detail: unknown = null;
  let message = `${res.status} ${res.statusText} for ${path}`;
  try {
    detail = (await res.json()).detail;
    message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? // FastAPI's validation errors: "password: String should have at least 8 characters".
            detail.map((d: { loc?: unknown[]; msg?: string }) => `${d.loc?.at(-1) ?? "input"}: ${d.msg}`).join("; ")
          : (detail as { message?: string } | null)?.message ?? JSON.stringify(detail);
  } catch {}
  if (res.status === 410) endDemoLocally();
  return new ApiError(res.status, message, detail);
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store", headers: headers(path, false) });
  if (!res.ok) throw await failure(res, path);
  return res.json();
}

// Writes surface the API's own message ("CSC-121 does not carry SS"), since
// the person editing a record needs to know what to fix.
async function send<T>(method: "POST" | "PUT" | "PATCH" | "DELETE", path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: headers(path, body !== undefined),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw await failure(res, path);
  return (res.status === 204 ? undefined : await res.json()) as T;
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

export type RequirementState = "complete" | "in_progress" | "planned" | "outstanding";

export type AuditNode = {
  label: string;
  rule_type:
    | "all_of"
    | "any_of"
    | "specific_course"
    | "n_from_set"
    | "credit_minimum"
    | "attribute_count";
  spec: Record<string, unknown>;
  notes: string;
  state: RequirementState;
  // Courses meeting it, or for a credit/attribute count, the courses counted.
  applied: string[];
  need: number;
  have: number;
  remaining: number;
  // need/have are courses; false for credit and attribute counts.
  in_courses: boolean;
  // Catalog courses not on the record that would count here.
  options: string[];
  // False on an "any of" branch the evaluation did not use.
  chosen: boolean;
  children: AuditNode[];
};

export type Audit = {
  student_key: string;
  program: ProgramSummary;
  catalog_year: string;
  declared: boolean;
  summary: {
    complete: number;
    in_progress: number;
    planned: number;
    outstanding: number;
    rule_types: string[];
  };
  root: AuditNode;
};

export const fetchAudit = (student: string, programId: string) =>
  get<Audit>(
    `/api/students/${encodeURIComponent(student)}/audit/${encodeURIComponent(programId)}`,
  );

export const fetchCourse = (courseId: string) =>
  get<CourseDetail>(`/api/courses/${encodeURIComponent(courseId)}`);

export const credits = (lo: number | null, hi: number | null) =>
  lo === null && hi === null ? "" : lo === hi ? `${lo}` : `${lo}–${hi}`;

export const AREAS = ["AH", "SM", "SS", "LA", "GL", "PPD"] as const;
export type Area = (typeof AREAS)[number];
export const AREA_NAME: Record<Area, string> = {
  AH: "Arts and Humanities",
  SM: "Science and Mathematics",
  SS: "Social Science",
  LA: "Language",
  GL: "Global Learning",
  PPD: "Power, Privilege and Diversity",
};
export type Competence = "W" | "Q" | "S";
export type Standing = "first_year" | "sophomore" | "junior" | "senior";

export type Enrollment = {
  id: number;
  course_id: string;
  label: string;
  title: string;
  credits: number | null;
  term: string;
  status: "completed" | "in_progress";
  grade: string | null;
  competence: Competence | null;
  competence_options: Competence[];
  // Two or more means the course is "X-or-Y" and area_choice can pin one.
  areas: Area[];
  area_choice: Area | null;
  added_by_student: boolean;
  counts_as: string[];
};

export type StudentDetail = {
  student_key: string;
  name: string;
  catalog_year: string;
  class_standing: Standing;
  expected_graduation: string;
  start_term: string | null;
  // The student's own setting; null when it is worked out from the record.
  current_term: string | null;
  current_term_auto: string | null;
  programs: string[];
  enrollments: Enrollment[];
  plan: { id: number; course_id: string; label: string; term: string }[];
};

export type CourseSummary = {
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
};

export type NewCourse = {
  title: string;
  credits: number;
  areas: Area[];
  attributes: ("FYS" | "ES")[];
  competence_variants: Competence[];
};

const S = (key: string) => `/api/students/${encodeURIComponent(key)}`;

export const fetchStudent = (key: string) => get<StudentDetail>(S(key));
export const fetchAllCourses = () => get<CourseSummary[]>("/api/courses?include_stubs=true");

// Writes to a record: only its student, logged in (the API answers 403
// to anyone else). Future courses go through placeCourse, which checks them.
export const updateStudent = (
  key: string,
  body: Partial<Pick<StudentDetail, "name" | "class_standing" | "expected_graduation" | "start_term" | "current_term" | "programs">>,
) => send<StudentDetail>("PATCH", S(key), body);

export const addEnrollment = (
  key: string,
  body: {
    course_id: string;
    term: string;
    status: "completed" | "in_progress";
    grade?: string | null;
    competence?: Competence | null;
    area_choice?: Area | null;
    new_course?: NewCourse;
  },
) => send<StudentDetail>("POST", `${S(key)}/enrollments`, body);

export const updateEnrollment = (
  key: string,
  id: number,
  body: Partial<Pick<Enrollment, "term" | "status" | "grade" | "competence" | "area_choice">>,
) => send<StudentDetail>("PATCH", `${S(key)}/enrollments/${id}`, body);

export const deleteEnrollment = (key: string, id: number) =>
  send<void>("DELETE", `${S(key)}/enrollments/${id}`);

export const areasOf = (c: Pick<CourseSummary, "distribution" | "attributes">): Area[] =>
  AREAS.filter((a) => c.distribution === a || c.attributes.includes(a));

export type SemesterNeed = {
  course_id: string | null;
  label: string;
  title: string;
  credits: number;
  kind: "planned" | "required" | "chosen" | "prerequisite" | "unnamed";
  reasons: string[];
  round: number;
};

export type SemesterEstimate = {
  student_key: string;
  programs: string[];
  added: string[];
  current_term: string | null;
  expected_graduation: string;
  terms_left: number;
  chain_bound: number;
  chain: string[];
  remaining_credits: number;
  credit_basis: string;
  max_load: number;
  credit_bound: number;
  estimate: number;
  binding: "chain" | "credits" | "both" | "none";
  feasible: boolean;
  extra_terms: number;
  needs: SemesterNeed[];
  assumed: string[];
  note: string;
};

export const fetchSemesters = (student: string, opts: { add?: string[]; maxLoad?: number } = {}) => {
  const q = new URLSearchParams();
  opts.add?.forEach((a) => q.append("add", a));
  if (opts.maxLoad) q.set("max_load", String(opts.maxLoad));
  const qs = q.toString();
  return get<SemesterEstimate>(`${S(student)}/semesters${qs ? `?${qs}` : ""}`);
};

export type RequirementLine = {
  label: string;
  rule_type: AuditNode["rule_type"];
  state: RequirementState;
  applied: string[];
  need: number;
  have: number;
  options: string[];
};

export type Bounds = {
  estimate: number;
  chain_bound: number;
  chain: string[];
  credit_bound: number;
  remaining_credits: number;
  credit_basis: string;
  binding: SemesterEstimate["binding"];
  feasible: boolean;
  extra_terms: number;
};

export type SharedCourse = { course_id: string; label: string; programs: string[] };

export type ProgramImpact = {
  program: ProgramSummary;
  satisfied: RequirementLine[];
  underway: RequirementLine[];
  outstanding: RequirementLine[];
  shared_done: SharedCourse[];
  shared_needed: SharedCourse[];
  new_courses: SemesterNeed[];
  new_credits: number;
  warnings: string[];
};

export type Exploration = {
  student_key: string;
  declared: string[];
  added: string[];
  current_term: string | null;
  expected_graduation: string;
  terms_left: number;
  max_load: number;
  baseline: Bounds;
  combined: Bounds;
  additional_terms: number;
  new_courses: SemesterNeed[];
  new_credits: number;
  extra_credits_to_graduate: number;
  programs: ProgramImpact[];
  note: string;
};

export const fetchExplore = (student: string, add: string[], maxLoad?: number) => {
  const q = new URLSearchParams();
  add.forEach((a) => q.append("add", a));
  if (maxLoad) q.set("max_load", String(maxLoad));
  return get<Exploration>(`${S(student)}/explore?${q}`);
};

export type CreditTotals = { completed: number; in_progress: number; planned: number };

export type Progress = {
  student_key: string;
  name: string;
  catalog_year: string;
  class_standing: Standing;
  expected_graduation: string;
  credits: CreditTotals;
  credits_required: number;
  programs: { audit: Audit; credits: CreditTotals; courses_open: number }[];
  // Course -> declared majors/minors it counts toward, for courses in two or more.
  shared: Record<string, string[]>;
};

export const fetchProgress = (student: string) => get<Progress>(`${S(student)}/progress`);

// -- Checkpoint 4: planner, logins, demo mode, advising -----------------------

export type PlacementView = {
  course_id: string;
  label: string;
  title: string;
  credits: number;
  term: string;
  ok: boolean;
  unmet: string[];
  confirm: string[];
  message: string | null;
  override: string | null;
  overridable: boolean;
  open_comments: number;
};

export type PlacementCheck = {
  course_id: string;
  label: string;
  term: string;
  ok: boolean;
  unmet: string[];
  confirm: string[];
  message: string | null;
  load: number;
  overloaded: boolean;
  overridable: boolean;
};

export type PlanSuggestion = {
  course_id: string;
  label: string;
  title: string;
  credits: number;
  kind: "required" | "chosen" | "prerequisite";
  reasons: string[];
  round: number;
};

export type TakenView = {
  course_id: string;
  label: string;
  title: string;
  credits: number;
  term: string;
  status: "completed" | "in_progress";
};

export type PlanView = {
  student_key: string;
  name: string;
  current_term: string | null;
  expected_graduation: string;
  terms: string[];
  max_load: number;
  // Winter and May Term: Extended Studies courses only, up to this many credits.
  short_max_load: number;
  // The terms already gone through, from the first academic year, and the
  // record's courses: the planner shows the whole degree.
  past_terms: string[];
  taken: TakenView[];
  // Future terms the student took out of the plan; each can be put back.
  removed_terms: string[];
  placements: PlacementView[];
  loads: Record<string, number>;
  overloaded: string[];
  problems: number;
  suggestions: PlanSuggestion[];
  editable: boolean;
  demo: boolean;
  read_only_reason: string | null;
};

export type AccountInfo = {
  key: string;
  role: "student" | "advisor";
  name: string;
  student_key: string | null;
};

export type PlanComment = {
  id: number;
  student_key: string;
  author: string;
  author_name: string;
  body: string;
  course_id: string | null;
  label: string | null;
  term: string | null;
  resolved: boolean;
  created: string;
  // The conversation this answers; null for the comment that opened it.
  parent_id: number | null;
};

export type Advisee = {
  student_key: string;
  name: string;
  class_standing: string;
  programs: string[];
  expected_graduation: string;
  credits_completed: number;
  credits_in_progress: number;
  credits_planned: number;
  min_terms: number;
  terms_left: number;
  on_time: boolean;
  unplanned: number;
  plan_problems: number;
  overloaded_terms: string[];
  open_comments: number;
  // Open conversations whose last word is the student's.
  awaiting_reply: number;
};

const L = (maxLoad?: number) => (maxLoad ? `?max_load=${maxLoad}` : "");

export const fetchPlan = (key: string, maxLoad?: number) => get<PlanView>(`${S(key)}/plan${L(maxLoad)}`);

export const checkPlacement = (key: string, courseId: string, term: string, maxLoad?: number) =>
  send<PlacementCheck>("POST", `${S(key)}/plan/check${L(maxLoad)}`, { course_id: courseId, term });

// A rejection throws an ApiError with status 409 and the check as `detail`.
export const placeCourse = (key: string, courseId: string, term: string, override?: string, maxLoad?: number) =>
  send<PlanView>("PUT", `${S(key)}/plan/${encodeURIComponent(courseId)}${L(maxLoad)}`, {
    term,
    override: override ?? null,
  });

export const unplanCourse = (key: string, courseId: string, maxLoad?: number) =>
  send<PlanView>("DELETE", `${S(key)}/plan/${encodeURIComponent(courseId)}${L(maxLoad)}`);

// Take a future term out of the plan (it must be empty), or put it back.
export const removeTerm = (key: string, term: string, maxLoad?: number) =>
  send<PlanView>("DELETE", `${S(key)}/plan/terms/${encodeURIComponent(term)}${L(maxLoad)}`);
export const restoreTerm = (key: string, term: string, maxLoad?: number) =>
  send<PlanView>("PUT", `${S(key)}/plan/terms/${encodeURIComponent(term)}${L(maxLoad)}`);

export const login = (key: string, password: string) =>
  send<{ token: string; account: AccountInfo }>("POST", "/api/auth/login", { key, password });

export type SignupBody = {
  key: string;
  password: string;
  name: string;
  class_standing: Standing;
  start_term: string | null;
  expected_graduation: string;
  programs: string[];
  advisor: string | null;
};

export const signup = (body: SignupBody) =>
  send<{ token: string; account: AccountInfo }>("POST", "/api/auth/signup", body);

export const fetchAdvisors = () => get<{ key: string; name: string }[]>("/api/auth/advisors");

export const startDemoSession = () =>
  send<{ token: string; student_key: string }>("POST", "/api/demo/session");

export const fetchAdvisees = () => get<Advisee[]>("/api/advisor/advisees");

export const fetchComments = (key: string) => get<PlanComment[]>(`${S(key)}/comments`);

export const addComment = (key: string, body: string, courseId?: string | null) =>
  send<PlanComment>("POST", `${S(key)}/comments`, { body, course_id: courseId ?? null });

export const replyToComment = (id: number, body: string) =>
  send<PlanComment>("POST", `/api/comments/${id}/replies`, { body });

export const resolveComment = (id: number) => send<PlanComment>("POST", `/api/comments/${id}/resolve`);

// Ends a demo session on the server and in this tab. Best effort: the server
// forgets an idle session by itself.
export async function endDemoSession() {
  const { demo } = readSession();
  if (demo) {
    await fetch(`${API}/api/demo/session`, { method: "DELETE", headers: { "X-Demo-Session": demo } }).catch(() => {});
  }
  endDemoLocally();
}
