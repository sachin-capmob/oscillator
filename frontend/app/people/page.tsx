"use client";

import { useEffect, useState } from "react";
import { useInsight, fetchActorIssues } from "@/lib/api";
import { useRange } from "@/components/shell";
import { AreaChart, BarChart, type SeriesDef } from "@/components/charts";
import { EmptyState, ErrorState, Eyebrow, LoadingPanel, Panel, Section, formatDate } from "@/components/ui";
import { PlayerCard } from "@/components/game";
import { buildRoster } from "@/lib/game";
import type { ActorStat, ByActorResp, Overview, ThroughputByActorResp, ActorIssuesResp } from "@/lib/types";

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

function displayName(a: { name: string | null; email: string | null; actor_id: number }): string {
  if (a.name) return a.name;
  if (a.email) return a.email;
  return `Actor ${a.actor_id}`;
}

/* -------------------------------------------------------------------------- */
/* Person Issues Panel — dropdown to pick a person, shows their closed issues */
/* -------------------------------------------------------------------------- */
function PersonIssuesPanel({ actors }: { actors: ActorStat[] }) {
  const { range, anchor } = useRange();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [issues, setIssues] = useState<ActorIssuesResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset selection when range/anchor changes
  useEffect(() => {
    setSelectedId(null);
    setIssues(null);
  }, [range, anchor]);

  // Auto-select first actor once list loads
  useEffect(() => {
    if (actors.length > 0 && selectedId === null) {
      setSelectedId(actors[0].actor_id);
    }
  }, [actors, selectedId]);

  // Fetch issues whenever selection changes
  useEffect(() => {
    if (selectedId === null) return;
    let alive = true;
    setLoading(true);
    setError(null);
    setIssues(null);
    fetchActorIssues(selectedId, range, anchor)
      .then((d) => {
        if (alive) { setIssues(d); setLoading(false); }
      })
      .catch((e) => {
        if (alive) { setError(String(e)); setLoading(false); }
      });
    return () => { alive = false; };
  }, [selectedId, range, anchor]);

  if (actors.length === 0) return null;

  const selectedActor = actors.find((a) => a.actor_id === selectedId);

  return (
    <Section
      title="Closed issues by person"
      description="Select a team member to see all issues they closed in the selected range."
    >
      <Panel
        loading={loading}
        eyebrow="Person"
        title={selectedActor ? displayName(selectedActor) : "Select a person"}
        subtitle={
          issues
            ? `${issues.issues.length} issue${issues.issues.length !== 1 ? "s" : ""} closed this ${range}`
            : undefined
        }
        bodyClassName="p-0"
      >
        {/* Dropdown selector */}
        <div className="border-b border-edge px-6 py-4">
          <div className="flex items-center gap-3">
            <Eyebrow>Person</Eyebrow>
            <div className="relative">
              <select
                id="person-issues-select"
                value={selectedId ?? ""}
                onChange={(e) => setSelectedId(Number(e.target.value))}
                className="appearance-none rounded border border-edge bg-surface py-1.5 pl-3 pr-8 text-body text-ink focus:outline-none focus:ring-1"
                style={{
                  fontSize: "13px",
                  minWidth: "200px",
                  // Custom focus ring using signal colour
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  ["--tw-ring-color" as any]: "var(--signal)",
                }}
              >
                {actors.map((a) => (
                  <option key={a.actor_id} value={a.actor_id}>
                    {displayName(a)} ({a.throughput} closed)
                  </option>
                ))}
              </select>
              {/* Custom chevron */}
              <span
                className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2"
                aria-hidden
              >
                <svg width="10" height="6" viewBox="0 0 10 6" fill="none">
                  <path d="M1 1l4 4 4-4" stroke="var(--muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
            </div>
          </div>
        </div>

        {/* Issue list */}
        {loading ? (
          <div className="p-6">
            <LoadingPanel height="h-48" />
          </div>
        ) : error ? (
          <div className="p-6">
            <ErrorState message={error} />
          </div>
        ) : issues && issues.issues.length === 0 ? (
          <EmptyState message="No issues closed in this range." />
        ) : issues ? (
          <div className="flex flex-col">
            {issues.issues.map((issue, i) => (
              <div
                key={issue.issue_id}
                className="flex items-center gap-4 border-b border-edge px-6 py-3.5 last:border-b-0"
                style={{
                  background: i % 2 === 0 ? "var(--surface)" : "var(--void)",
                }}
              >
                {/* Identifier badge */}
                {issue.identifier && (
                  <span
                    className="shrink-0 rounded px-2 py-0.5 font-mono text-[11px] font-medium"
                    style={{
                      background: "rgba(var(--signal-rgb), 0.12)",
                      color: "var(--signal)",
                    }}
                  >
                    {issue.identifier}
                  </span>
                )}

                {/* Title + team */}
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="truncate text-body text-ink">
                    {issue.title ?? "(Untitled)"}
                  </span>
                  {issue.team_name && (
                    <span className="text-[11px] text-muted">{issue.team_name}</span>
                  )}
                </div>

                {/* Cycle time + completion date */}
                <div className="flex shrink-0 flex-col items-end gap-0.5">
                  {issue.cycle_hours != null && (
                    <span className="font-mono text-[12px] text-ink">
                      {issue.cycle_hours < 24
                        ? `${issue.cycle_hours}h`
                        : `${(issue.cycle_hours / 24).toFixed(1)}d`}
                    </span>
                  )}
                  {issue.completed_at && (
                    <span className="font-mono text-[11px] text-muted">
                      {new Date(issue.completed_at).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                      })}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </Panel>
    </Section>
  );
}

export default function PeoplePage() {
  const { range, anchor, refreshKey } = useRange();
  const table = useInsight<ByActorResp>("by-actor", range, anchor, refreshKey);
  const overview = useInsight<Overview>("overview", range, anchor, refreshKey);
  const series = useInsight<ThroughputByActorResp>("throughput-by-actor", range, anchor, refreshKey);

  const actors = table.data?.actors ?? [];

  // Gamified player profiles — XP, level, streaks, badges — from the same
  // aggregate data the roster table uses. Global avg cycle time (from overview)
  // drives the under-average XP bonus so numbers match the Overview leaderboard.
  const players = buildRoster(actors, overview.data?.avg_cycle_hours.current ?? null, anchor);

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
      {/* Player cards — the gamified roster: level, XP, streak, achievements */}
      <Section
        title="Player cards"
        description="Every teammate as a player — level & title from XP, progress to the next level, and achievement badges (earned + locked)."
      >
        {table.error ? (
          <Panel>
            <ErrorState message={table.error} />
          </Panel>
        ) : table.loading ? (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="relative h-72 border border-edge bg-surface">
                <div className="loadbar" aria-hidden />
              </div>
            ))}
          </div>
        ) : players.length === 0 ? (
          <Panel>
            <EmptyState message="No players active in this range." />
          </Panel>
        ) : (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-3">
            {players.map((p, i) => (
              <PlayerCard key={p.actorId} player={p} index={i} />
            ))}
          </div>
        )}
      </Section>

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

      {/* Closed issues by person — dropdown explorer */}
      <PersonIssuesPanel actors={actors} />

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
