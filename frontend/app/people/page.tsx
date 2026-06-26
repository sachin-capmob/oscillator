"use client";

import {
  Card,
  SparkAreaChart,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
  Text,
  Title,
} from "@tremor/react";

import { useInsight } from "@/lib/api";
import { useRange } from "@/components/shell";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui";
import type { ByActorResp } from "@/lib/types";

export default function PeoplePage() {
  const { range, anchor } = useRange();
  const { data, loading, error } = useInsight<ByActorResp>("by-actor", range, anchor);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;
  if (!data || data.actors.length === 0)
    return (
      <div className="space-y-6">
        <Title>People</Title>
        <EmptyState message="No per-person activity in this range." />
      </div>
    );

  return (
    <div className="space-y-6">
      <div>
        <Title>People</Title>
        <Text>
          Per-person activity for the selected {range}. Sparkline = last 14 days completed.
        </Text>
      </div>

      <Card>
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Person</TableHeaderCell>
              <TableHeaderCell className="text-right">Completed</TableHeaderCell>
              <TableHeaderCell className="text-right">Created</TableHeaderCell>
              <TableHeaderCell className="text-right">Avg cycle (h)</TableHeaderCell>
              <TableHeaderCell className="text-right">Comments</TableHeaderCell>
              <TableHeaderCell className="text-right">Last 14 days</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.actors.map((a) => (
              <TableRow key={a.actor_id}>
                <TableCell>
                  <span className="font-medium text-tremor-content-strong">
                    {a.name ?? a.email ?? `Actor ${a.actor_id}`}
                  </span>
                </TableCell>
                <TableCell className="text-right">{a.throughput}</TableCell>
                <TableCell className="text-right">{a.created}</TableCell>
                <TableCell className="text-right">
                  {a.avg_cycle_hours ?? "—"}
                </TableCell>
                <TableCell className="text-right">{a.comments}</TableCell>
                <TableCell>
                  <div className="flex justify-end">
                    <SparkAreaChart
                      data={a.sparkline.map((v, i) => ({ i, v }))}
                      index="i"
                      categories={["v"]}
                      colors={["blue"]}
                      className="h-8 w-28"
                    />
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
