import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { CATALOG_YEAR } from "@/components/AppShell";
import { DemoButton } from "@/components/DemoButton";

const FEATURES = [
  { href: "/graph", name: "Prerequisite graph", note: "Every course coloured by status; select one to trace what it needs and what it opens." },
  { href: "/planner", name: "Semester planner", note: "Drag courses into terms; a placement that breaks a prerequisite is refused, naming it." },
  { href: "/explore", name: "Major and minor explorer", note: "What adding a program costs: courses that count twice, new credits, extra terms." },
  { href: "/progress", name: "Degree progress", note: "Every declared program and the B.A. requirements, complete to outstanding." },
];

const SHOWCASE = [
  {
    href: "/courses/CSC-322",
    code: "CSC 322",
    note: "CSC 231 and CSC 235 — both required.",
  },
  {
    href: "/courses/CSC-340",
    code: "CSC 340",
    note: "Either CSC 231 or CSC 235 — the same two courses, but a choice.",
  },
  {
    href: "/courses/MATH-323",
    code: "MATH 323",
    note: "Cites CSC 233, retired and renumbered to CSC 236.",
  },
  {
    href: "/courses/CSC-498",
    code: "CSC 498",
    note: "Senior standing plus one CSC course numbered 300 or above.",
  },
];

export default function Home() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-12 sm:px-6 sm:py-20">
      <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
        Catalog {CATALOG_YEAR} · Checkpoint 4
      </p>
      <h1 className="mt-3 font-display text-4xl leading-tight sm:text-5xl">CourseGraph</h1>
      <p className="mt-4 max-w-xl text-muted-foreground">
        An interactive prerequisite graph and multi-major degree planner for the
        DePauw catalog.
      </p>

      <div className="mt-8 flex flex-wrap items-start gap-3">
        <DemoButton>Try the demo, no account needed</DemoButton>
        <Link
          href="/login"
          className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm hover:bg-secondary"
        >
          Log in
        </Link>
        <Link
          href="/signup"
          className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm hover:bg-secondary"
        >
          Sign up
        </Link>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        The demo plans for a fictional student. Your changes stay in this tab and are discarded when you leave.
      </p>

      <ul className="mt-10 grid gap-2 sm:grid-cols-2">
        {FEATURES.map((f) => (
          <li key={f.href}>
            <Link href={f.href} className="panel block h-full p-3 text-sm transition-colors hover:bg-secondary">
              <span className="flex items-center gap-1 font-medium">
                {f.name} <ArrowRight className="size-3.5" />
              </span>
              <span className="mt-1 block text-muted-foreground">{f.note}</span>
            </Link>
          </li>
        ))}
      </ul>

      <section className="mt-14">
        <h2 className="text-xl">Why prerequisites are expression trees</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          A flat list of prerequisite edges cannot represent a choice. CSC 322 and
          CSC 340 name the same two courses, so a flat list stores both as{" "}
          <code className="font-mono text-xs">[CSC 231, CSC 235]</code> — losing the
          fact that one demands both and the other accepts either.
        </p>

        <ul className="mt-5 grid gap-2">
          {SHOWCASE.map((s) => (
            <li key={s.href}>
              <Link
                href={s.href}
                className="panel flex items-baseline gap-3 p-3 text-sm transition-colors hover:bg-secondary"
              >
                <span className="font-mono font-medium">{s.code}</span>
                <span className="text-muted-foreground">{s.note}</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
