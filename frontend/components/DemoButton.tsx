"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowRight } from "lucide-react";
import { startDemoSession } from "@/lib/api";
import { saveDemo } from "@/lib/session";

// Starts a demonstration session: a private copy of the demo student's plan,
// no account, nothing saved.
export function DemoButton({ to = "/planner", children }: { to?: string; children: React.ReactNode }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <span className="inline-flex flex-col">
      <button
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            const { token } = await startDemoSession();
            saveDemo(token);
            router.push(to);
          } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
            setBusy(false);
          }
        }}
        className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:opacity-90 disabled:opacity-60"
      >
        {children}
        <ArrowRight className="size-4" />
      </button>
      {error ? <span className="mt-1 text-xs text-destructive">{error}</span> : null}
    </span>
  );
}
