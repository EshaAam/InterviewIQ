"use client";

/**
 * Who is signed in, resolved from the token by asking the backend.
 *
 * There is no client-side JWT decoding here on purpose: the only authority on
 * whether a token is still good is `GET /auth/me`. A failure means the token
 * is gone or dead, and the caller is sent to /login.
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { me } from "./api";
import { clearTokens, getAccessToken, type User } from "./auth";

export function useUser({ redirectTo = "/login" }: { redirectTo?: string | null } = {}) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    if (!getAccessToken()) {
      setLoading(false);
      if (redirectTo) router.replace(redirectTo);
      return;
    }

    me()
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch(() => {
        clearTokens();
        if (!cancelled && redirectTo) router.replace(redirectTo);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [router, redirectTo]);

  return { user, loading };
}

/**
 * The candidate has no "list my sessions" endpoint — that is recruiter-only —
 * so the app remembers the session it just created to offer a way back to it.
 */
const LAST_SESSION = "interviewiq.last_session";

export function rememberSession(sessionId: string): void {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(LAST_SESSION, sessionId);
  }
}

export function recallSession(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(LAST_SESSION);
}
