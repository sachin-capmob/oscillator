"use client";

import { AreaChart, Card, Grid, Text, Title } from "@tremor/react";

import { useInsight } from "@/lib/api";
import { useRange } from "@/components/shell";
import {
  EmptyState,
  ErrorState,
  KpiCard,
  LoadingState,
  formatDate,
} from "@/components/ui";
import type {
  Overview,
  ThroughputResp,
  ThroughputByActorResp,
} from "@/lib/types";

export default function OverviewPage() {
  const { range, anchor } = useRange();

  const ov = useInsight<Overview>("overview", range, anchor);
  const thr = useInsight<ThroughputResp>("throughput", range, anchor);
  const byActor = useInsight<ThroughputByActorResp>(
    "throughput-by-actor",
    range,
    anchor
  );

  if (ov.loading) return <LoadingState />;
  if (ov.error) return <ErrorState message={ov.error} />;
  if (!ov.data) return <EmptyState />;

  const o = ov.data;

  // Global chart data — one row per period with both Completed and Created.
  const chartData =
    thr.data?.series.map((p) => ({
      date: formatDate(p.period),
      Completed: p.completed ?? 0,
      Created: p.created ?? 0,
    })) ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Title>Overview</Title>
        <Text>
          {range[0].toUpperCase() + range.slice(1)} of{" "}
          {formatDate(o.period_start)} — comparisons vs. the previous {range}.
        </Text>
      </div>

      {/* KPI cards */}
      <Grid numItemsSm={2} numItemsLg={4} className="gap-4">
        <KpiCard
          title="Throughput"
          value={o.throughput.current ?? 0}
          unit="done"
          deltaPct={o.throughput.delta_pct}
          accent="indigo"
        />
        <KpiCard
          title="Avg cycle time"
          value={o.avg_cycle_hours.current ?? "—"}
          unit="h"
          deltaPct={o.avg_cycle_hours.delta_pct}
          invertDelta
          accent="cyan"
        />
        <KpiCard title="Work in progress" value={o.wip} unit="started" accent="amber" />
        <KpiCard title="Open issues" value={o.open_issues} accent="emerald" />
      </Grid>

      {/* Global throughput trend — Completed (blue) + Created (yellow) */}
      <Card>
        <Title>Throughput trend</Title>
        <Text>Issues completed and created per {thr.data?.unit ?? range}</Text>
        {chartData.length === 0 ? (
          <EmptyState message="No issues in this window." />
        ) : (
          <AreaChart
            className="mt-4 h-64"
            data={chartData}
            index="date"
            categories={["Completed", "Created"]}
            colors={["blue", "yellow"]}
            showLegend={true}
            yAxisWidth={36}
          />
        )}
      </Card>

      {/* Per-person throughput charts */}
      {byActor.data && byActor.data.actors.length > 0 && (
        <div className="space-y-4">
          <div>
            <Title>Throughput by person</Title>
            <Text>
              Issues completed (blue) and created (yellow) per person per{" "}
              {byActor.data.unit}
            </Text>
          </div>
          <Grid numItemsSm={1} numItemsLg={2} className="gap-4">
            {byActor.data.actors.map((actor) => {
              const actorChartData = actor.series.map((p) => ({
                date: formatDate(p.period),
                Completed: p.completed ?? 0,
                Created: p.created ?? 0,
              }));
              const label =
                actor.name ?? actor.email ?? `Actor ${actor.actor_id}`;
              return (
                <Card key={actor.actor_id}>
                  <Title>{label}</Title>
                  {actorChartData.length === 0 ? (
                    <EmptyState message="No data." />
                  ) : (
                    <AreaChart
                      className="mt-3 h-48"
                      data={actorChartData}
                      index="date"
                      categories={["Completed", "Created"]}
                      colors={["blue", "yellow"]}
                      showLegend={true}
                      yAxisWidth={36}
                    />
                  )}
                </Card>
              );
            })}
          </Grid>
        </div>
      )}
    </div>
  );
}
