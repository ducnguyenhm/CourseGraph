// Who is using the app: a login (token + account), a demo session, or
// neither. A login lasts across tabs (localStorage); a demo session belongs to
// one tab and is gone when it closes (sessionStorage), which is the
// proposal's "discarded when the session ends". Storage can be unavailable
// (private windows, blocked site data), so every access is guarded and the
// app then behaves as anonymous.

import type { AccountInfo } from "@/lib/api";

export const DEMO_STUDENT = "demo";
const LOGIN = "coursegraph:login";
const DEMO = "coursegraph:demo-session";
const EVENT = "coursegraph:session";

export type SessionState = { token: string | null; account: AccountInfo | null; demo: string | null };

export function readSession(): SessionState {
  const out: SessionState = { token: null, account: null, demo: null };
  if (typeof window === "undefined") return out;
  try {
    const raw = localStorage.getItem(LOGIN);
    if (raw) Object.assign(out, JSON.parse(raw));
  } catch {}
  try {
    out.demo = sessionStorage.getItem(DEMO);
  } catch {}
  return out;
}

function changed() {
  window.dispatchEvent(new Event(EVENT));
}

export function saveLogin(token: string, account: AccountInfo) {
  try {
    localStorage.setItem(LOGIN, JSON.stringify({ token, account }));
    // Logging in leaves demo mode: the two would disagree about whose plan it is.
    sessionStorage.removeItem(DEMO);
  } catch {}
  changed();
}

export function logout() {
  try {
    localStorage.removeItem(LOGIN);
  } catch {}
  changed();
}

export function saveDemo(token: string) {
  try {
    sessionStorage.setItem(DEMO, token);
    localStorage.removeItem(LOGIN);
  } catch {}
  changed();
}

// The server ended it (expired, or the API restarted): forget it here too.
export function endDemoLocally() {
  try {
    sessionStorage.removeItem(DEMO);
  } catch {}
  changed();
}

export function onSessionChange(fn: () => void): () => void {
  window.addEventListener(EVENT, fn);
  window.addEventListener("storage", fn);
  return () => {
    window.removeEventListener(EVENT, fn);
    window.removeEventListener("storage", fn);
  };
}
