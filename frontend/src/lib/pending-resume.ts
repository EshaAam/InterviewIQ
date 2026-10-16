/**
 * A resume chosen on the public landing page before the person has signed in.
 *
 * Held in module memory, which survives the client-side trip landing →
 * /login → /interview, and mirrored into sessionStorage (as a data URL) so a
 * full page load on the way — a reload, a stale tab, a hard redirect — doesn't
 * drop it. Resumes are capped at 2 MB, well inside sessionStorage's quota; if
 * the copy can't be written anyway, memory still carries the common case.
 */

import { useSyncExternalStore } from "react";

const KEY = "interviewiq.pending-resume";
/** Older than this, a stashed file is a leftover, not something just chosen. */
const MAX_AGE_MS = 30 * 60 * 1000;

type Stashed = { name: string; type: string; data: string; at: number };

let pending: File | null = null;

export function setPendingResume(file: File): void {
  pending = file;
  try {
    const reader = new FileReader();
    reader.onload = () => {
      // Skip the write if it was already taken or replaced while reading,
      // or it would come back as a ghost on the next visit.
      if (pending !== file || typeof reader.result !== "string") return;
      const stash: Stashed = {
        name: file.name,
        type: file.type,
        data: reader.result,
        at: Date.now(),
      };
      try {
        window.sessionStorage.setItem(KEY, JSON.stringify(stash));
      } catch {
        /* quota or storage disabled: memory still has it */
      }
    };
    reader.readAsDataURL(file);
  } catch {
    /* no FileReader: memory still has it */
  }
}

export function peekPendingResume(): File | null {
  if (pending || typeof window === "undefined") return pending;
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (!raw) return null;
    const stash = JSON.parse(raw) as Stashed;
    if (Date.now() - stash.at > MAX_AGE_MS) {
      window.sessionStorage.removeItem(KEY);
      return null;
    }
    const bytes = Uint8Array.from(atob(stash.data.split(",")[1] ?? ""), (c) => c.charCodeAt(0));
    // Cached in memory so repeated peeks return the same File object.
    pending = new File([bytes], stash.name, { type: stash.type });
    return pending;
  } catch {
    return null;
  }
}

export function clearPendingResume(): void {
  pending = null;
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    /* nothing stashed, or no storage */
  }
}

/** Read it once and forget it, so it is acted on exactly once. */
export function takePendingResume(): File | null {
  const file = peekPendingResume();
  clearPendingResume();
  return file;
}

const noSubscription = () => () => {};

/**
 * The pending file for rendering. The server snapshot is null (no storage
 * there), so a page prerendered without it hydrates cleanly and then shows it.
 */
export function usePendingResume(): File | null {
  return useSyncExternalStore(noSubscription, peekPendingResume, () => null);
}
