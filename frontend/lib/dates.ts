// Date helpers operating in UTC, to match the backend (which anchors on UTC dates).

import type { Range } from "./types";

export function todayUTC(): string {
  return new Date().toISOString().slice(0, 10);
}

const WEEKDAYS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function parse(d: string): Date {
  return new Date(`${d}T00:00:00Z`);
}

/** Techy mono readout for a period, e.g. "2026.06.26 · TUE" / "Jun 22 → wk" / "Jun · 2026". */
export function periodLabel(dateStr: string, range: Range): string {
  const d = parse(dateStr);
  const y = d.getUTCFullYear();
  const mo = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  if (range === "day") return `${y}.${mo}.${day} · ${WEEKDAYS[d.getUTCDay()]}`;
  if (range === "week") return `WK OF ${MONTHS[d.getUTCMonth()]} ${day}`;
  return `${MONTHS[d.getUTCMonth()]} · ${y}`;
}

/** Relative offset of a tick from the most recent tick (the right edge / "now"). */
export function relativeLabel(stepsFromNow: number, range: Range): string {
  if (stepsFromNow === 0) return "LIVE";
  const u = range === "day" ? "d" : range === "week" ? "w" : "mo";
  return `−${stepsFromNow}${u}`;
}
