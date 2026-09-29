/** Small display helpers shared by the recruiter tables. */

export function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  return `${Math.round(hours / 24)} d ago`;
}

/** UUIDs are unreadable in a table; the first block is enough to tell rows apart. */
export function shortId(id: string): string {
  return `${id.slice(0, 4)}…${id.slice(-2)}`;
}
