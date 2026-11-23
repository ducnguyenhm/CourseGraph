import Link from "next/link";
import { LogIn } from "lucide-react";
import { DemoButton } from "@/components/DemoButton";

// Shown where a page needs a student and the visitor has none: anonymous
// visitors log in or try the demo; an advisor picks an advisee first.
export function SignInPrompt({ advisor = false, to }: { advisor?: boolean; to: string }) {
  if (advisor) {
    return (
      <div className="panel mx-auto flex max-w-xl flex-col gap-3 p-5 text-sm">
        <p>Pick an advisee to see their record here.</p>
        <Link href="/advisees" className="underline underline-offset-4">
          Go to your advisees
        </Link>
      </div>
    );
  }
  return (
    <div className="panel mx-auto flex max-w-xl flex-col gap-4 p-5 text-sm">
      <p>Log in to see your own record here, or try the demo student without an account.</p>
      <div className="flex flex-wrap items-center gap-3">
        <Link
          href="/login"
          className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 hover:bg-secondary"
        >
          <LogIn className="size-4" /> Log in
        </Link>
        <DemoButton to={to}>Try the demo</DemoButton>
      </div>
    </div>
  );
}
