"use client";

import { useInsight } from "@/lib/api";
import { useRange } from "@/components/shell";
import { AreaChart, type SeriesDef } from "@/components/charts";
import {
  EmptyState,
  ErrorState,
  Kpi,
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

export default function OverviewPage() {
  const { range, anchor } = useRange();
  const ov = useInsight<Overview>("overview", range, anchor);
  const cyc = useInsight<CycleTimeResp>("cycle-time", range, anchor);
  const thr = useInsight<ThroughputResp>("throughput", range, anchor);
  const wip = useInsight<WipResp>("wip", range, anchor);
  const actors = useInsight<ByActorResp>("by-actor", range, anchor);

  if (ov.error) {
    return (
      <Panel title="Overview">
        <ErrorState message={ov.error} />
      </Panel>
    );
  }

  const o = ov.data;
  const loading = ov.loading;
  const unit = thr.data?.unit ?? range;

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

  const contributors = [...(actors.data?.actors ?? [])]
    .sort((a, b) => b.throughput - a.throughput)
    .slice(0, 8);
  const maxThr = Math.max(1, ...contributors.map((c) => c.throughput));

  return (
    <div className="flex flex-col gap-12">
      <Section
        title="Overview"
        description={
          o
            ? range === "all"
              ? "All time — every issue on record, no prior-period comparison."
              : `${cap(range)} of ${formatDate(o.period_start)} — compared against the previous ${range}.`
            : "Loading the current period…"
        }
      >
        {/* KPI row — four spacious cards */}
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
          <Kpi
            label="Throughput"
            value={o?.throughput.current ?? 0}
            unit="done"
            deltaPct={o?.throughput.delta_pct}
            placeholder={loading || !o}
          />
          <Kpi
            label="Avg cycle time"
            value={o?.avg_cycle_hours.current ?? 0}
            unit="h"
            decimals={1}
            deltaPct={o?.avg_cycle_hours.delta_pct}
            invertDelta
            placeholder={loading || !o || o.avg_cycle_hours.current == null}
          />
          <Kpi label="Work in progress" value={o?.wip ?? 0} unit="started" placeholder={loading || !o} />
          <Kpi label="Open issues" value={o?.open_issues ?? 0} unit="open" placeholder={loading || !o} />
        </div>
      </Section>

      {/* Primary analysis — throughput (8) + top contributors (4) */}
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
          title="Top contributors"
          subtitle="By issues completed"
          bodyClassName="p-0"
        >
          {actors.loading ? (
            <div className="p-6">
              <LoadingPanel height="h-72" />
            </div>
          ) : contributors.length === 0 ? (
            <EmptyState message="No contributors this range." />
          ) : (
            <div className="flex flex-col">
              {contributors.map((c) => {
                const name = c.name ?? c.email ?? `Actor ${c.actor_id}`;
                const pct = (c.throughput / maxThr) * 100;
                return (
                  <div
                    key={c.actor_id}
                    className="relative flex items-center justify-between border-b border-edge px-6 py-3.5 last:border-b-0"
                  >
                    <span
                      aria-hidden
                      className="absolute inset-y-0 left-0 z-0"
                      style={{ width: `${pct}%`, background: "rgba(var(--signal-rgb), 0.08)" }}
                    />
                    <span className="relative z-10 truncate pr-4 text-body text-ink">{name}</span>
                    <span className="relative z-10 font-mono text-body text-ink">{c.throughput}</span>
                  </div>
                );
              })}
            </div>
          )}
        </Panel>
      </div>

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
