import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { CATALOG_YEAR } from "@/components/AppShell";

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
    <main className="mx-auto max-w-3xl px-6 py-20">
      <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
        Catalog {CATALOG_YEAR} · Checkpoint 2
      </p>
      <h1 className="mt-3 font-display text-5xl leading-tight">CourseGraph</h1>
      <p className="mt-4 max-w-xl text-muted-foreground">
        An interactive prerequisite graph and multi-major degree planner for the
        DePauw catalog.
      </p>

      <Link
        href="/graph"
        className="mt-8 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:opacity-90"
      >
        Open the prerequisite graph
        <ArrowRight className="size-4" />
      </Link>

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
