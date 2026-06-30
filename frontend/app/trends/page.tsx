"use client";

import { useInsight } from "@/lib/api";
import { useRange } from "@/components/shell";
import { AreaChart, BarChart, type SeriesDef } from "@/components/charts";
import { EmptyState, ErrorState, LoadingPanel, Panel, Section, formatDate } from "@/components/ui";
import type { CycleTimeResp, ThroughputResp, WipResp } from "@/lib/types";

const THR_SERIES: SeriesDef[] = [
  { key: "Completed", name: "Completed", tone: "signal" },
  { key: "Created", name: "Created", tone: "edge" },
];
const CYCLE_SERIES: SeriesDef[] = [
  { key: "Average", name: "Average", tone: "signal" },
  { key: "Median", name: "Median", tone: "edge" },
];
const WIP_SERIES: SeriesDef[] = [{ key: "WIP", name: "WIP", tone: "signal" }];
const FLOW_SERIES: SeriesDef[] = [{ key: "Net", name: "Net flow", tone: "signal" }];

export default function TrendsPage() {
  const { range, anchor } = useRange();
  const thr = useInsight<ThroughputResp>("throughput", range, anchor);
  const cyc = useInsight<CycleTimeResp>("cycle-time", range, anchor);
  const wip = useInsight<WipResp>("wip", range, anchor);

  const unit = thr.data?.unit ?? range;

  const thrData =
    thr.data?.series.map((p) => ({
      date: formatDate(p.period),
      Completed: p.completed ?? 0,
      Created: p.created ?? 0,
    })) ?? [];

  // Net flow = created − completed. Positive = backlog growing, negative =
  // burning down faster than new work arrives.
  const flowData =
    thr.data?.series.map((p) => ({
      date: formatDate(p.period),
      Net: (p.created ?? 0) - (p.completed ?? 0),
    })) ?? [];

  const cycData =
    cyc.data?.series.map((p) => ({
      date: formatDate(p.period),
      Average: p.avg_hours,
      Median: p.median_hours,
    })) ?? [];
  const cycHasData = cycData.some((d) => d.Average != null || d.Median != null);

  const wipData = wip.data?.series.map((p) => ({ date: formatDate(p.period), WIP: p.value ?? 0 })) ?? [];

  if (thr.error) {
    return (
      <Panel title="Trends">
        <ErrorState message={thr.error} />
      </Panel>
    );
  }

  return (
    <div className="flex flex-col gap-12">
      <Section title="Trends" description={`Activity over time, per ${unit}.`}>
        {/* Primary — throughput, full width and tall */}
        <Panel
          loading={thr.loading}
          eyebrow="Flow"
          title="Throughput"
          subtitle={`Issues completed vs. created, per ${unit}`}
          bodyClassName="px-2 py-4"
        >
          {thr.loading ? (
            <LoadingPanel height="h-[400px]" />
          ) : thrData.length === 0 ? (
            <EmptyState />
          ) : (
            <AreaChart data={thrData} index="date" series={THR_SERIES} height={400} />
          )}
        </Panel>
      </Section>

      {/* Secondary — cycle time + WIP side by side */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Panel
          loading={cyc.loading}
          eyebrow="Velocity"
          title="Cycle time"
          subtitle="Hours from start → done"
          bodyClassName="px-2 py-4"
        >
          {cyc.loading ? (
            <LoadingPanel height="h-80" />
          ) : cycHasData ? (
            <AreaChart data={cycData} index="date" series={CYCLE_SERIES} height={320} valueSuffix="h" />
          ) : (
            <EmptyState message="No cycle-time data yet." />
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
            <LoadingPanel height="h-80" />
          ) : wipData.length === 0 ? (
            <EmptyState />
          ) : (
            <AreaChart data={wipData} index="date" series={WIP_SERIES} height={320} />
          )}
        </Panel>
      </div>

      {/* Tertiary — net flow, the new analytical view */}
      <Panel
        loading={thr.loading}
        eyebrow="Balance"
        title="Net flow"
        subtitle={`Created minus completed — positive means the backlog grew that ${unit}`}
        bodyClassName="px-2 py-4"
      >
        {thr.loading ? (
          <LoadingPanel height="h-72" />
        ) : flowData.length === 0 ? (
          <EmptyState />
        ) : (
          <BarChart data={flowData} index="date" series={FLOW_SERIES} height={288} />
        )}
      </Panel>
    </div>
  );
}
