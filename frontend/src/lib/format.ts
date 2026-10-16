/** Small display helpers shared by the candidate and recruiter screens. */

export function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  return `${Math.round(hours / 24)} d ago`;
}

/**
 * "today, 11:31", "yesterday, 09:05", "3 days ago", "last week", or a date —
 * how a person would say when something happened.
 */
export function humanWhen(iso: string, now: Date = new Date()): string {
  const then = new Date(iso);
  const time = then.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((startOfDay(now) - startOfDay(then)) / 86_400_000);
  if (days <= 0) return `today, ${time}`;
  if (days === 1) return `yesterday, ${time}`;
  if (days < 7) return `${days} days ago`;
  if (days < 14) return "last week";
  return then.toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });
}

/** UUIDs are unreadable in a table; the first block is enough to tell rows apart. */
export function shortId(id: string): string {
  return `${id.slice(0, 4)}…${id.slice(-2)}`;
}

/** The first eight characters — how a session is named to its owner. */
export function sessionName(id: string): string {
  return id.slice(0, 8);
}

/** 83_000 → "1m 23s"; 4_200 → "4s". */
export function duration(ms: number): string {
  const total = Math.round(ms / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

/** A 0..1 score on the 0..100 scale people read, clamped and rounded. */
export function toHundred(score: number): number {
  return Math.round(Math.min(Math.max(score, 0), 1) * 100);
}

/** Whole minutes until `iso`, never negative. */
export function minutesLeft(iso: string, now: number = Date.now()): number {
  return Math.max(0, Math.ceil((new Date(iso).getTime() - now) / 60_000));
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
