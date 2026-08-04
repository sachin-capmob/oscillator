"use client";

import { useInsight } from "@/lib/api";
import { useRange } from "@/components/shell";
import { BarChart, type SeriesDef } from "@/components/charts";
import { EmptyState, ErrorState, Eyebrow, LoadingPanel, Panel, Section } from "@/components/ui";
import type { ByTeamResp, TeamStat } from "@/lib/types";

const VELOCITY_SERIES: SeriesDef[] = [
  { key: "Throughput", name: "Throughput", tone: "signal" },
  { key: "WIP", name: "WIP", tone: "edge" },
];
const CYCLE_SERIES: SeriesDef[] = [
  { key: "Average", name: "Avg cycle", tone: "signal" },
  { key: "Median", name: "Median cycle", tone: "edge" },
];

export default function CyclesPage() {
  const { range, anchor } = useRange();
  const { data, loading, error } = useInsight<ByTeamResp>("by-team", range, anchor);

  const teams = data?.teams ?? [];

  const velocityData = teams.map((t) => ({
    name: t.name ?? t.key ?? `Team ${t.team_id}`,
    Throughput: t.throughput,
    WIP: t.wip,
  }));
  const cycleData = teams
    .filter((t) => t.avg_cycle_hours != null || t.median_cycle_hours != null)
    .map((t) => ({
      name: t.name ?? t.key ?? `Team ${t.team_id}`,
      Average: t.avg_cycle_hours ?? 0,
      Median: t.median_cycle_hours ?? 0,
    }));

  if (error) {
    return (
      <Panel title="Cycles">
        <ErrorState message={error} />
      </Panel>
    );
  }

  const empty = !loading && teams.length === 0;

  return (
    <div className="flex flex-col gap-12">
      <Section
        title="Cycles"
        description={`Team velocity ${range === "all" ? "across all time" : `for the current ${range}`}. Bar = completed share of in-flight work.`}
      >
        <Panel
          loading={loading}
          eyebrow="Progress"
          title="Completion"
          subtitle="Done vs. in-flight, by team"
          bodyClassName="p-0"
        >
          {loading ? (
            <div className="p-6">
              <LoadingPanel height="h-40" />
            </div>
          ) : empty ? (
            <EmptyState message="No team activity in this range." />
          ) : (
            <div className="flex flex-col">
              {teams.map((t) => (
                <CycleRow key={t.team_id} team={t} />
              ))}
            </div>
          )}
        </Panel>
      </Section>

      {/* Velocity + cycle-time comparison side by side */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Panel
          loading={loading}
          eyebrow="Velocity"
          title="Velocity by team"
          subtitle="Throughput vs. WIP"
          bodyClassName="px-2 py-4"
        >
          {loading ? (
            <LoadingPanel height="h-72" />
          ) : empty ? (
            <EmptyState />
          ) : (
            <BarChart data={velocityData} index="name" series={VELOCITY_SERIES} height={288} />
          )}
        </Panel>

        <Panel
          loading={loading}
          eyebrow="Velocity"
          title="Cycle time by team"
          subtitle="Average vs. median hours"
          bodyClassName="px-2 py-4"
        >
          {loading ? (
            <LoadingPanel height="h-72" />
          ) : cycleData.length === 0 ? (
            <EmptyState message="No cycle-time data for these teams." />
          ) : (
            <BarChart data={cycleData} index="name" series={CYCLE_SERIES} height={288} />
          )}
        </Panel>
      </div>
    </div>
  );
}

function CycleRow({ team: t }: { team: TeamStat }) {
  const name = t.name ?? t.key ?? `Team ${t.team_id}`;
  const inflight = t.throughput + t.wip;
  const pct = inflight > 0 ? Math.round((t.throughput / inflight) * 100) : 0;

  return (
    <div className="grid grid-cols-12 items-center gap-5 border-b border-edge px-6 py-4 last:border-b-0">
      <div className="col-span-12 sm:col-span-3">
        <div className="text-body text-ink">{name}</div>
        <Eyebrow>
          {t.throughput} done · {t.wip} wip
        </Eyebrow>
      </div>
      <div className="col-span-10 sm:col-span-8">
        <div className="relative h-7 w-full border border-edge bg-void">
          <div
            className="absolute inset-y-0 left-0"
            style={{ width: `${pct}%`, background: "rgba(var(--signal-rgb), 0.6)" }}
          />
          <div
            className="absolute top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2"
            style={{ left: `${pct}%`, background: "var(--signal)" }}
            aria-hidden
          />
          {t.scope_added > 0 && (
            <span
              className="absolute right-2 top-1/2 -translate-y-1/2 font-mono text-[11px]"
              style={{ color: "var(--negative)" }}
            >
              +{t.scope_added}
            </span>
          )}
        </div>
      </div>
      <div className="col-span-2 sm:col-span-1 text-right">
        <span className="font-mono text-body text-ink">{pct}</span>
        <span className="font-mono text-body text-muted">%</span>
      </div>
    </div>
  );
}

