"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { UserPlus } from "lucide-react";
import { input, OptionalTerm, ProgramPicker, STANDINGS, TermPicker } from "@/components/RecordFields";
import { fetchAdvisors, fetchPrograms, signup, type ProgramSummary, type SignupBody, type Standing } from "@/lib/api";
import { saveLogin } from "@/lib/session";

// A new student account with an empty record. Courses are added afterwards on
// /record; picking an advisor here is what puts the student on their dashboard.
export default function SignupPage() {
  const router = useRouter();
  const [programs, setPrograms] = useState<ProgramSummary[]>([]);
  const [advisors, setAdvisors] = useState<{ key: string; name: string }[]>([]);
  const [form, setForm] = useState<SignupBody>({
    key: "",
    password: "",
    name: "",
    class_standing: "first_year",
    start_term: "2025FA",
    expected_graduation: "2029SP",
    programs: [],
    advisor: null,
  });
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchPrograms().then(setPrograms).catch(() => setPrograms([]));
    fetchAdvisors().then(setAdvisors).catch(() => setAdvisors([]));
  }, []);

  const mismatch = confirm !== "" && confirm !== form.password;

  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center px-4 py-12">
      <Link href="/" className="font-display text-3xl">
        CourseGraph
      </Link>
      <h1 className="mt-6 text-2xl">Create an account</h1>
      <p className="text-sm text-muted-foreground">
        A student account with your own course record. Add your courses after signing up.
      </p>

      <form
        className="panel mt-4 flex flex-col gap-4 p-5"
        onSubmit={async (e) => {
          e.preventDefault();
          if (mismatch) return;
          setBusy(true);
          setError(null);
          try {
            const { token, account } = await signup({ ...form, name: form.name.trim() });
            saveLogin(token, account);
            router.push("/record");
          } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
            setBusy(false);
          }
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm">
            Name
            <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} autoComplete="name" className={input} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Login
            <input
              required
              pattern="[a-z0-9][a-z0-9_\-]{1,31}"
              title="2–32 lowercase letters, digits, - or _"
              value={form.key}
              onChange={(e) => setForm({ ...form, key: e.target.value.toLowerCase() })}
              autoComplete="username"
              className={input}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Password
            <input
              required
              type="password"
              minLength={8}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              autoComplete="new-password"
              className={input}
            />
            <span className="text-xs text-muted-foreground">At least 8 characters.</span>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Password again
            <input
              required
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              aria-invalid={mismatch}
              className={input}
            />
            {mismatch ? <span className="text-xs text-destructive">The passwords differ.</span> : null}
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Class standing
            <select value={form.class_standing} onChange={(e) => setForm({ ...form, class_standing: e.target.value as Standing })} className={input}>
              {STANDINGS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Advisor
            <select value={form.advisor ?? ""} onChange={(e) => setForm({ ...form, advisor: e.target.value || null })} className={input}>
              <option value="">None yet</option>
              {advisors.map((a) => (
                <option key={a.key} value={a.key}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Started
            <OptionalTerm value={form.start_term} fallback="2025FA" unset="Not set" onChange={(t) => setForm({ ...form, start_term: t })} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Expected graduation
            <TermPicker value={form.expected_graduation} onChange={(t) => setForm({ ...form, expected_graduation: t })} only={["SP", "FA"]} />
          </label>
        </div>
        <ProgramPicker programs={programs} value={form.programs} onChange={(p) => setForm({ ...form, programs: p })} />
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <button
          disabled={busy || mismatch}
          className="inline-flex items-center justify-center gap-2 self-start rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          <UserPlus className="size-4" /> Create account
        </button>
      </form>

      <p className="mt-4 text-sm text-muted-foreground">
        Already have one?{" "}
        <Link href="/login" className="underline underline-offset-4">
          Log in
        </Link>
      </p>
    </main>
  );
}
