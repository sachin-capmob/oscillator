// ============================================================================
// Football (FIFA-Ultimate-Team-style) layer. Every teammate becomes a player
// card rated out of 99, built from the SAME Linear-backed metrics the rest of
// the dashboard already computes (throughput, cycle time, comments, created,
// streak). Stateless — recomputed per load, nothing persisted.
//
// Concept (à la GitFut): six activity signals each map to a classic football
// stat, an overall rating is a weighted blend, and cards fall into bronze /
// silver / gold / icon tiers. Raw ratings cap at 88; the 90s ("icon") are
// gated behind sustained output + a live streak, so one big week can't mint an
// icon on its own.
// ============================================================================

import type { Player } from "./game";

export type FutTier = "bronze" | "silver" | "gold" | "icon";

export interface FutStats {
  pac: number; // Pace     ← delivery speed (inverse cycle time)
  sho: number; // Shooting ← issues closed (goals)
  pas: number; // Passing  ← comments (collaboration / assists)
  dri: number; // Dribbling← shipping streak (flow / consistency)
  def: number; // Defending← closed-vs-opened ratio (holds the line)
  phy: number; // Physical ← total activity volume (stamina)
}

export interface FutPlayer {
  base: Player;
  stats: FutStats;
  overall: number; // 1..99
  tier: FutTier;
  position: string; // ST / RW / CAM / CM / CDM / CB
  band: "FWD" | "MID" | "DEF"; // pitch grouping
  isCaptain: boolean;
}

const MIN_STAT = 48; // pros don't sit at 1 — floor the scale like FIFA does

function clampStat(n: number): number {
  return Math.max(1, Math.min(99, Math.round(n)));
}
function scale(norm: number): number {
  return clampStat(MIN_STAT + Math.max(0, Math.min(1, norm)) * (99 - MIN_STAT));
}

// ---- Stat labels (for legends / tooltips) ----------------------------------
export const STAT_META: { key: keyof FutStats; label: string; source: string }[] = [
  { key: "pac", label: "PAC", source: "Delivery speed — inverse of cycle time" },
  { key: "sho", label: "SHO", source: "Issues closed — goals scored" },
  { key: "pas", label: "PAS", source: "Comments — collaboration & assists" },
  { key: "dri", label: "DRI", source: "Shipping streak — flow & consistency" },
  { key: "def", label: "DEF", source: "Closed vs. opened — holding the line" },
  { key: "phy", label: "PHY", source: "Total activity volume — stamina" },
];

// ---- Position from the dominant stat ---------------------------------------
const POSITION_BY_STAT: Record<keyof FutStats, { code: string; band: FutPlayer["band"] }> = {
  sho: { code: "ST", band: "FWD" },
  pac: { code: "RW", band: "FWD" },
  dri: { code: "CAM", band: "MID" },
  pas: { code: "CM", band: "MID" },
  phy: { code: "CDM", band: "MID" },
  def: { code: "CB", band: "DEF" },
};

function dominantPosition(stats: FutStats): { code: string; band: FutPlayer["band"] } {
  // Priority order breaks ties toward the more attacking role.
  const order: (keyof FutStats)[] = ["sho", "pac", "dri", "pas", "phy", "def"];
  let best = order[0];
  for (const k of order) if (stats[k] > stats[best]) best = k;
  return POSITION_BY_STAT[best];
}

export function tierFor(overall: number): FutTier {
  if (overall >= 90) return "icon";
  if (overall >= 78) return "gold";
  if (overall >= 68) return "silver";
  return "bronze";
}

// ---- Squad build -----------------------------------------------------------
/**
 * Turn the XP-ranked roster into rated football cards. Stats are normalised
 * against the squad (so ratings spread across the team), then blended into an
 * overall with an icon gate for sustained top performers.
 */
export function buildSquad(players: Player[]): FutPlayer[] {
  if (players.length === 0) return [];

  const maxThroughput = Math.max(1, ...players.map((p) => p.throughput));
  const maxComments = Math.max(1, ...players.map((p) => p.comments));
  const maxStreak = Math.max(1, ...players.map((p) => p.streak.streak));
  const maxTotal = Math.max(
    1,
    ...players.map((p) => p.throughput + p.created + p.comments),
  );
  const cycles = players.map((p) => p.avgCycle).filter((c): c is number => c != null);
  const minCycle = cycles.length ? Math.min(...cycles) : 0;
  const maxCycle = cycles.length ? Math.max(...cycles) : 0;

  const squad: FutPlayer[] = players.map((base) => {
    const { throughput, created, comments, avgCycle, streak } = base;

    // PAC — faster cycle time → higher. Null cycle (no completed-with-start
    // data) sits at a neutral mid-table pace.
    let pacNorm: number;
    if (avgCycle == null) pacNorm = 0.45;
    else if (maxCycle === minCycle) pacNorm = 0.7;
    else pacNorm = (maxCycle - avgCycle) / (maxCycle - minCycle);

    const stats: FutStats = {
      pac: scale(pacNorm),
      sho: scale(throughput / maxThroughput),
      pas: scale(comments / maxComments),
      dri: scale(streak.streak / maxStreak),
      def: scale(throughput + created > 0 ? throughput / (throughput + created) : 0.5),
      phy: scale((throughput + created + comments) / maxTotal),
    };

    const rawOverall = Math.round(
      0.24 * stats.sho +
        0.2 * stats.pac +
        0.16 * stats.phy +
        0.16 * stats.pas +
        0.12 * stats.dri +
        0.12 * stats.def,
    );

    // Icon gate: elite, sustained output only. Otherwise the raw rating caps at 88.
    const iconEligible = throughput >= 10 && streak.streak >= 5;
    const overall = iconEligible
      ? Math.min(99, rawOverall + Math.min(11, throughput - 10 + (streak.streak - 5)))
      : Math.min(88, rawOverall);

    const pos = dominantPosition(stats);

    return {
      base,
      stats,
      overall,
      tier: tierFor(overall),
      position: pos.code,
      band: pos.band,
      isCaptain: false,
    } satisfies FutPlayer;
  });

  // Highest overall wears the armband.
  squad.sort((a, b) => b.overall - a.overall);
  if (squad.length) squad[0].isCaptain = true;
  return squad;
}

// ---- Formation grouping (for the pitch view) -------------------------------
export interface Formation {
  fwd: FutPlayer[];
  mid: FutPlayer[];
  def: FutPlayer[];
}

/** Split the top XI into attack / midfield / defence rows for the pitch. */
export function toFormation(squad: FutPlayer[], limit = 11): Formation {
  const xi = squad.slice(0, limit);
  return {
    fwd: xi.filter((p) => p.band === "FWD"),
    mid: xi.filter((p) => p.band === "MID"),
    def: xi.filter((p) => p.band === "DEF"),
  };
}

// ---- Tier palettes (used by the card component) ----------------------------
export interface TierSkin {
  gradient: string;
  ink: string; // primary text on the card
  sub: string; // secondary text
  rule: string; // divider / accents
  holo: boolean; // animate the holographic sheen
}

export const TIER_SKIN: Record<FutTier, TierSkin> = {
  bronze: {
    gradient: "linear-gradient(160deg, #5c3b22 0%, #8a5a34 45%, #b98a5a 100%)",
    ink: "#fbeede",
    sub: "rgba(251,238,222,0.72)",
    rule: "rgba(251,238,222,0.35)",
    holo: false,
  },
  silver: {
    gradient: "linear-gradient(160deg, #6f7681 0%, #aab2bd 45%, #e4e9f0 100%)",
    ink: "#1c2027",
    sub: "rgba(28,32,39,0.68)",
    rule: "rgba(28,32,39,0.28)",
    holo: false,
  },
  gold: {
    gradient: "linear-gradient(160deg, #9a7413 0%, #d9ab3c 42%, #f6df94 100%)",
    ink: "#2a2008",
    sub: "rgba(42,32,8,0.72)",
    rule: "rgba(42,32,8,0.3)",
    holo: true,
  },
  icon: {
    gradient: "linear-gradient(160deg, #141821 0%, #29303f 55%, #10131a 100%)",
    ink: "#f6df94",
    sub: "rgba(246,223,148,0.75)",
    rule: "rgba(246,223,148,0.4)",
    holo: true,
  },
};
