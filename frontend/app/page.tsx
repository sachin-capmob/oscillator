"use client";

import { useInsight } from "@/lib/api";
import { useRange } from "@/components/shell";
import { AreaChart, type SeriesDef } from "@/components/charts";
import { DigestBanner } from "@/components/digest";
import {
  Leaderboard,
  SprintQuestCard,
  StatTile,
  StreakRow,
  fmtXp,
} from "@/components/game";
import {
  buildRoster,
  deriveSprintQuest,
  teamXp,
  XP_AMBER,
  XP_BLUE,
  XP_PURPLE,
  XP_TEAL,
} from "@/lib/game";
import {
  EmptyState,
  ErrorState,
  LoadingPanel,
  Panel,
  Section,
  formatDate,
} from "@/components/ui";
import type {
  Overview,
  CycleTimeResp,
  ThroughputResp,
  WipResp,
  ByActorResp,
} from "@/lib/types";

const CYCLE_SERIES: SeriesDef[] = [
  { key: "Average", name: "Average", tone: "signal" },
  { key: "Median", name: "Median", tone: "edge" },
];
const THR_SERIES: SeriesDef[] = [
  { key: "Completed", name: "Completed", tone: "signal" },
  { key: "Created", name: "Created", tone: "edge" },
];
const WIP_SERIES: SeriesDef[] = [{ key: "WIP", name: "WIP", tone: "signal" }];

function periodWordFor(range: string): string {
  return range === "day" ? "day" : range === "month" ? "month" : "week";
}

export default function OverviewPage() {
  const { range, anchor, refreshKey } = useRange();
  const ov = useInsight<Overview>("overview", range, anchor, refreshKey);
  const cyc = useInsight<CycleTimeResp>("cycle-time", range, anchor, refreshKey);
  const thr = useInsight<ThroughputResp>("throughput", range, anchor, refreshKey);
  const wip = useInsight<WipResp>("wip", range, anchor, refreshKey);
  const actors = useInsight<ByActorResp>("by-actor", range, anchor, refreshKey);

  if (ov.error) {
    return (
      <Panel title="Overview">
        <ErrorState message={ov.error} />
      </Panel>
    );
  }

  const o = ov.data;
  const loading = ov.loading;
  const isAllTime = range === "all";
  const periodWord = periodWordFor(range);
  const unit = thr.data?.unit ?? range;
  const globalAvg = o?.avg_cycle_hours.current ?? null;

  // --- Gamification: derive players + team XP from live data ---
  const players = buildRoster(actors.data?.actors ?? [], globalAvg, anchor);
  const tXp = teamXp(players);
  // Estimate prior-period team XP from the team throughput delta so the tile can
  // show a directional "gained this period" figure without a second fetch.
  const thrDelta = o?.throughput.delta_pct ?? null;
  const teamXpGain =
    thrDelta != null && thrDelta > -100 ? Math.max(0, tXp - tXp / (1 + thrDelta / 100)) : null;

  // WIP-over-average warning.
  const wipVals = wip.data?.series.map((p) => p.value ?? 0) ?? [];
  const avgWip = wipVals.length ? wipVals.reduce((a, b) => a + b, 0) / wipVals.length : 0;
  const wipWarn =
    o && avgWip > 0 && o.wip > avgWip ? `over ${Math.round(avgWip)} avg` : null;

  const quest = o && !loading ? deriveSprintQuest(o, wip.data?.series, isAllTime) : null;

  // --- Chart data (unchanged) ---
  const cycData =
    cyc.data?.series.map((p) => ({
      date: formatDate(p.period),
      Average: p.avg_hours,
      Median: p.median_hours,
    })) ?? [];
  const cycHasData = cycData.some((d) => d.Average != null || d.Median != null);

  const thrData =
    thr.data?.series.map((p) => ({
      date: formatDate(p.period),
      Completed: p.completed ?? 0,
      Created: p.created ?? 0,
    })) ?? [];

  const wipData = wip.data?.series.map((p) => ({ date: formatDate(p.period), WIP: p.value ?? 0 })) ?? [];

  return (
    <div className="flex flex-col gap-12">
      <Section
        title="Overview"
        description={
          o
            ? isAllTime
              ? "All time — every issue on record, no prior-period comparison."
              : `${cap(range)} of ${formatDate(o.period_start)} — compared against the previous ${range}.`
            : "Loading the current period…"
        }
      >
        {/* Narrative digest — what changed this period and why it matters */}
        <div className="mb-6">
          <DigestBanner />
        </div>

        {/* Sprint quest — the headline objective, above everything else */}
        <div className="mb-6">
          {quest ? (
            <SprintQuestCard quest={quest} periodWord={periodWord} isAllTime={isAllTime} />
          ) : (
            <div className="relative h-[168px] border border-edge bg-surface">
              <div className="loadbar" aria-hidden />
            </div>
          )}
        </div>

        {/* Gamified KPI tiles */}
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
          <StatTile
            label="Throughput"
            value={o?.throughput.current ?? 0}
            unit="done"
            deltaPct={isAllTime ? null : o?.throughput.delta_pct}
            periodWord={periodWord}
            accent={XP_TEAL}
            placeholder={loading || !o}
          />
          <StatTile
            label="Avg cycle time"
            value={o?.avg_cycle_hours.current ?? 0}
            unit="h"
            decimals={1}
            deltaPct={isAllTime ? null : o?.avg_cycle_hours.delta_pct}
            periodWord={periodWord}
            invertDelta
            accent={XP_BLUE}
            placeholder={loading || !o || o.avg_cycle_hours.current == null}
          />
          <StatTile
            label="Work in progress"
            value={o?.wip ?? 0}
            unit="started"
            accent={XP_AMBER}
            warn={wipWarn}
            placeholder={loading || !o}
          />
          <StatTile
            label="Team XP"
            value={tXp}
            unit="XP"
            accent={XP_PURPLE}
            footnote={
              teamXpGain && teamXpGain >= 1 ? `+${fmtXp(teamXpGain)} this ${periodWord}` : undefined
            }
            placeholder={actors.loading}
          />
        </div>
      </Section>

      {/* Leaderboard (replaces Top contributors) + throughput chart */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <Panel
            loading={thr.loading}
            eyebrow="Flow"
            title="Throughput"
            subtitle={`Issues completed vs. created, per ${unit}`}
            bodyClassName="px-2 py-4"
          >
            {thr.loading ? (
              <LoadingPanel height="h-80" />
            ) : thrData.length === 0 ? (
              <EmptyState message="No issues in this window." />
            ) : (
              <AreaChart data={thrData} index="date" series={THR_SERIES} height={320} />
            )}
          </Panel>
        </div>

        <Panel
          loading={actors.loading}
          eyebrow="People"
          title="Leaderboard"
          subtitle="Ranked by XP earned this period"
          bodyClassName="p-0"
        >
          {actors.error ? (
            <div className="p-6">
              <ErrorState message={actors.error} />
            </div>
          ) : actors.loading ? (
            <div className="p-6">
              <LoadingPanel height="h-72" />
            </div>
          ) : players.length === 0 ? (
            <EmptyState message="No contributors this range." />
          ) : (
            <Leaderboard players={players.slice(0, 8)} />
          )}
        </Panel>
      </div>

      {/* Activity streaks — per-person shipping this week */}
      <Section
        title="Activity streaks"
        description="Daily shipping this week (Mon–Sun). Green = shipped, blue = today, empty = no activity."
      >
        <Panel
          loading={actors.loading}
          eyebrow="Momentum"
          title="Shipping streaks"
          subtitle={`${players.filter((p) => p.streak.streak >= 3).length} on a 3+ day streak`}
          bodyClassName="p-0"
        >
          {actors.loading ? (
            <div className="p-6">
              <LoadingPanel height="h-64" />
            </div>
          ) : players.length === 0 ? (
            <EmptyState message="No activity this range." />
          ) : (
            <div className="flex flex-col">
              {players.slice(0, 10).map((p, i) => (
                <StreakRow key={p.actorId} player={p} index={i} />
              ))}
            </div>
          )}
        </Panel>
      </Section>

      {/* Secondary analysis — cycle time trend + WIP side by side */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Panel
          loading={cyc.loading}
          eyebrow="Velocity"
          title="Cycle time trend"
          subtitle={`Hours from start → done, per ${cyc.data?.unit ?? range}`}
          bodyClassName="px-2 py-4"
        >
          {cyc.loading ? (
            <LoadingPanel height="h-72" />
          ) : cycHasData ? (
            <AreaChart data={cycData} index="date" series={CYCLE_SERIES} height={288} valueSuffix="h" />
          ) : (
            <EmptyState message="No cycle-time data for this range." />
          )}
        </Panel>

        <Panel
          loading={wip.loading}
          eyebrow="Load"
          title="Work in progress"
          subtitle={`Issues in a started state, per ${unit}`}
          bodyClassName="px-2 py-4"
        >
          {wip.loading ? (
            <LoadingPanel height="h-72" />
          ) : wipData.length === 0 ? (
            <EmptyState />
          ) : (
            <AreaChart data={wipData} index="date" series={WIP_SERIES} height={288} />
          )}
        </Panel>
      </div>
    </div>
  );
}

function cap(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
