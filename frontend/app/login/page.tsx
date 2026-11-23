"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowRight, LogIn } from "lucide-react";
import { login, startDemoSession } from "@/lib/api";
import { saveDemo, saveLogin } from "@/lib/session";

// The seeded demonstration logins (backend/data/demo_accounts.json). The
// people are fictional and the passwords public on purpose; each student can
// edit their own record freely, and re-seeding puts it back.
const DEMO_LOGINS = [
  { key: "advisor", password: "advisor-demo", who: "Prof. Brian Howard, advisor to both demo students" },
  { key: "demo", password: "student-demo", who: "Duc Nguyen, the demo student (junior, CS major)" },
  { key: "demo-2", password: "student-demo", who: "John Dee (sophomore, MATH major)" },
];

export default function LoginPage() {
  const router = useRouter();
  const [key, setKey] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(k = key, p = password) {
    setBusy(true);
    setError(null);
    try {
      const { token, account } = await login(k, p);
      saveLogin(token, account);
      router.push(account.role === "advisor" ? "/advisees" : "/planner");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 py-12">
      <Link href="/" className="font-display text-3xl">
        CourseGraph
      </Link>
      <h1 className="mt-6 text-2xl">Log in</h1>

      <form
        className="panel mt-4 flex flex-col gap-3 p-5"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <label className="flex flex-col gap-1 text-sm">
          Login
          <input
            value={key}
            onChange={(e) => setKey(e.target.value)}
            autoComplete="username"
            className="rounded-md border border-border bg-surface px-3 py-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            className="rounded-md border border-border bg-surface px-3 py-2"
          />
        </label>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <button
          disabled={busy || !key || !password}
          className="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          <LogIn className="size-4" /> Log in
        </button>
      </form>

      <p className="mt-3 text-sm text-muted-foreground">
        New here?{" "}
        <Link href="/signup" className="underline underline-offset-4">
          Create an account
        </Link>
      </p>

      <section className="mt-6">
        <h2 className="text-sm font-medium">Demonstration logins</h2>
        <ul className="mt-2 flex flex-col gap-2">
          {DEMO_LOGINS.map((d) => (
            <li key={d.key}>
              <button
                onClick={() => submit(d.key, d.password)}
                disabled={busy}
                className="panel flex w-full items-baseline justify-between gap-3 p-3 text-left text-sm hover:bg-secondary"
              >
                <span>
                  <span className="font-mono font-medium">{d.key}</span>
                  <span className="block text-xs text-muted-foreground">{d.who}</span>
                </span>
                <span className="shrink-0 font-mono text-xs text-muted-foreground">{d.password}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <button
        onClick={async () => {
          const { token } = await startDemoSession();
          saveDemo(token);
          router.push("/planner");
        }}
        className="mt-6 inline-flex items-center gap-2 self-start text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
      >
        Or try the demo without an account <ArrowRight className="size-4" />
      </button>
    </main>
  );
}
