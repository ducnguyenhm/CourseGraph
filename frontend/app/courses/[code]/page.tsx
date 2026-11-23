"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { PrereqTree } from "@/components/PrereqTree";
import { credits, fetchCourse, type CourseDetail } from "@/lib/api";

export default function CoursePage({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = use(params);
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCourse(decodeURIComponent(code))
      .then(setCourse)
      .catch((e) => setError(String(e)));
  }, [code]);

  if (error)
    return (
      <AppShell title="Course">
        <pre className="text-sm text-destructive">{error}</pre>
        <Link href="/graph" className="text-sm underline underline-offset-2">
          ← back to graph
        </Link>
      </AppShell>
    );

  if (!course)
    return (
      <AppShell title="Course">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </AppShell>
    );

  const tags = [
    course.distribution,
    ...course.competence_variants,
    ...course.attributes,
  ].filter(Boolean);

  return (
    <AppShell
      title={`${course.label} — ${course.title}`}
      subtitle={`${credits(course.credits_min, course.credits_max)} credit · catalog ${course.catalog_year}`}
      aside={
        <Link href="/graph" className="text-xs underline underline-offset-2">
          ← back to graph
        </Link>
      }
    >
      <div className="max-w-4xl space-y-6">
        {tags.length ? (
          <div className="flex flex-wrap gap-1">
            {tags.map((t) => (
              <span key={t} className="rounded bg-secondary px-2 py-0.5 text-xs">
                {t}
              </span>
            ))}
          </div>
        ) : null}

        {/* The Checkpoint 1 deliverable: the stored tree beside the wording
            it was read from. */}
        <div className="grid gap-5 md:grid-cols-2">
          <section className="panel p-4">
            <h2 className="mb-2 text-xs uppercase tracking-wider text-muted-foreground">
              Catalog text
            </h2>
            <p className="font-mono text-xs leading-relaxed">
              {course.prereq_raw || (
                <span className="not-italic text-muted-foreground">
                  The catalog prints no prerequisite sentence for this course.
                </span>
              )}
            </p>
          </section>

          <section className="panel p-4">
            <h2 className="mb-2 text-xs uppercase tracking-wider text-muted-foreground">
              Parsed expression tree
            </h2>
            <div className="text-sm">
              <PrereqTree node={course.prereq_expr} />
            </div>
          </section>
        </div>

        <details className="panel p-4">
          <summary className="cursor-pointer text-xs uppercase tracking-wider text-muted-foreground">
            Stored JSONB
          </summary>
          <pre className="mt-3 overflow-x-auto font-mono text-xs">
            {JSON.stringify(course.prereq_expr, null, 2)}
          </pre>
        </details>

        {Object.keys(course.extra).length > 0 ? (
          <details className="panel p-4">
            <summary className="cursor-pointer text-xs uppercase tracking-wider text-muted-foreground">
              Curated fields not yet modelled ({Object.keys(course.extra).join(", ")})
            </summary>
            <pre className="mt-3 overflow-x-auto font-mono text-xs">
              {JSON.stringify(course.extra, null, 2)}
            </pre>
          </details>
        ) : null}
      </div>
    </AppShell>
  );
}
