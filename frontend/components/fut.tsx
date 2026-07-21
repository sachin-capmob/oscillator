"use client";

// ============================================================================
// Football player-card UI (FIFA-Ultimate-Team style). Pure existing stack:
// divs + Tailwind tokens + inline tier gradients + a little pointer math for
// the 3D tilt. No external libraries. Colours come from lib/fut tier skins.
// ============================================================================

import { useRef, useState } from "react";

import { CountUp } from "@/components/ui";
import {
  STAT_META,
  TIER_SKIN,
  toFormation,
  type FutPlayer,
  type FutStats,
} from "@/lib/fut";
import { initials as initialsOf } from "@/lib/game";

const MAX_TILT = 9; // degrees

/* -------------------------------------------------------------------------- */
/* TiltCard — tilts toward the pointer with a soft glare that tracks it.      */
/* -------------------------------------------------------------------------- */
function TiltCard({
  children,
  className = "",
  glow = false,
}: {
  children: React.ReactNode;
  className?: string;
  glow?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [t, setT] = useState({ rx: 0, ry: 0, gx: 50, gy: 0, active: false });

  function onMove(e: React.MouseEvent) {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width; // 0..1
    const py = (e.clientY - r.top) / r.height; // 0..1
    setT({
      rx: (0.5 - py) * 2 * MAX_TILT,
      ry: (px - 0.5) * 2 * MAX_TILT,
      gx: px * 100,
      gy: py * 100,
      active: true,
    });
  }
  function onLeave() {
    setT({ rx: 0, ry: 0, gx: 50, gy: 0, active: false });
  }

  return (
    <div style={{ perspective: 900 }} className={className}>
      <div
        ref={ref}
        onMouseMove={onMove}
        onMouseLeave={onLeave}
        className={`fut-card relative ${glow ? "fut-glow" : ""}`}
        style={{
          transform: `rotateX(${t.rx}deg) rotateY(${t.ry}deg) scale(${t.active ? 1.03 : 1})`,
          boxShadow: glow ? undefined : t.active ? "0 18px 50px rgba(0,0,0,0.45)" : "0 6px 20px rgba(0,0,0,0.3)",
        }}
      >
        {children}
        {/* Pointer glare */}
        <span
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background: `radial-gradient(circle at ${t.gx}% ${t.gy}%, rgba(255,255,255,0.28), transparent 45%)`,
            opacity: t.active ? 1 : 0,
            transition: "opacity 0.2s ease",
            mixBlendMode: "soft-light",
          }}
        />
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* FutCard — the player card itself.                                          */
/* -------------------------------------------------------------------------- */
export function FutCard({
  player,
  index = 0,
  big = false,
}: {
  player: FutPlayer;
  index?: number;
  big?: boolean;
}) {
  const skin = TIER_SKIN[player.tier];
  const { base } = player;
  const inits = initialsOf({ name: base.name, email: null, actor_id: base.actorId });

  return (
    <TiltCard glow={player.tier === "icon"} className="fut-in" >
      <div
        className="relative overflow-hidden"
        style={{
          background: skin.gradient,
          color: skin.ink,
          border: `1px solid ${skin.rule}`,
          padding: big ? "26px 24px" : "20px 18px",
          minHeight: big ? 400 : 320,
        }}
      >
        {/* Holographic sheen (gold/icon) */}
        {skin.holo && <span aria-hidden className="fut-shine absolute inset-0 overflow-hidden" />}
        {/* Subtle pitch/hex texture */}
        <span
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              "repeating-linear-gradient(0deg, rgba(255,255,255,0.05) 0 1px, transparent 1px 26px)",
            opacity: 0.5,
          }}
        />

        <div className="relative flex flex-col" style={{ gap: big ? 18 : 14 }}>
          {/* Top: rating block + avatar */}
          <div className="flex items-start justify-between">
            <div className="flex flex-col items-center" style={{ minWidth: 56 }}>
              <span
                className="font-mono font-semibold leading-none"
                style={{ fontSize: big ? 52 : 42 }}
              >
                <CountUp value={player.overall} />
              </span>
              <span className="mt-1 font-mono font-medium tracking-widest" style={{ fontSize: big ? 16 : 14 }}>
                {player.position}
              </span>
              <span className="my-2 h-px w-8" style={{ background: skin.rule }} aria-hidden />
              <span className="text-[15px] leading-none" aria-hidden>⚽</span>
              <span
                className="mt-1.5 font-mono tracking-widest"
                style={{ fontSize: 10, color: skin.sub }}
              >
                OSC
              </span>
              {player.isCaptain && (
                <span
                  className="mt-2 flex h-5 w-5 items-center justify-center rounded-full font-mono text-[11px] font-bold"
                  style={{ border: `1.5px solid ${skin.ink}`, color: skin.ink }}
                  title="Squad captain — highest overall"
                >
                  C
                </span>
              )}
            </div>

            {/* Avatar */}
            <div
              className="flex items-center justify-center rounded-full font-mono font-semibold"
              style={{
                width: big ? 108 : 84,
                height: big ? 108 : 84,
                fontSize: big ? 38 : 30,
                color: skin.ink,
                background: "rgba(0,0,0,0.16)",
                border: `1.5px solid ${skin.rule}`,
              }}
              aria-hidden
            >
              {inits}
            </div>
          </div>

          {/* Name banner */}
          <div className="flex items-center gap-3">
            <span className="h-px flex-1" style={{ background: skin.rule }} aria-hidden />
            <span
              className="truncate text-center font-semibold uppercase tracking-wide"
              style={{ fontSize: big ? 18 : 15, letterSpacing: "0.04em" }}
            >
              {base.name}
            </span>
            <span className="h-px flex-1" style={{ background: skin.rule }} aria-hidden />
          </div>

          {/* Stats — two FIFA-style columns */}
          <div className="grid grid-cols-2 gap-x-7 gap-y-2" style={{ paddingInline: big ? 8 : 2 }}>
            <StatCol keys={["pac", "sho", "pas"]} stats={player.stats} skin={skin} big={big} />
            <StatCol keys={["dri", "def", "phy"]} stats={player.stats} skin={skin} big={big} />
          </div>
        </div>
      </div>
    </TiltCard>
  );
}

const STAT_LABEL: Record<keyof FutStats, string> = {
  pac: "PAC",
  sho: "SHO",
  pas: "PAS",
  dri: "DRI",
  def: "DEF",
  phy: "PHY",
};
const STAT_TIP = Object.fromEntries(STAT_META.map((m) => [m.key, m.source])) as Record<
  keyof FutStats,
  string
>;

function StatCol({
  keys,
  stats,
  skin,
  big,
}: {
  keys: (keyof FutStats)[];
  stats: FutStats;
  skin: (typeof TIER_SKIN)[keyof typeof TIER_SKIN];
  big: boolean;
}) {
  return (
    <div className="flex flex-col gap-2">
      {keys.map((k) => (
        <div
          key={k}
          className="flex items-baseline gap-2"
          title={`${STAT_LABEL[k]} — ${STAT_TIP[k]}`}
        >
          <span className="font-mono font-semibold" style={{ fontSize: big ? 19 : 16 }}>
            {stats[k]}
          </span>
          <span
            className="font-mono font-medium tracking-wider"
            style={{ fontSize: big ? 12 : 11, color: skin.sub }}
          >
            {STAT_LABEL[k]}
          </span>
        </div>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* SquadPitch — the top XI laid out on a football pitch by role band.         */
/* -------------------------------------------------------------------------- */
export function SquadPitch({ squad }: { squad: FutPlayer[] }) {
  const { fwd, mid, def } = toFormation(squad, 11);
  return (
    <div
      className="relative overflow-hidden border border-edge px-4 py-8 sm:px-8"
      style={{
        background:
          "linear-gradient(160deg, #0c2a1a 0%, #103a24 50%, #0c2a1a 100%)",
      }}
    >
      {/* pitch markings */}
      <span aria-hidden className="pointer-events-none absolute inset-0" style={{ opacity: 0.5 }}>
        <span
          className="absolute inset-x-0 top-1/2 h-px"
          style={{ background: "rgba(255,255,255,0.18)" }}
        />
        <span
          className="absolute left-1/2 top-1/2 h-28 w-28 -translate-x-1/2 -translate-y-1/2 rounded-full border"
          style={{ borderColor: "rgba(255,255,255,0.18)" }}
        />
        <span
          className="absolute inset-0"
          style={{
            backgroundImage:
              "repeating-linear-gradient(90deg, rgba(255,255,255,0.04) 0 60px, transparent 60px 120px)",
          }}
        />
      </span>

      <div className="relative flex flex-col gap-8">
        <PitchRow label="Attack" players={fwd} />
        <PitchRow label="Midfield" players={mid} />
        <PitchRow label="Defence" players={def} />
      </div>
    </div>
  );
}

function PitchRow({ label, players }: { label: string; players: FutPlayer[] }) {
  if (players.length === 0) return null;
  return (
    <div className="flex flex-col items-center gap-2">
      <span className="text-[10px] font-medium uppercase tracking-[0.2em]" style={{ color: "rgba(255,255,255,0.55)" }}>
        {label}
      </span>
      <div className="flex flex-wrap items-center justify-center gap-3">
        {players.map((p) => (
          <PitchChip key={p.base.actorId} player={p} />
        ))}
      </div>
    </div>
  );
}

function PitchChip({ player }: { player: FutPlayer }) {
  const skin = TIER_SKIN[player.tier];
  const inits = initialsOf({ name: player.base.name, email: null, actor_id: player.base.actorId });
  return (
    <div
      className="flex w-[104px] flex-col items-center gap-1 px-2 py-2.5"
      style={{ background: skin.gradient, color: skin.ink, border: `1px solid ${skin.rule}` }}
      title={`${player.base.name} · ${player.overall} ${player.position}`}
    >
      <div className="flex w-full items-center justify-between">
        <span className="font-mono text-[15px] font-bold leading-none">{player.overall}</span>
        <span className="font-mono text-[10px] tracking-widest" style={{ color: skin.sub }}>
          {player.position}
        </span>
      </div>
      <div
        className="my-0.5 flex h-9 w-9 items-center justify-center rounded-full font-mono text-[13px] font-semibold"
        style={{ background: "rgba(0,0,0,0.16)", border: `1px solid ${skin.rule}` }}
        aria-hidden
      >
        {inits}
      </div>
      <span className="w-full truncate text-center text-[11px] font-medium">{player.base.name}</span>
    </div>
  );
}
