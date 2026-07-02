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

      {/* Per-team detail cards */}
      {!loading && !empty && (
        <Section title="Team detail" description="Per-team breakdown for the current period.">
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-3">
            {teams.map((t) => (
              <TeamCard key={t.team_id} team={t} />
            ))}
          </div>
        </Section>
      )}
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

function TeamCard({ team: t }: { team: TeamStat }) {
  const name = t.name ?? t.key ?? `Team ${t.team_id}`;
  return (
    <div className="border border-edge bg-surface px-6 py-6">
      <div className="flex items-center gap-2.5">
        <span
          aria-hidden
          className="inline-block h-3.5 w-px shrink-0"
          style={{ background: "var(--signal)" }}
        />
        <h3 className="truncate text-title font-medium text-ink">{name}</h3>
      </div>
      <div className="mt-4 flex items-baseline gap-2">
        <span className="font-mono text-callout font-light text-ink">{t.throughput}</span>
        <span className="font-mono text-body text-muted">completed</span>
      </div>
      <dl className="mt-5 flex flex-col gap-2.5 text-body">
        <Stat label="Avg cycle" value={t.avg_cycle_hours} suffix="h" />
        <Stat label="Median cycle" value={t.median_cycle_hours} suffix="h" />
        <Stat label="WIP" value={t.wip} />
        <Stat label="Comments" value={t.comments} />
        <Stat label="Scope added" value={t.scope_added} negative={t.scope_added > 0} />
      </dl>
    </div>
  );
}

function Stat({
  label,
  value,
  suffix = "",
  negative = false,
}: {
  label: string;
  value: number | null;
  suffix?: string;
  negative?: boolean;
}) {
  return (
    <div className="flex items-center justify-between border-t border-edge pt-2.5 first:border-t-0 first:pt-0">
      <dt className="text-muted">{label}</dt>
      <dd className="font-mono" style={{ color: negative ? "var(--negative)" : "var(--ink)" }}>
        {value ?? "--"}
        {value != null && suffix}
      </dd>
    </div>
  );
}
