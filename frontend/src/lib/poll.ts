/**
 * Polling for the backend's 202-style endpoints.
 *
 * Every wait has three exits, and callers must handle all of them:
 *   - settled   → the promise resolves with the value that satisfied `done`
 *   - failed    → it rejects with the ApiError (a 4xx is a real answer)
 *   - gave up   → it rejects with PollTimeout
 *
 * "Gave up" is not "failed". The worker keeps going after the browser stops
 * waiting, so a PollTimeout should become "still working — keep waiting?",
 * never an error that throws away the id being waited on.
 */

import { ApiError } from "./api";

export class PollTimeout extends Error {
  constructor() {
    super("Still working — this is taking longer than usual.");
    this.name = "PollTimeout";
  }
}

export type PollOptions = {
  /** Abort to stop polling (e.g. the component unmounted). */
  signal?: AbortSignal;
  /** Give up after this long. The server may still finish later. */
  timeoutMs?: number;
  /**
   * Called with the error when a check fails in a way worth retrying (a
   * network drop or a 5xx), and with `null` once a check succeeds again —
   * enough to show and hide a "reconnecting…" line.
   */
  onConnectionChange?: (problem: unknown | null) => void;
};

const FIRST_DELAY_MS = 1000;
const MAX_DELAY_MS = 5000;

export async function pollUntil<T>(
  fetcher: () => Promise<T>,
  done: (value: T) => boolean,
  { signal, timeoutMs = 3 * 60_000, onConnectionChange }: PollOptions = {},
): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  let delay = FIRST_DELAY_MS;
  let troubled = false;

  // Check *before* the first sleep: with the LLM cache warm, the work is
  // often already done, and there's no reason to wait a second to find out.
  for (;;) {
    signal?.throwIfAborted();
    try {
      const latest = await fetcher();
      if (troubled) {
        troubled = false;
        onConnectionChange?.(null);
      }
      if (done(latest)) return latest;
    } catch (err) {
      if (!isRetryable(err)) throw err;
      troubled = true;
      onConnectionChange?.(err);
    }

    if (Date.now() + delay > deadline) throw new PollTimeout();
    await sleep(delay, signal);
    // Back off gently: quick checks early, when the answer is likely, and
    // one request every few seconds for a long wait.
    delay = Math.min(delay * 1.5, MAX_DELAY_MS);
  }
}

/** A network failure (not an ApiError) or a 5xx might clear up; a 4xx won't. */
function isRetryable(err: unknown): boolean {
  if (isAbort(err)) return false;
  return !(err instanceof ApiError) || err.status >= 500;
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const id = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(id);
        reject(signal.reason);
      },
      { once: true },
    );
  });
}

/**
 * True for the rejection you get after calling `controller.abort()`.
 *
 * Checked by name, not `instanceof DOMException`: an abort can come from a
 * different realm's DOMException (Node's, under jsdom; a fetch polyfill's),
 * and `instanceof` is false across realms. The name is the contract.
 */
export function isAbort(err: unknown): boolean {
  return (err as { name?: unknown } | null)?.name === "AbortError";
}
