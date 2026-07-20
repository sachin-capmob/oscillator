// ============================================================================
// Gamification engine — stateless. Everything here is derived from the same
// Linear-backed insights the rest of the dashboard already fetches (by-actor,
// overview, wip, throughput). Nothing is persisted: XP, levels, streaks and
// badges are recomputed on every load from the live data.
//
// XP formula (per person):
//   (issues_closed × 130)
//   + (issues_closed_under_avg_cycle_time × 50)
//   + (streak_days × 20)
// Team XP = Σ per-person XP.
// ============================================================================

import type { ActorStat, Overview, TimePoint } from "./types";

// ---- Palette ---------------------------------------------------------------
// The gamification accent palette. XP bars cycle through the first four so
// adjacent players read as distinct; blue is reserved for "today"/informational.
export const XP_PURPLE = "#7F77DD";
export const XP_TEAL = "#1D9E75";
export const XP_AMBER = "#BA7517";
export const XP_CORAL = "#D85A30";
export const XP_BLUE = "#185FA5";

const XP_CYCLE = [XP_PURPLE, XP_TEAL, XP_AMBER, XP_CORAL];

/** Stable accent colour for a player, cycling through the four XP hues. */
export function xpColor(index: number): string {
  return XP_CYCLE[((index % XP_CYCLE.length) + XP_CYCLE.length) % XP_CYCLE.length];
}

// ---- XP constants ----------------------------------------------------------
export const XP_PER_CLOSE = 130;
export const XP_UNDER_AVG_BONUS = 50;
export const XP_PER_STREAK_DAY = 20;
export const XP_PER_LEVEL = 200;

// ---- Names / initials ------------------------------------------------------
function personName(a: { name: string | null; email: string | null; actor_id: number }): string {
  if (a.name) return a.name;
  if (a.email) return a.email.split("@")[0];
  return `Actor ${a.actor_id}`;
}

/** Up to two uppercase initials from a display name (or email handle). */
export function initials(a: { name: string | null; email: string | null; actor_id: number }): string {
  const source = a.name ?? a.email?.split("@")[0] ?? `A${a.actor_id}`;
  const parts = source.trim().split(/[\s._-]+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

// ---- Date helpers (UTC, to match the backend & lib/dates) ------------------
const WEEKDAYS_MON = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function parseUTC(d: string): Date {
  return new Date(`${d}T00:00:00Z`);
}
function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10);
}
function addDays(d: Date, n: number): Date {
  const r = new Date(d);
  r.setUTCDate(r.getUTCDate() + n);
  return r;
}
function daysBetween(a: Date, b: Date): number {
  return Math.round((b.getTime() - a.getTime()) / 86_400_000);
}

// ---- Streaks ---------------------------------------------------------------
export type DayState = "shipped" | "today" | "empty" | "future";

export interface DayCell {
  label: string; // Mon..Sun
  date: string; // YYYY-MM-DD
  value: number; // issues shipped that day (0 if none / unknown)
  state: DayState;
}

export interface StreakInfo {
  /** Current live streak: trailing consecutive shipping days (today counts as
   *  in-progress, so an as-yet-empty today does not break the streak). */
  streak: number;
  /** Mon→Sun cells for the week that contains the anchor. */
  week: DayCell[];
  /** Day name a mid-week streak broke on (a zero day between shipping days), else null. */
  brokenDay: string | null;
}

/**
 * Derive streak + weekly shipping dots from the 14-value daily sparkline that
 * `by-actor` returns. The sparkline ends on `anchor` (sparkline[len-1] === the
 * anchor day), so we can date every entry and slice out the anchor's week.
 */
export function computeStreak(sparkline: number[], anchor: string): StreakInfo {
  const spark = sparkline ?? [];
  const anchorDate = parseUTC(anchor);
  const sparkStart = addDays(anchorDate, -(spark.length - 1)); // date of spark[0]

  const valueOn = (d: Date): number | null => {
    const idx = daysBetween(sparkStart, d);
    if (idx < 0 || idx >= spark.length) return null;
    return spark[idx] ?? 0;
  };

  // --- current streak: walk back from the anchor day ---
  let streak = 0;
  let i = spark.length - 1;
  // Grace for "today": if the most recent day has nothing yet, don't let that
  // break an otherwise-live streak — start counting from the day before.
  if (i >= 0 && (spark[i] ?? 0) === 0) i -= 1;
  while (i >= 0 && (spark[i] ?? 0) > 0) {
    streak += 1;
    i -= 1;
  }

  // --- week (Mon→Sun) containing the anchor ---
  const dow = anchorDate.getUTCDay(); // 0=Sun..6=Sat
  const monday = addDays(anchorDate, dow === 0 ? -6 : -(dow - 1));

  const week: DayCell[] = WEEKDAYS_MON.map((label, k) => {
    const d = addDays(monday, k);
    const v = valueOn(d) ?? 0;
    const cmp = daysBetween(anchorDate, d); // 0 = anchor day (today)
    let state: DayState;
    if (cmp > 0) state = "future";
    else if (cmp === 0) state = "today";
    else state = v > 0 ? "shipped" : "empty";
    return { label, date: toISODate(d), value: v, state };
  });

  // --- broken mid-week? first empty *past* day that sits after a shipping day ---
  let brokenDay: string | null = null;
  let seenShipped = false;
  for (const cell of week) {
    if (cell.state === "shipped") seenShipped = true;
    else if (cell.state === "empty" && seenShipped) {
      brokenDay = cell.label;
      break;
    }
  }

  return { streak, week, brokenDay };
}

// ---- Under-average cycle-time bonus ----------------------------------------
/**
 * Estimated count of a person's closed issues that beat the global average
 * cycle time. Aggregate views only expose each person's *average* cycle time,
 * not per-issue timings, so this is a bounded, monotonic estimate: a person
 * whose average equals the global average is credited with ~half their closes;
 * faster-than-average trends toward all, slower toward none. On the People
 * page, exact per-issue data can refine this, but the estimate keeps Team XP
 * derivable from a single by-actor call.
 */
export function estimateUnderAvg(
  throughput: number,
  avgCycle: number | null,
  globalAvg: number | null,
): number {
  if (throughput <= 0 || avgCycle == null || globalAvg == null || globalAvg <= 0) return 0;
  const fraction = Math.min(1, Math.max(0, 0.5 + 0.5 * ((globalAvg - avgCycle) / globalAvg)));
  return Math.round(throughput * fraction);
}

// ---- Core XP + levels ------------------------------------------------------
export function computeXp(throughput: number, underAvgCount: number, streakDays: number): number {
  return (
    throughput * XP_PER_CLOSE +
    underAvgCount * XP_UNDER_AVG_BONUS +
    streakDays * XP_PER_STREAK_DAY
  );
}

export interface LevelInfo {
  level: number;
  title: string;
  progressPct: number; // 0..100 toward next level
  xpIntoLevel: number;
  xpToNext: number;
}

/** Title bracket for a level. */
export function levelTitle(level: number): string {
  if (level >= 13) return "Legend";
  if (level >= 10) return "Sprint Ace";
  if (level >= 7) return "Bug Slayer";
  if (level >= 4) return "Contributor";
  return "Rookie";
}

/** level = ⌊XP / 200⌋ + 1 (everyone starts at level 1; every 200 XP = +1). */
export function levelInfo(xp: number): LevelInfo {
  const level = Math.floor(xp / XP_PER_LEVEL) + 1;
  const xpIntoLevel = xp % XP_PER_LEVEL;
  const xpToNext = XP_PER_LEVEL - xpIntoLevel;
  return {
    level,
    title: levelTitle(level),
    progressPct: (xpIntoLevel / XP_PER_LEVEL) * 100,
    xpIntoLevel,
    xpToNext,
  };
}

// ---- Badges ----------------------------------------------------------------
export interface BadgeDef {
  id: string;
  icon: string;
  name: string;
  /** How to unlock — shown in the tooltip on locked badges. */
  howTo: string;
}

export interface BadgeState extends BadgeDef {
  earned: boolean;
}

export interface BadgeContext {
  throughput: number; // issues closed this period
  created: number; // issues opened this period
  streak: number; // current streak (days)
  totalClosed: number; // closed in the selected range (all-time on the "All" range)
}

// Criteria are wired to the signals the insights feed actually exposes. Where
// Linear label/reopen data isn't in the pipeline, the closest honest proxy is
// used and spelled out in `howTo` so the tooltip stays truthful.
export const BADGES: { def: BadgeDef; earned: (c: BadgeContext) => boolean }[] = [
  {
    def: {
      id: "shipped",
      icon: "🚀",
      name: "Shipped",
      howTo: "Close 10+ issues in a single sprint.",
    },
    earned: (c) => c.throughput >= 10,
  },
  {
    def: {
      id: "onfire",
      icon: "🔥",
      name: "On fire",
      howTo: "Ship on 5 days in a row.",
    },
    earned: (c) => c.streak >= 5,
  },
  {
    def: {
      id: "noregress",
      icon: "🛡️",
      name: "No regressions",
      howTo: "Close at least as many issues as you open in a cycle (no backlog regression).",
    },
    earned: (c) => c.throughput > 0 && c.throughput >= c.created,
  },
  {
    def: {
      id: "bugslayer",
      icon: "🐛",
      name: "Bug Slayer",
      howTo: "Close 5+ issues in a single cycle.",
    },
    earned: (c) => c.throughput >= 5,
  },
  {
    def: {
      id: "diamond",
      icon: "💎",
      name: "Diamond",
      howTo: "Hold a 30-day shipping streak. Rare.",
    },
    earned: (c) => c.streak >= 30,
  },
  {
    def: {
      id: "speeddemon",
      icon: "⚡",
      name: "Speed demon",
      howTo: "Close 50+ issues total (switch the range to All to count all-time).",
    },
    earned: (c) => c.totalClosed >= 50,
  },
];

export function evaluateBadges(ctx: BadgeContext): BadgeState[] {
  return BADGES.map(({ def, earned }) => ({ ...def, earned: earned(ctx) }));
}

// ---- Player (per-person aggregate) -----------------------------------------
export interface Player {
  actorId: number;
  name: string;
  initials: string;
  throughput: number;
  created: number;
  comments: number;
  avgCycle: number | null;
  underAvgCount: number;
  streak: StreakInfo;
  xp: number;
  level: LevelInfo;
  badges: BadgeState[];
}

/** Build the full gamified profile for one actor from aggregate insights data. */
export function buildPlayer(actor: ActorStat, globalAvg: number | null, anchor: string): Player {
  const created = actor.created ?? 0;
  const streak = computeStreak(actor.sparkline ?? [], anchor);
  const underAvgCount = estimateUnderAvg(actor.throughput, actor.avg_cycle_hours, globalAvg);
  const xp = computeXp(actor.throughput, underAvgCount, streak.streak);
  const badges = evaluateBadges({
    throughput: actor.throughput,
    created,
    streak: streak.streak,
    totalClosed: actor.throughput,
  });
  return {
    actorId: actor.actor_id,
    name: personName(actor),
    initials: initials(actor),
    throughput: actor.throughput,
    created,
    comments: actor.comments,
    avgCycle: actor.avg_cycle_hours,
    underAvgCount,
    streak,
    xp,
    level: levelInfo(xp),
    badges,
  };
}

/** Build + XP-rank every active actor. */
export function buildRoster(actors: ActorStat[], globalAvg: number | null, anchor: string): Player[] {
  return actors
    .map((a) => buildPlayer(a, globalAvg, anchor))
    .sort((a, b) => b.xp - a.xp || b.throughput - a.throughput);
}

export function teamXp(players: Player[]): number {
  return players.reduce((sum, p) => sum + p.xp, 0);
}

// ---- Sprint quest ----------------------------------------------------------
export interface SprintQuest {
  closed: number;
  target: number; // committed scope = closed + in-flight
  inFlight: number;
  progressPct: number;
  throughputDeltaPct: number | null;
  daysRemaining: number | null; // null on the all-time range
  atRisk: number; // in-flight issues above the historical WIP average
  hitBonus: boolean; // 100% of committed scope closed
  startISO: string;
  endISO: string;
}

/** Derive the sprint-quest state for the anchor's period from the overview. */
export function deriveSprintQuest(
  overview: Overview,
  wipSeries: TimePoint[] | undefined,
  isAllTime: boolean,
): SprintQuest {
  const closed = overview.throughput.current ?? 0;
  const inFlight = overview.wip ?? 0;
  const target = Math.max(closed + inFlight, closed, 1);
  const progressPct = Math.min(100, (closed / target) * 100);

  // Historical WIP average across the visible series → anything above it is "at risk".
  const wipValues = (wipSeries ?? []).map((p) => p.value ?? 0);
  const avgWip = wipValues.length ? wipValues.reduce((a, b) => a + b, 0) / wipValues.length : 0;
  const atRisk = Math.max(0, inFlight - Math.round(avgWip));

  let daysRemaining: number | null = null;
  if (!isAllTime && overview.period_end) {
    const end = new Date(overview.period_end).getTime();
    daysRemaining = Math.max(0, Math.ceil((end - Date.now()) / 86_400_000));
  }

  return {
    closed,
    target,
    inFlight,
    progressPct,
    throughputDeltaPct: overview.throughput.delta_pct,
    daysRemaining,
    atRisk,
    hitBonus: closed > 0 && inFlight === 0,
    startISO: overview.period_start,
    endISO: overview.period_end,
  };
}
