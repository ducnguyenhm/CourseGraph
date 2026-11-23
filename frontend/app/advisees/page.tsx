"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AlertTriangle, ArrowRight, CheckCircle2, MessageSquare, XCircle } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { ApiError, fetchAdvisees, type Advisee } from "@/lib/api";
import { useSession } from "@/lib/useSession";

const STANDING: Record<string, string> = {
  first_year: "First year",
  sophomore: "Sophomore",
  junior: "Junior",
  senior: "Senior",
};
const fmt = (n: number) => (Number.isInteger(n) ? `${n}` : n.toFixed(1));
const termName = (t: string) =>
  `${{ FA: "Fall", WI: "Winter Term", SP: "Spring", SU: "Summer" }[t.slice(4)] ?? t.slice(4)} ${t.slice(0, 4)}`;

export default function AdviseesPage() {
  const session = useSession();
  const [advisees, setAdvisees] = useState<Advisee[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    if (session.account?.role !== "advisor") {
      setError(null);
      return;
    }
    fetchAdvisees()
      .then(setAdvisees)
      .catch((e) => setError(e instanceof ApiError && e.status === 401 ? "Your login has expired." : String(e)));
  }, [session]);

  const advisor = session?.account?.role === "advisor";

  return (
    <AppShell title="Advisees" subtitle="Your assigned students at a glance. Open a plan to review it and comment on a placement.">
      {session && !advisor ? (
        <p className="text-sm">
          This page is for advisors.{" "}
          <Link href="/login" className="underline underline-offset-4">
            Log in as an advisor
          </Link>
          .
        </p>
      ) : null}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {advisees ? (
        <ul className="mx-auto grid max-w-5xl gap-3">
          {advisees.map((a) => (
            <li key={a.student_key}>
              <Link
                href={`/planner?student=${encodeURIComponent(a.student_key)}`}
                className="panel grid gap-3 p-4 transition-colors hover:bg-secondary md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_auto] md:items-center"
              >
                <div>
                  <div className="text-lg">{a.name}</div>
                  <div className="text-sm text-muted-foreground">
                    {STANDING[a.class_standing] ?? a.class_standing} · {a.programs.join(", ") || "no program declared"}
                  </div>
                </div>
                <div className="text-sm">
                  <div>
                    <b>{fmt(a.credits_completed)}</b> credit{a.credits_completed === 1 ? "" : "s"} completed
                  </div>
                  <div className="text-muted-foreground">
                    {fmt(a.credits_in_progress)} in progress · {fmt(a.credits_planned)} planned
                  </div>
                </div>
                <div className="text-sm">
                  <div className={`flex items-center gap-1.5 ${a.on_time ? "text-[var(--status-completed)]" : "text-destructive"}`}>
                    {a.on_time ? <CheckCircle2 className="size-4" /> : <XCircle className="size-4" />}
                    {a.on_time ? "On time" : "At risk"} for {termName(a.expected_graduation)}
                  </div>
                  <div className="text-muted-foreground">
                    needs at least {a.min_terms} term{a.min_terms === 1 ? "" : "s"}, has {a.terms_left}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 text-xs md:flex-col md:items-end">
                  {a.plan_problems ? (
                    <span className="inline-flex items-center gap-1 text-destructive">
                      <XCircle className="size-3.5" /> {a.plan_problems} plan problem{a.plan_problems > 1 ? "s" : ""}
                    </span>
                  ) : null}
                  {a.overloaded_terms.length ? (
                    <span className="inline-flex items-center gap-1 text-warning">
                      <AlertTriangle className="size-3.5" /> overloaded {a.overloaded_terms.map(termName).join(", ")}
                    </span>
                  ) : null}
                  <span className="text-muted-foreground">{a.unplanned} still unplanned</span>
                  {a.open_comments ? (
                    <span className="inline-flex items-center gap-1">
                      <MessageSquare className="size-3.5" /> {a.open_comments} open
                    </span>
                  ) : null}
                  {a.awaiting_reply ? (
                    <span className="inline-flex items-center gap-1 font-medium text-primary">
                      <MessageSquare className="size-3.5" /> {a.awaiting_reply} waiting for your reply
                    </span>
                  ) : null}
                  <ArrowRight className="hidden size-4 text-muted-foreground md:block" />
                </div>
              </Link>
              {/* The card opens the plan; the record holds every course taken. */}
              <div className="mt-1 flex gap-4 px-1 text-xs">
                {[
                  ["/record", "Courses taken"],
                  ["/progress", "Degree progress"],
                  ["/audit", "Audit"],
                ].map(([to, text]) => (
                  <Link key={to} href={`${to}?student=${encodeURIComponent(a.student_key)}`} className="text-muted-foreground underline-offset-2 hover:text-foreground hover:underline">
                    {text}
                  </Link>
                ))}
              </div>
            </li>
          ))}
          {!advisees.length ? <li className="text-sm text-muted-foreground">No students are assigned to you.</li> : null}
        </ul>
      ) : advisor && !error ? (
        <p className="text-sm text-muted-foreground">Loading advisees…</p>
      ) : null}
    </AppShell>
  );
}
