"use client";

import { AreaChart, Card, Title, Text, Grid } from "@tremor/react";

import { useInsight } from "@/lib/api";
import { useRange } from "@/components/shell";
import { EmptyState, ErrorState, LoadingState, formatDate } from "@/components/ui";
import type { CycleTimeResp, ThroughputResp, WipResp } from "@/lib/types";

export default function TrendsPage() {
  const { range, anchor } = useRange();
  const thr = useInsight<ThroughputResp>("throughput", range, anchor);
  const cyc = useInsight<CycleTimeResp>("cycle-time", range, anchor);
  const wip = useInsight<WipResp>("wip", range, anchor);

  if (thr.loading || cyc.loading || wip.loading) return <LoadingState />;
  if (thr.error) return <ErrorState message={thr.error} />;

  const unit = thr.data?.unit ?? range;
  const thrData = thr.data?.series.map((p) => ({ date: formatDate(p.period), Completed: p.value ?? 0 })) ?? [];
  const cycData =
    cyc.data?.series.map((p) => ({
      date: formatDate(p.period),
      Average: p.avg_hours,
      Median: p.median_hours,
    })) ?? [];
  const wipData = wip.data?.series.map((p) => ({ date: formatDate(p.period), WIP: p.value ?? 0 })) ?? [];

  return (
    <div className="space-y-6">
      <div>
        <Title>Trends</Title>
        <Text>Per-{unit} activity over time.</Text>
      </div>

      <Card>
        <Title>Throughput</Title>
        <Text>Issues completed per {unit}</Text>
        {thrData.length === 0 ? (
          <EmptyState message="No completed issues yet." />
        ) : (
          <AreaChart
            className="mt-4 h-72"
            data={thrData}
            index="date"
            categories={["Completed"]}
            colors={["blue"]}
            showLegend={false}
            yAxisWidth={36}
          />
        )}
      </Card>

      <Grid numItemsLg={2} className="gap-6">
        <Card>
          <Title>Cycle time</Title>
          <Text>Hours from start → done</Text>
          {cycData.every((d) => d.Average == null && d.Median == null) ? (
            <EmptyState message="No cycle-time data yet." />
          ) : (
            <AreaChart
              className="mt-4 h-72"
              data={cycData}
              index="date"
              categories={["Average", "Median"]}
              colors={["indigo", "cyan"]}
              connectNulls
              yAxisWidth={40}
              valueFormatter={(v) => `${v}h`}
            />
          )}
        </Card>

        <Card>
          <Title>Work in progress</Title>
          <Text>Issues in a started state per {unit}</Text>
          {wipData.length === 0 ? (
            <EmptyState />
          ) : (
            <AreaChart
              className="mt-4 h-72"
              data={wipData}
              index="date"
              categories={["WIP"]}
              colors={["amber"]}
              showLegend={false}
              yAxisWidth={36}
            />
          )}
        </Card>
      </Grid>
    </div>
  );
}
