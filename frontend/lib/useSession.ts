"use client";

import { useEffect, useState } from "react";
import { onSessionChange, readSession, type SessionState } from "@/lib/session";

// Null until mounted: the server render cannot know, and guessing "anonymous"
// would flash the wrong controls for a logged-in user.
export function useSession(): SessionState | null {
  const [state, setState] = useState<SessionState | null>(null);
  useEffect(() => {
    setState(readSession());
    return onSessionChange(() => setState(readSession()));
  }, []);
  return state;
}
