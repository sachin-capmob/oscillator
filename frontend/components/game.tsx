"use client";

// ============================================================================
// Gamification UI primitives. Built entirely from the existing stack (raw divs
// + Tailwind tokens + the gamification palette from lib/game). No external
// gamification libraries. Every colour comes from a CSS variable so the surface
// re-themes with the rest of the app.
// ============================================================================

import { CountUp, Eyebrow } from "@/components/ui";
import { formatDate } from "@/components/ui";
import {
  XP_BLUE,
  XP_TEAL,
  xpColor,
  type BadgeState,
  type Player,
  type SprintQuest,
  type StreakInfo,
} from "@/lib/game";

const NEG = "var(--negative)";

export function fmtXp(n: number): string {
  return Math.round(n).toLocaleString();
}

/* -------------------------------------------------------------------------- */
/* XpBar — coloured progress track that fills from 0 on mount.                */
/* -------------------------------------------------------------------------- */
export function XpBar({
  pct,
  color,
  height = 8,
  sheen = false,
  className = "",
}: {
  pct: number;
  color: string;
  height?: number;
  sheen?: boolean;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(100, pct));
  return (
    <div
      className={`relative w-full overflow-hidden border border-edge bg-void ${className}`}
      style={{ height }}
      role="progressbar"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={`xp-bar-fill relative h-full ${sheen ? "xp-bar-sheen" : ""}`}
        style={{ width: `${clamped}%`, background: color }}
      />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Avatar — initials chip tinted with the player's accent colour.             */
/* -------------------------------------------------------------------------- */
export function Avatar({
  text,
  color,
  size = 40,
}: {
  text: string;
  color: string;
  size?: number;
}) {
  return (
    <span
      aria-hidden
      className="flex shrink-0 items-center justify-center font-mono font-medium"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.34,
        color,
        background: `color-mix(in srgb, ${color} 18%, transparent)`,
        border: `1px solid color-mix(in srgb, ${color} 55%, transparent)`,
      }}
    >
      {text}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Medal — 🥇🥈🥉 for the top three, a mono rank number otherwise.             */
/* -------------------------------------------------------------------------- */
export function Medal({ rank }: { rank: number }) {
  const medal = ["🥇", "🥈", "🥉"][rank - 1];
  if (medal) {
    return (
      <span className="flex w-7 shrink-0 justify-center text-[18px] leading-none" aria-label={`Rank ${rank}`}>
        {medal}
      </span>
    );
  }
  return (
    <span className="flex w-7 shrink-0 justify-center font-mono text-body text-muted" aria-label={`Rank ${rank}`}>
      {rank}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Flame — streak indicator, only rendered at ≥3 days.                        */
/* -------------------------------------------------------------------------- */
export function StreakFlame({ streak, className = "" }: { streak: number; className?: string }) {
  if (streak < 3) return null;
  return (
    <span
      className={`inline-flex items-center gap-1 font-mono text-[12px] ${className}`}
      style={{ color: XP_TEAL }}
      title={`${streak}-day shipping streak`}
    >
      🔥 {streak}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Leaderboard — ranks players by XP, colour-coded bars, medals + streaks.    */
/* -------------------------------------------------------------------------- */
export function Leaderboard({ players }: { players: Player[] }) {
  const maxXp = Math.max(1, ...players.map((p) => p.xp));
  return (
    <div className="flex flex-col">
      {players.map((p, i) => {
        const color = xpColor(i);
        const barPct = (p.xp / maxXp) * 100;
        return (
          <div
            key={p.actorId}
            className="flex items-center gap-4 border-b border-edge px-6 py-3.5 last:border-b-0"
          >
            <Medal rank={i + 1} />
            <Avatar text={p.initials} color={color} size={32} />
            <div className="flex min-w-0 flex-1 flex-col gap-1.5">
              <div className="flex items-center justify-between gap-3">
                <span className="truncate text-body text-ink">{p.name}</span>
                <span className="flex shrink-0 items-center gap-2.5">
                  <StreakFlame streak={p.streak.streak} />
                  <span className="font-mono text-body" style={{ color }}>
                    {fmtXp(p.xp)}
                    <span className="ml-1 text-[11px] text-muted">XP</span>
                  </span>
                </span>
              </div>
              <XpBar pct={barPct} color={color} height={6} sheen={i === 0} />
            </div>
            <span className="hidden shrink-0 flex-col items-end gap-0.5 sm:flex" style={{ minWidth: 56 }}>
              <span className="font-mono text-body text-ink">{p.throughput}</span>
              <Eyebrow>closed</Eyebrow>
            </span>
          </div>
        );
      })}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* BadgeChip — earned (full) or locked (35% opacity + how-to tooltip).        */
/* -------------------------------------------------------------------------- */
export function BadgeChip({ badge, index = 0 }: { badge: BadgeState; index?: number }) {
  const earned = badge.earned;
  return (
    <div
      title={earned ? `${badge.name} — earned` : `${badge.name} — locked. ${badge.howTo}`}
      className={`flex items-center gap-2 border border-edge bg-void px-2.5 py-1.5 ${earned ? "badge-pop" : ""}`}
      style={{
        opacity: earned ? 1 : 0.35,
        animationDelay: earned ? `${index * 60}ms` : undefined,
      }}
    >
      <span className="text-[15px] leading-none" aria-hidden>
        {badge.icon}
      </span>
      <span className="text-[12px] text-ink">{badge.name}</span>
      {!earned && (
        <span className="ml-0.5 text-[10px] text-muted" aria-hidden>
          🔒
        </span>
      )}
    </div>
  );
}

export function BadgeGrid({ badges }: { badges: BadgeState[] }) {
  const ordered = [...badges].sort((a, b) => Number(b.earned) - Number(a.earned));
  return (
    <div className="flex flex-wrap gap-2">
      {ordered.map((b, i) => (
        <BadgeChip key={b.id} badge={b} index={i} />
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* PlayerCard — avatar, level + title, XP-to-next bar, achievement badges.    */
/* -------------------------------------------------------------------------- */
export function PlayerCard({ player, index }: { player: Player; index: number }) {
  const color = xpColor(index);
  const { level } = player;
  const earnedCount = player.badges.filter((b) => b.earned).length;

  return (
    <div className="flex flex-col gap-5 border border-edge bg-surface px-6 py-6">
      {/* Header — avatar + name + level pill */}
      <div className="flex items-center gap-3.5">
        <Avatar text={player.initials} color={color} size={48} />
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="truncate text-title font-medium text-ink">{player.name}</span>
          <span className="flex items-center gap-2 text-[12px] text-muted">
            <span
              className="font-mono font-medium"
              style={{ color }}
            >
              LVL {level.level}
            </span>
            <span aria-hidden>·</span>
            <span>{level.title}</span>
            <StreakFlame streak={player.streak.streak} className="ml-1" />
          </span>
        </div>
      </div>

      {/* XP progress to next level */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between text-[11px]">
          <span className="font-mono" style={{ color }}>
            {fmtXp(player.xp)} XP
          </span>
          <span className="text-muted">{fmtXp(level.xpToNext)} to LVL {level.level + 1}</span>
        </div>
        <XpBar pct={level.progressPct} color={color} height={8} sheen />
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-3 gap-2 border-y border-edge py-3">
        <MiniStat label="Closed" value={player.throughput} />
        <MiniStat
          label="Avg cycle"
          value={player.avgCycle != null ? `${player.avgCycle}h` : "--"}
        />
        <MiniStat label="Comments" value={player.comments} />
      </div>

      {/* Badges */}
      <div className="flex flex-col gap-2.5">
        <div className="flex items-center justify-between">
          <Eyebrow>Achievements</Eyebrow>
          <span className="font-mono text-[11px] text-muted">
            {earnedCount}/{player.badges.length}
          </span>
        </div>
        <BadgeGrid badges={player.badges} />
      </div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <span className="font-mono text-title text-ink">{value}</span>
      <Eyebrow>{label}</Eyebrow>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* StreakDots — one player's Mon→Sun shipping dots + count + broken note.     */
/* -------------------------------------------------------------------------- */
function dotStyle(state: string): React.CSSProperties {
  switch (state) {
    case "shipped":
      return { background: XP_TEAL, borderColor: XP_TEAL };
    case "today":
      return { background: XP_BLUE, borderColor: XP_BLUE };
    case "future":
      return { background: "transparent", borderColor: "var(--edge)", opacity: 0.45 };
    default: // empty
      return { background: "transparent", borderColor: "var(--edge)" };
  }
}

export function StreakDots({ streak }: { streak: StreakInfo }) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-2.5">
        {streak.week.map((d) => (
          <div key={d.date} className="flex flex-col items-center gap-1.5" title={`${d.label}: ${d.value} shipped`}>
            <span className="h-3 w-3 rounded-full border" style={dotStyle(d.state)} aria-hidden />
            <span className="text-[9px] uppercase tracking-eyebrow text-muted">{d.label[0]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** A full streak row (name + dots + count) for the Overview streak board. */
export function StreakRow({ player, index }: { player: Player; index: number }) {
  const color = xpColor(index);
  const s = player.streak;
  return (
    <div className="flex items-center gap-4 border-b border-edge px-6 py-4 last:border-b-0">
      <Avatar text={player.initials} color={color} size={30} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="truncate text-body text-ink">{player.name}</span>
        {s.brokenDay ? (
          <span className="text-[11px]" style={{ color: NEG }}>
            streak broken on {s.brokenDay}
          </span>
        ) : s.streak > 0 ? (
          <span className="text-[11px] text-muted">
            {s.streak}-day streak{s.streak >= 3 ? " 🔥" : ""}
          </span>
        ) : (
          <span className="text-[11px] text-muted">no streak yet</span>
        )}
      </div>
      <StreakDots streak={s} />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* SprintQuestCard — the headline "quest" above the charts.                   */
/* -------------------------------------------------------------------------- */
export function SprintQuestCard({
  quest,
  periodWord,
  isAllTime,
}: {
  quest: SprintQuest;
  periodWord: string;
  isAllTime: boolean;
}) {
  const range = `${formatDate(quest.startISO)} → ${
    isAllTime ? "now" : formatDate(quest.endISO)
  }`;
  const delta = quest.throughputDeltaPct;

  return (
    <div className="relative overflow-hidden border border-edge bg-surface px-6 py-6 sm:px-8">
      {/* faint accent glow */}
      <span
        aria-hidden
        className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full"
        style={{ background: "radial-gradient(circle, rgba(var(--xp-purple-rgb),0.18), transparent 70%)" }}
      />

      <div className="relative flex flex-col gap-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-2.5">
              <span className="text-[16px]" aria-hidden>
                🎯
              </span>
              <h3 className="text-title font-medium text-ink">
                Sprint quest · {range}
              </h3>
            </div>
            <p className="text-body text-muted">
              Close <span className="font-mono text-ink">{quest.target}</span> issues
              {!isAllTime && quest.endISO ? (
                <> before <span className="text-ink">{formatDate(quest.endISO)}</span></>
              ) : null}
            </p>
          </div>

          {/* Countdown */}
          {!isAllTime && quest.daysRemaining != null && (
            <div className="flex flex-col items-end">
              <span className="font-mono text-callout font-light text-ink">
                {quest.daysRemaining}
              </span>
              <Eyebrow>{quest.daysRemaining === 1 ? "day left" : "days left"}</Eyebrow>
            </div>
          )}
        </div>

        {/* Big progress bar */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between text-[12px]">
            <span className="font-mono text-ink">
              {quest.closed} / {quest.target} closed
            </span>
            <span className="font-mono" style={{ color: "var(--xp-teal)" }}>
              {Math.round(quest.progressPct)}%
            </span>
          </div>
          <XpBar
            pct={quest.progressPct}
            color="linear-gradient(90deg, var(--xp-purple), var(--xp-teal))"
            height={14}
            sheen
          />
        </div>

        {/* Tags */}
        <div className="flex flex-wrap items-center gap-2.5">
          {delta != null && (
            <QuestTag
              tone={delta >= 0 ? "good" : "bad"}
              label={`${delta >= 0 ? "↑ +" : "↓ "}${delta}% vs last ${periodWord}`}
            />
          )}
          {quest.hitBonus && <QuestTag tone="bonus" label="+500 XP · 100% cleared" />}
          {quest.atRisk > 0 && (
            <QuestTag tone="warn" label={`${quest.atRisk} at risk · WIP over avg`} />
          )}
          {quest.inFlight > 0 && (
            <QuestTag tone="neutral" label={`${quest.inFlight} in flight`} />
          )}
        </div>
      </div>
    </div>
  );
}

function QuestTag({
  label,
  tone,
}: {
  label: string;
  tone: "good" | "bad" | "warn" | "bonus" | "neutral";
}) {
  const map: Record<string, { color: string; rgb: string }> = {
    good: { color: "var(--xp-teal)", rgb: "var(--xp-teal-rgb)" },
    bad: { color: NEG, rgb: "255,107,107" },
    warn: { color: "var(--xp-amber)", rgb: "var(--xp-amber-rgb)" },
    bonus: { color: "var(--xp-purple)", rgb: "var(--xp-purple-rgb)" },
    neutral: { color: "var(--muted)", rgb: "74,85,104" },
  };
  const { color, rgb } = map[tone];
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 font-mono text-[11px]"
      style={{
        color,
        background: `rgba(${rgb}, 0.12)`,
        border: `1px solid rgba(${rgb}, 0.35)`,
      }}
    >
      {label}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* StatTile — gamified KPI tile with a directional, colour-coded delta.       */
/* -------------------------------------------------------------------------- */
export function StatTile({
  label,
  value,
  unit,
  decimals = 0,
  deltaPct,
  periodWord,
  invertDelta = false,
  accent = "var(--xp-teal)",
  warn,
  footnote,
  placeholder = false,
}: {
  label: string;
  value: number;
  unit?: string;
  decimals?: number;
  deltaPct?: number | null;
  periodWord?: string;
  invertDelta?: boolean;
  accent?: string;
  warn?: string | null;
  footnote?: string;
  placeholder?: boolean;
}) {
  const hasDelta = deltaPct !== undefined && deltaPct !== null;
  const good = hasDelta ? (invertDelta ? deltaPct! <= 0 : deltaPct! >= 0) : true;
  const arrow = hasDelta ? (deltaPct! >= 0 ? "↑" : "↓") : "";
  const sign = hasDelta && deltaPct! > 0 ? "+" : "";
  const deltaColor = good ? "var(--xp-teal)" : NEG;

  return (
    <div className="relative flex flex-col gap-4 overflow-hidden border border-edge bg-surface px-6 py-6">
      {/* left accent rule */}
      <span aria-hidden className="absolute inset-y-0 left-0 w-0.5" style={{ background: accent }} />
      <div className="flex items-center gap-2.5">
        <Eyebrow>{label}</Eyebrow>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-kpi font-light text-ink">
          {placeholder ? "--" : <CountUp value={value} decimals={decimals} />}
        </span>
        {unit && !placeholder && <span className="font-mono text-body text-muted">{unit}</span>}
      </div>
      <div className="min-h-[16px]">
        {!placeholder && warn ? (
          <span className="font-mono text-[12px]" style={{ color: "var(--xp-amber)" }}>
            ⚠ {warn}
          </span>
        ) : !placeholder && hasDelta ? (
          <span className="font-mono text-body" style={{ color: deltaColor }}>
            {arrow} {sign}
            {deltaPct}%
            {periodWord && <span className="ml-1.5 text-muted">vs last {periodWord}</span>}
          </span>
        ) : !placeholder && footnote ? (
          <span className="font-mono text-body" style={{ color: accent }}>
            {footnote}
          </span>
        ) : null}
      </div>
    </div>
  );
}
