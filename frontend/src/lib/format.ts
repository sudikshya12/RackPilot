export function fmtTime(iso?: string | null, withDate = false): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const t = d.toISOString();
  return withDate ? `${t.slice(0, 10)} ${t.slice(11, 19)}Z` : `${t.slice(11, 19)}Z`;
}
export function fmtDateTime(iso?: string | null) { return fmtTime(iso, true); }

export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "Unavailable";
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m < 60) return `${m}m ${s.toString().padStart(2, "0")}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${(m % 60).toString().padStart(2, "0")}m`;
}

export function elapsedSince(iso: string, now = Date.now()): string {
  const s = Math.max(0, (now - new Date(iso).getTime()) / 1000);
  return fmtDuration(s);
}

export function relative(iso?: string | null, now = Date.now()): string {
  if (!iso) return "—";
  const s = Math.round((now - new Date(iso).getTime()) / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export const human = (s?: string | null) => (s ? s.replace(/_/g, " ") : "—");
export const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Compact whole-unit age for lists: 42s, 7m, 3h, 2d. */
export function age(iso?: string | null, now = Date.now()): string {
  if (!iso) return "";
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}
