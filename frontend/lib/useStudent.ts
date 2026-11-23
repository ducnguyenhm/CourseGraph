"use client";

import { useEffect, useState } from "react";
import { DEMO_STUDENT, type SessionState } from "@/lib/session";
import { useSession } from "@/lib/useSession";

export type Viewer = {
  session: SessionState;
  // Whose record the page shows; null when nobody is logged in, or an advisor
  // has not picked an advisee.
  student: string | null;
  advisor: boolean;
};

// The login decides whose record every page shows: a student sees their own,
// a demo session the demo student, and an advisor the advisee named in
// ?student= (they arrive from /advisees). A student's ?student= is ignored, so
// a link cannot open someone else's record; the API refuses it anyway.
// Null until mounted, like useSession.
export function useStudent(): Viewer | null {
  const session = useSession();
  const [param, setParam] = useState<string | null>(null);
  useEffect(() => {
    setParam(new URLSearchParams(window.location.search).get("student"));
  }, []);
  if (!session) return null;
  const advisor = session.account?.role === "advisor";
  const student = session.demo
    ? DEMO_STUDENT
    : advisor
      ? param
      : (session.account?.student_key ?? null);
  return { session, student, advisor };
}
