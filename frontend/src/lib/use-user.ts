"use client";

/**
 * Who is signed in, resolved from the token by asking the backend.
 *
 * There is no client-side JWT decoding here on purpose: the only authority on
 * whether a token is still good is `GET /auth/me`. A failure means the token
 * is gone or dead, and the caller is sent to /login — with `next` set to the
 * page they were on, so signing in brings them back to it.
 */

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { me } from "./api";
import { clearTokens, getAccessToken, TOKENS_CHANGED, type User } from "./auth";

/**
 * localStorage is an external store, so read it with useSyncExternalStore
 * rather than copying it into state from an effect. The server snapshot is
 * `undefined` ("can't know yet") — the server has no localStorage — and React
 * swaps in the real value right after hydration without a mismatch.
 *
 * Two events can change it: `storage` (another tab signed in or out) and
 * TOKENS_CHANGED (this tab did — e.g. api.ts cleared them after a failed
 * refresh). Either way the page reacts on its own, with no plumbing.
 */
function subscribeToTokens(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(TOKENS_CHANGED, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(TOKENS_CHANGED, onChange);
  };
}

/**
 * A boolean, not the token itself: a silent refresh swaps the token string
 * every 15 minutes, and that must not look like "a different user signed in"
 * — it would unmount the page mid-interview and lose the typed answer.
 */
function useHasToken(): boolean | undefined {
  return useSyncExternalStore(
    subscribeToTokens,
    () => getAccessToken() !== null,
    () => undefined,
  );
}

/**
 * True between a deliberate sign-out and the signed-in pages unmounting.
 * Without it, clearing the tokens looks exactly like an expired session to
 * every mounted `useUser`, whose redirect to /login would land after — and
 * override — sign-out's own navigation to the landing page.
 */
let signingOut = false;

/** Sign out and go to the public landing page. */
export function useSignOut(): () => void {
  const router = useRouter();
  return useCallback(() => {
    signingOut = true;
    clearTokens();
    router.replace("/");
  }, [router]);
}

export function useUser({ redirectTo = "/login" }: { redirectTo?: string | null } = {}) {
  const router = useRouter();
  const hasToken = useHasToken();
  // undefined = not asked yet; the /auth/me answer otherwise.
  const [fetched, setFetched] = useState<User | undefined>(undefined);

  useEffect(() => {
    if (hasToken === undefined) return; // still hydrating
    if (!hasToken) {
      if (redirectTo && !signingOut) {
        router.replace(redirectTo === "/login" ? loginHref(window.location.pathname) : redirectTo);
      }
      return;
    }

    let cancelled = false;
    me()
      .then((user) => {
        if (!cancelled) setFetched(user);
      })
      // Clearing fires TOKENS_CHANGED → hasToken turns false → this effect
      // re-runs and takes the redirect branch above.
      .catch(() => clearTokens());

    return () => {
      cancelled = true;
    };
  }, [hasToken, router, redirectTo]);

  // Sign-out is over once the pages that were showing have unmounted; from
  // then on a missing token means "send to sign-in" again (e.g. pressing Back
  // into /interview).
  useEffect(
    () => () => {
      signingOut = false;
    },
    [],
  );

  return {
    user: hasToken ? (fetched ?? null) : null,
    // Three states: asking (loading), signed in (user), signed out (neither).
    loading: hasToken === undefined || (hasToken && fetched === undefined),
  };
}

/** Where a user lands after sign-in, and where "home" links point. */
export function homeFor(user: Pick<User, "role">): string {
  return user.role === "recruiter" ? "/recruiter/review" : "/interview";
}

/** The sign-in page, remembering where to go afterwards. */
export function loginHref(next?: string): string {
  return next && next !== "/" ? `/login?next=${encodeURIComponent(next)}` : "/login";
}

/**
 * Where to send someone right after they sign in: `next` if it is one of their
 * own pages, otherwise their home. Matching on the role's own path prefixes
 * (rather than "anything starting with /") is what keeps `next` from being an
 * open redirect — `//evil.example` or `/\evil.example` match neither — and
 * stops a recruiter being sent to a candidate page that would only 403.
 */
export function destinationFor(user: Pick<User, "role">, next: string | null): string {
  const prefixes = user.role === "recruiter" ? ["/recruiter"] : ["/interview", "/reports"];
  const ok =
    next !== null &&
    prefixes.some((p) => next === p || next.startsWith(`${p}/`) || next.startsWith(`${p}?`));
  return ok ? next : homeFor(user);
}
