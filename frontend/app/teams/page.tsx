"use client";

import { BarChart, Card, Flex, Grid, Metric, Text, Title } from "@tremor/react";

import { useInsight } from "@/lib/api";
import { useRange } from "@/components/shell";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui";
import type { ByTeamResp } from "@/lib/types";

export default function TeamsPage() {
  const { range, anchor } = useRange();
  const { data, loading, error } = useInsight<ByTeamResp>("by-team", range, anchor);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;
  if (!data || data.teams.length === 0)
    return (
      <div className="space-y-6">
        <Title>Teams &amp; Cycles</Title>
        <EmptyState message="No team activity in this range." />
      </div>
    );

  const velocity = data.teams.map((t) => ({
    name: t.name ?? t.key ?? `Team ${t.team_id}`,
    Throughput: t.throughput,
    WIP: t.wip,
  }));

  return (
    <div className="space-y-6">
      <div>
        <Title>Teams &amp; Cycles</Title>
        <Text>
          Velocity for the current {range === "month" ? "month" : "week"} (starting{" "}
          {new Date(data.period_start).toLocaleDateString()}).
        </Text>
      </div>

      <Card>
        <Title>Velocity by team</Title>
        <BarChart
          className="mt-4 h-72"
          data={velocity}
          index="name"
          categories={["Throughput", "WIP"]}
          colors={["blue", "amber"]}
          yAxisWidth={36}
          stack={false}
        />
      </Card>

      <Grid numItemsSm={2} numItemsLg={3} className="gap-4">
        {data.teams.map((t) => (
          <Card key={t.team_id}>
            <Text>{t.name ?? t.key ?? `Team ${t.team_id}`}</Text>
            <Flex className="mt-2" justifyContent="start" alignItems="baseline">
              <Metric>{t.throughput}</Metric>
              <Text className="ml-2">completed</Text>
            </Flex>
            <div className="mt-4 space-y-1 text-tremor-default text-tremor-content">
              <Flex justifyContent="between">
                <span>Avg cycle</span>
                <span className="text-tremor-content-strong">
                  {t.avg_cycle_hours ?? "—"} h
                </span>
              </Flex>
              <Flex justifyContent="between">
                <span>Median cycle</span>
                <span className="text-tremor-content-strong">
                  {t.median_cycle_hours ?? "—"} h
                </span>
              </Flex>
              <Flex justifyContent="between">
                <span>WIP</span>
                <span className="text-tremor-content-strong">{t.wip}</span>
              </Flex>
              <Flex justifyContent="between">
                <span>Comments</span>
                <span className="text-tremor-content-strong">{t.comments}</span>
              </Flex>
              <Flex justifyContent="between">
                <span>Scope added</span>
                <span className="text-tremor-content-strong">{t.scope_added}</span>
              </Flex>
            </div>
          </Card>
        ))}
      </Grid>
    </div>
  );
}
