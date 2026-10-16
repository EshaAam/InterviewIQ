/**
 * A resume chosen on the public landing page before the person has signed in.
 *
 * Held in module memory, not storage: a `File` can't be serialised into
 * localStorage, and the trip landing → /login → /interview is all client-side
 * navigation, so the module (and the file) survives it. A full page reload
 * drops it, which only costs the person choosing the file again.
 */

let pending: File | null = null;

export function setPendingResume(file: File): void {
  pending = file;
}

export function peekPendingResume(): File | null {
  return pending;
}

export function clearPendingResume(): void {
  pending = null;
}
