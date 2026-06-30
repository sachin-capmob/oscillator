"use client";

import { useInsight } from "@/lib/api";
import { useRange } from "@/components/shell";
import { AreaChart, BarChart, type SeriesDef } from "@/components/charts";
import { EmptyState, ErrorState, Eyebrow, LoadingPanel, Panel, Section, formatDate } from "@/components/ui";
import type { ActorStat, ByActorResp, ThroughputByActorResp } from "@/lib/types";

const PERSON_SERIES: SeriesDef[] = [
  { key: "Completed", name: "Completed", tone: "signal" },
  { key: "Created", name: "Created", tone: "edge" },
];
const COMPARE_SERIES: SeriesDef[] = [
  { key: "Completed", name: "Completed", tone: "signal" },
  { key: "Created", name: "Created", tone: "edge" },
];

// Short display name for axis labels — emails collapse to their handle so the
// comparison bars stay readable.
function shortName(a: { name: string | null; email: string | null; actor_id: number }): string {
  if (a.name) return a.name;
  if (a.email) return a.email.split("@")[0];
  return `Actor ${a.actor_id}`;
}

export default function PeoplePage() {
  const { range, anchor } = useRange();
  const table = useInsight<ByActorResp>("by-actor", range, anchor);
  const series = useInsight<ThroughputByActorResp>("throughput-by-actor", range, anchor);

  const actors = table.data?.actors ?? [];

  // Everyone's output side by side — completed vs. created, ranked by
  // throughput so the leaderboard reads top-down.
  const compareData = [...actors]
    .sort((a, b) => b.throughput - a.throughput)
    .map((a) => ({
      name: shortName(a),
      Completed: a.throughput,
      Created: a.created,
    }));
  // Give the chart enough height to fit every person comfortably.
  const compareHeight = Math.max(160, compareData.length * 44 + 24);

  // Only show small-multiples for people with any activity in the window, most
  // active first, capped so the grid stays scannable.
  const personSeries = [...(series.data?.actors ?? [])]
    .map((a) => ({
      ...a,
      total: a.series.reduce((s, p) => s + (p.completed ?? 0), 0),
    }))
    .filter((a) => a.total > 0)
    .sort((a, b) => b.total - a.total)
    .slice(0, 6);

  return (
    <div className="flex flex-col gap-12">
      <Section
        title="People"
        description="Per-person activity for the selected range. Trend = last 7 periods completed."
      >
        <Panel
          loading={table.loading}
          eyebrow="Roster"
          title="Activity by person"
          subtitle={`${actors.length} active this range`}
          bodyClassName="p-0"
        >
          {table.error ? (
            <ErrorState message={table.error} />
          ) : table.loading ? (
            <div className="p-6">
              <LoadingPanel height="h-64" />
            </div>
          ) : actors.length === 0 ? (
            <EmptyState message="No per-person activity in this range." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b border-edge">
                    <Th align="left">Name</Th>
                    <Th align="right">Throughput</Th>
                    <Th align="right">Avg cycle</Th>
                    <Th align="right">Created</Th>
                    <Th align="right">Comments</Th>
                    <Th align="right">Trend</Th>
                  </tr>
                </thead>
                <tbody>
                  {actors.map((a, i) => (
                    <Row key={a.actor_id} actor={a} even={i % 2 === 0} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </Section>

      {/* Everyone at a glance — ranked completed vs. created */}
      <Section
        title="Performance comparison"
        description="Completed vs. created this range, ranked by throughput."
      >
        <Panel loading={table.loading} eyebrow="Leaderboard" title="Output by person" bodyClassName="px-2 py-5">
          {table.error ? (
            <ErrorState message={table.error} />
          ) : table.loading ? (
            <LoadingPanel height="h-72" />
          ) : compareData.length === 0 ? (
            <EmptyState message="No per-person activity in this range." />
          ) : (
            <BarChart
              data={compareData}
              index="name"
              series={COMPARE_SERIES}
              horizontal
              height={compareHeight}
              categoryWidth={140}
            />
          )}
        </Panel>
      </Section>

      {/* Per-person throughput small-multiples */}
      <Section
        title="Throughput by person"
        description={`Completed vs. created over time, per ${series.data?.unit ?? range}.`}
      >
        {series.loading ? (
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 xl:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <Panel key={i} loading bodyClassName="px-2 py-4">
                <LoadingPanel height="h-48" />
              </Panel>
            ))}
          </div>
        ) : personSeries.length === 0 ? (
          <Panel>
            <EmptyState message="No per-person throughput in this range." />
          </Panel>
        ) : (
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 xl:grid-cols-3">
            {personSeries.map((a) => {
              const name = a.name ?? a.email ?? `Actor ${a.actor_id}`;
              const data = a.series.map((p) => ({
                date: formatDate(p.period),
                Completed: p.completed ?? 0,
                Created: p.created ?? 0,
              }));
              return (
                <Panel key={a.actor_id} title={name} subtitle={`${a.total} completed`} bodyClassName="px-2 py-4">
                  <AreaChart data={data} index="date" series={PERSON_SERIES} height={200} />
                </Panel>
              );
            })}
          </div>
        )}
      </Section>
    </div>
  );
}

function Th({ children, align }: { children: React.ReactNode; align: "left" | "right" }) {
  return (
    <th className={`px-6 py-3.5 ${align === "right" ? "text-right" : "text-left"}`}>
      <Eyebrow>{children}</Eyebrow>
    </th>
  );
}

function Row({ actor: a, even }: { actor: ActorStat; even: boolean }) {
  const name = a.name ?? a.email ?? `Actor ${a.actor_id}`;
  return (
    <tr
      className="group border-b border-edge transition-colors last:border-b-0 hover:bg-edge"
      style={{ background: even ? "var(--surface)" : "var(--void)" }}
    >
      <td className="px-6 py-3.5 text-body text-ink">{name}</td>
      <td className="px-6 py-3.5 text-right font-mono text-body text-ink">{a.throughput}</td>
      <td className="px-6 py-3.5 text-right font-mono text-body text-muted">
        {a.avg_cycle_hours ?? "--"}
        {a.avg_cycle_hours != null && <span className="text-muted">h</span>}
      </td>
      <td className="px-6 py-3.5 text-right font-mono text-body text-muted">{a.created}</td>
      <td className="px-6 py-3.5 text-right font-mono text-body text-muted">{a.comments}</td>
      <td className="px-6 py-3.5">
        <div className="flex justify-end">
          <Sparkline values={a.sparkline} />
        </div>
      </td>
    </tr>
  );
}

// 7 bars; --signal at 40% opacity, the most recent (current) period at 100%.
function Sparkline({ values }: { values: number[] }) {
  const last7 = values.slice(-7);
  while (last7.length < 7) last7.unshift(0);
  const max = Math.max(1, ...last7);
  return (
    <div className="flex h-7 items-end gap-0.5" aria-hidden>
      {last7.map((v, i) => {
        const h = 2 + (v / max) * 26;
        const current = i === last7.length - 1;
        return (
          <span
            key={i}
            className="w-1"
            style={{ height: `${h}px`, background: "var(--signal)", opacity: current ? 1 : 0.4 }}
          />
        );
      })}
    </div>
  );
}
