/** Small formatting helpers, shared so timestamps read the same everywhere. */

const timeFormat = new Intl.DateTimeFormat("en-IN", {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const dayFormat = new Intl.DateTimeFormat("en-IN", {
  day: "2-digit",
  month: "short",
});

/** 14:32 — the ledger's timestamp. */
export function clock(iso: string | null | undefined): string {
  if (!iso) return "--:--";
  return timeFormat.format(new Date(iso));
}

/** 26 Oct */
export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dayFormat.format(new Date(iso));
}

/** "13h 02m" until a future moment, or "now". */
export function until(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "now";
  const minutes = Math.floor(ms / 60000);
  const hours = Math.floor(minutes / 60);
  if (hours >= 1) return `${hours}h ${String(minutes % 60).padStart(2, "0")}m`;
  return `${minutes}m`;
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return count === 1 ? one : many;
}

export function initials(name: string | null | undefined, email?: string | null): string {
  const source = (name ?? email ?? "?").trim();
  const parts = source.split(/\s+/).slice(0, 2);
  return parts.map((part) => part.charAt(0).toUpperCase()).join("") || "?";
}