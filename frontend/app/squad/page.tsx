"use client";

import { useInsight } from "@/lib/api";
import { useRange } from "@/components/shell";
import { EmptyState, ErrorState, Eyebrow, Panel, Section } from "@/components/ui";
import { FutCard, SquadPitch } from "@/components/fut";
import { buildRoster } from "@/lib/game";
import { buildSquad, STAT_META } from "@/lib/fut";
import type { ByActorResp, Overview } from "@/lib/types";

export default function SquadPage() {
  const { range, anchor, refreshKey } = useRange();
  const table = useInsight<ByActorResp>("by-actor", range, anchor, refreshKey);
  const overview = useInsight<Overview>("overview", range, anchor, refreshKey);

  const players = buildRoster(
    table.data?.actors ?? [],
    overview.data?.avg_cycle_hours.current ?? null,
    anchor,
  );
  const squad = buildSquad(players);
  const captain = squad[0];

  return (
    <div className="flex flex-col gap-12">
      <Section
        title="Squad"
        description="Every teammate as a football player card — rated out of 99 from live Linear stats, in the FIFA Ultimate Team tradition. Bronze → silver → gold → icon."
      >
        {table.error ? (
          <Panel>
            <ErrorState message={table.error} />
          </Panel>
        ) : table.loading ? (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="relative h-80 border border-edge bg-surface">
                <div className="loadbar" aria-hidden />
              </div>
            ))}
          </div>
        ) : squad.length === 0 ? (
          <Panel>
            <EmptyState message="No players active in this range." />
          </Panel>
        ) : (
          <div className="flex flex-col gap-10">
            {/* Captain spotlight + rating legend */}
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,340px)_1fr]">
              <div className="flex flex-col gap-3">
                <Eyebrow>Team captain · highest rated</Eyebrow>
                {captain && <FutCard player={captain} big />}
              </div>
              <RatingKey />
            </div>

            {/* Starting XI on the pitch */}
            <div className="flex flex-col gap-3">
              <Eyebrow>Starting XI · by role</Eyebrow>
              <SquadPitch squad={squad} />
            </div>

            {/* Full squad grid */}
            <div className="flex flex-col gap-3">
              <Eyebrow>Full squad · {squad.length} players</Eyebrow>
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {squad.map((p, i) => (
                  <FutCard key={p.base.actorId} player={p} index={i} />
                ))}
              </div>
            </div>
          </div>
        )}
      </Section>
    </div>
  );
}

/* How the six football stats map to real Linear activity. */
function RatingKey() {
  return (
    <div className="flex flex-col justify-center gap-4 border border-edge bg-surface px-6 py-6">
      <div className="flex flex-col gap-1">
        <h3 className="flex items-center gap-2.5 text-title font-medium text-ink">
          <span aria-hidden className="inline-block h-3.5 w-px shrink-0" style={{ background: "var(--xp-teal)" }} />
          How the rating works
        </h3>
        <p className="text-body text-muted">
          Six activity signals become six football stats. The overall (out of 99) is a weighted
          blend; raw ratings cap at 88 — the 90s (icon) need sustained output and a live streak.
        </p>
      </div>
      <dl className="grid grid-cols-1 gap-x-8 gap-y-2.5 sm:grid-cols-2">
        {STAT_META.map((m) => (
          <div key={m.key} className="flex items-baseline gap-3 border-t border-edge pt-2.5">
            <dt className="w-10 shrink-0 font-mono text-title font-medium" style={{ color: "var(--xp-amber)" }}>
              {m.label}
            </dt>
            <dd className="text-body text-muted">{m.source}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
