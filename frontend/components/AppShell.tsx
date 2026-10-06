"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  CalendarRange,
  Compass,
  GraduationCap,
  Network,
  Users,
} from "lucide-react";
import type { ReactNode } from "react";

export const CATALOG_YEAR = "2025–2026";

// The proposal's five destinations. Only Graph exists at Checkpoint 2; the
// rest are shown inert so the intended structure is legible without
// pretending to features that are not built.
const NAV = [
  { to: "/graph", label: "Graph", icon: Network, ready: true },
  { to: "/planner", label: "Planner", icon: CalendarRange, ready: false },
  { to: "/explore", label: "Explore", icon: Compass, ready: false },
  { to: "/progress", label: "Progress", icon: GraduationCap, ready: false },
  { to: "/advisees", label: "Advisees", icon: Users, ready: false },
] as const;

export function AppShell({
  title,
  subtitle,
  children,
  bleed = false,
  aside,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  bleed?: boolean;
  aside?: ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen bg-background">
      <nav className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-border bg-surface md:flex">
        <Link href="/" className="block border-b border-border px-5 py-5">
          <span className="font-display text-xl leading-none">CourseGraph</span>
          <span className="mt-1 block text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
            Catalog {CATALOG_YEAR}
          </span>
        </Link>

        <div className="flex flex-1 flex-col gap-0.5 p-3">
          {NAV.map(({ to, label, icon: Icon, ready }) =>
            ready ? (
              <Link
                key={to}
                href={to}
                className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors hover:bg-secondary hover:text-foreground ${
                  pathname.startsWith(to)
                    ? "bg-secondary font-medium text-foreground"
                    : "text-muted-foreground"
                }`}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            ) : (
              <span
                key={to}
                aria-disabled
                title="Not built yet"
                className="flex cursor-not-allowed items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground/45"
              >
                <Icon className="size-4" />
                {label}
              </span>
            ),
          )}
        </div>

        <div className="border-t border-border px-5 py-4 text-xs text-muted-foreground">
          <div className="font-medium text-foreground">Checkpoint 2</div>
          <div>Prerequisite graph</div>
        </div>
      </nav>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border bg-surface px-6 py-4">
          <div>
            <h1 className="text-2xl">{title}</h1>
            {subtitle ? (
              <p className="text-sm text-muted-foreground">{subtitle}</p>
            ) : null}
          </div>
          {aside}
        </header>

        <main className={bleed ? "min-h-0 flex-1" : "flex-1 p-6"}>{children}</main>
      </div>
    </div>
  );
}
