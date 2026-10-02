/**
 * Token storage.
 *
 * Deliberately dependency-free: `api.ts` imports from here, never the other
 * way round, so there is no cycle between "how we talk to the backend" and
 * "where the token lives".
 *
 * Tokens sit in localStorage because the backend hands back a bearer pair
 * (`TokenPair`) rather than setting a cookie. If the backend ever moves to
 * httpOnly cookies, this file is the only thing that has to change.
 */

const ACCESS_KEY = "interviewiq.access_token";
const REFRESH_KEY = "interviewiq.refresh_token";

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: string;
};

export type UserRole = "candidate" | "recruiter";

export type User = {
  id: string;
  email: string;
  role: UserRole;
  created_at: string;
};

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}

/**
 * Fired on `window` whenever this tab stores or clears tokens. The browser's
 * own `storage` event only reaches *other* tabs, so without this a failed
 * refresh deep inside `api.ts` would clear the tokens and nobody on this page
 * would notice.
 */
export const TOKENS_CHANGED = "interviewiq:tokens-changed";

export function storeTokens(pair: TokenPair): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ACCESS_KEY, pair.access_token);
  window.localStorage.setItem(REFRESH_KEY, pair.refresh_token);
  window.dispatchEvent(new Event(TOKENS_CHANGED));
}

export function clearTokens(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(ACCESS_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
  window.dispatchEvent(new Event(TOKENS_CHANGED));
}
