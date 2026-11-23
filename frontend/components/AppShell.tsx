"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  CalendarRange,
  LogIn,
  LogOut,
  ClipboardCheck,
  Compass,
  NotebookPen,
  GraduationCap,
  Network,
  Users,
} from "lucide-react";
import type { ReactNode } from "react";
import { endDemoSession } from "@/lib/api";
import { logout } from "@/lib/session";
import { useSession } from "@/lib/useSession";
import { useStudent } from "@/lib/useStudent";

export const CATALOG_YEAR = "2025–2026";

// The proposal's five destinations, plus the requirement audit and the course
// record. Each shows the logged-in student's own record (useStudent), which
// only that student edits; Advisees is for advisors.
const NAV = [
  { to: "/graph", label: "Graph", icon: Network },
  { to: "/planner", label: "Planner", icon: CalendarRange },
  { to: "/audit", label: "Audit", icon: ClipboardCheck },
  { to: "/explore", label: "Explore", icon: Compass },
  { to: "/progress", label: "Progress", icon: GraduationCap },
  { to: "/record", label: "Record", icon: NotebookPen },
  { to: "/advisees", label: "Advisees", icon: Users, advisorOnly: true },
] as const;

// An advisor's pages are about the advisee in ?student=, so the links keep it.
function useNav() {
  const viewer = useStudent();
  const advisor = !!viewer?.advisor;
  const keep = advisor && viewer?.student ? `?student=${encodeURIComponent(viewer.student)}` : "";
  return NAV.filter((n) => !("advisorOnly" in n && !advisor)).map((n) => ({
    ...n,
    href: "advisorOnly" in n ? n.to : n.to + keep,
  }));
}

// Who is using the app, and the way out: end the demo, log out, or log in.
// Leaving reloads the page rather than pushing a route, so no page keeps
// state (or a URL rewrite in flight) from the session that just ended.
function AccountBox({ compact = false }: { compact?: boolean }) {
  const session = useSession();
  if (!session) return null;
  const button = "inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-xs hover:bg-secondary";
  if (session.demo) {
    return (
      <div className={compact ? "flex items-center gap-2" : "flex flex-col gap-2"}>
        <span className="text-xs">
          <span className="font-medium text-foreground">Demo mode</span>
          {compact ? null : <span className="block text-muted-foreground">Changes are discarded when you leave.</span>}
        </span>
        <button
          className={button}
          onClick={async () => {
            await endDemoSession();
            window.location.assign("/");
          }}
        >
          <LogOut className="size-3.5" /> End demo
        </button>
      </div>
    );
  }
  if (session.account) {
    return (
      <div className={compact ? "flex items-center gap-2" : "flex flex-col gap-2"}>
        <span className="text-xs">
          <span className="font-medium text-foreground">{session.account.name}</span>
          {compact ? null : <span className="block capitalize text-muted-foreground">{session.account.role}</span>}
        </span>
        <button
          className={button}
          onClick={() => {
            logout();
            window.location.assign("/login");
          }}
        >
          <LogOut className="size-3.5" /> Log out
        </button>
      </div>
    );
  }
  return (
    <Link href="/login" className={button}>
      <LogIn className="size-3.5" /> Log in
    </Link>
  );
}

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
  const nav = useNav();

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
          {nav.map(({ to, href, label, icon: Icon }) => (
            <Link
              key={to}
              href={href}
              className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors hover:bg-secondary hover:text-foreground ${
                pathname.startsWith(to) ? "bg-secondary font-medium text-foreground" : "text-muted-foreground"
              }`}
            >
              <Icon className="size-4" />
              {label}
            </Link>
          ))}
        </div>

        <div className="border-t border-border px-5 py-4">
          <AccountBox />
        </div>
        <div className="border-t border-border px-5 py-4 text-xs text-muted-foreground">
          <div className="font-medium text-foreground">Checkpoint 4</div>
          <div>Planner, advising, demo mode</div>
        </div>
      </nav>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Below md the sidebar is hidden: the same links as a scrolling strip. */}
        <div className="sticky top-0 z-30 border-b border-border bg-surface md:hidden">
          <div className="flex items-center justify-between gap-3 px-4 py-2">
            <Link href="/" className="font-display text-lg leading-none">
              CourseGraph
            </Link>
            <AccountBox compact />
          </div>
          <div className="flex gap-1 overflow-x-auto px-2 pb-2">
            {nav.map(({ to, href, label, icon: Icon }) => (
              <Link
                key={to}
                href={href}
                className={`flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs ${
                  pathname.startsWith(to) ? "bg-secondary font-medium text-foreground" : "text-muted-foreground"
                }`}
              >
                <Icon className="size-3.5" />
                {label}
              </Link>
            ))}
          </div>
        </div>
        <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border bg-surface px-4 py-4 sm:px-6">
          <div>
            <h1 className="text-2xl">{title}</h1>
            {subtitle ? (
              <p className="text-sm text-muted-foreground">{subtitle}</p>
            ) : null}
          </div>
          {aside}
        </header>

        <main className={bleed ? "min-h-0 flex-1" : "flex-1 p-4 sm:p-6"}>{children}</main>
      </div>
    </div>
  );
}
