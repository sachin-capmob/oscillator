"use client";

// Plain, print-ready Engineering Activity Report. Deliberately NOT styled
// like the rest of the dashboard — no gradients, animated bars, or
// gamification chrome. It exists to answer one question on paper: who did
// what, worth how many points, in exactly the period currently selected.
// Reads the same shared range/anchor as every other page (components/shell)
// so "download while Week is selected" reports on that week, nothing else.

import { useEffect, useState } from "react";

import { useInsight } from "@/lib/api";
import { useRange } from "@/components/shell";
import type { ByActorResp, Overview, PointsByActorResp } from "@/lib/types";

function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function periodTitle(range: string): string {
  return { day: "Daily", week: "Weekly", month: "Monthly", all: "All-Time" }[range] ?? range;
}

interface Row {
  actorId: number;
  name: string;
  email: string | null;
  points: number;
  breakdown: string;
  throughput: number;
  avgCycle: number | null;
  created: number;
  comments: number;
}

export default function ReportPage() {
  const { range, anchor } = useRange();
  const overview = useInsight<Overview>("overview", range, anchor);
  const actors = useInsight<ByActorResp>("by-actor", range, anchor);
  const points = useInsight<PointsByActorResp>("points/by-actor", range, anchor);

  // Stamped client-side only, after mount — computing this during the
  // server render would produce a different value than the client's
  // hydration pass and trip a hydration-mismatch error.
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  useEffect(() => {
    setGeneratedAt(new Date().toISOString());
  }, []);

  const loading = overview.loading || actors.loading || points.loading;
  const error = overview.error || actors.error || points.error;

  const pointsByActor = new Map(points.data?.actors.map((a) => [a.actor_id, a]) ?? []);

  const rows: Row[] = (actors.data?.actors ?? [])
    .map((a) => {
      const p = pointsByActor.get(a.actor_id);
      const breakdown = (p?.by_category ?? [])
        .filter((c) => c.points !== 0)
        .sort((x, y) => y.points - x.points)
        .map((c) => `${c.category} ${c.points > 0 ? "+" : ""}${c.points}`)
        .join(", ");
      return {
        actorId: a.actor_id,
        name: a.name ?? a.email ?? `Actor ${a.actor_id}`,
        email: a.email,
        points: p?.total_points ?? 0,
        breakdown: breakdown || "—",
        throughput: a.throughput,
        avgCycle: a.avg_cycle_hours,
        created: a.created,
        comments: a.comments,
      };
    })
    .sort((x, y) => y.points - x.points);

  const totalPoints = rows.reduce((s, r) => s + r.points, 0);
  const totalThroughput = rows.reduce((s, r) => s + r.throughput, 0);

  const periodStart = overview.data?.period_start;
  const periodEnd = overview.data?.period_end;

  return (
    <div className="flex flex-col gap-6">
      {/* Controls — screen only, never printed */}
      <div className="no-print flex flex-col items-start gap-3 border border-edge bg-surface px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div>
          <p className="text-body text-ink">Engineering Activity Report</p>
          <p className="text-body text-muted">
            Uses the range currently selected above ({periodTitle(range)}). Change it there, then come back.
          </p>
        </div>
        <button
          type="button"
          onClick={() => window.print()}
          disabled={loading || !!error}
          className="shrink-0 border border-signal px-4 py-2 text-[13px] font-medium text-signal disabled:opacity-40"
        >
          Download PDF
        </button>
      </div>
      {error && (
        <div className="no-print border border-edge bg-surface px-6 py-4 text-body" style={{ color: "var(--negative)" }}>
          {error}
        </div>
      )}

      {/* The report itself — plain black-on-white, print-first */}
      <div
        className="report-page mx-auto w-full max-w-[820px] px-5 py-8 sm:px-12 sm:py-10"
        style={{ background: "#fff", color: "#111", fontFamily: "var(--font-sans)" }}
      >
        <div style={{ borderBottom: "2px solid #111", paddingBottom: 12, marginBottom: 20 }}>
          <h1 style={{ fontSize: 20, fontWeight: 600, margin: 0 }}>Engineering Activity Report</h1>
          <p style={{ fontSize: 13, color: "#555", margin: "4px 0 0" }}>
            {periodTitle(range)} report
            {periodStart && periodEnd ? ` · ${fmtDate(periodStart)} — ${fmtDate(periodEnd)}` : ""}
          </p>
          <p style={{ fontSize: 11, color: "#888", margin: "2px 0 0" }}>
            Generated {generatedAt ? fmtDateTime(generatedAt) : "—"}
          </p>
        </div>

        {loading ? (
          <p style={{ fontSize: 13, color: "#555" }}>Loading…</p>
        ) : (
          <>
            {/* Team summary */}
            <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 24, fontSize: 12 }}>
              <tbody>
                <SummaryRow label="Throughput (issues closed)" value={String(overview.data?.throughput.current ?? 0)} />
                <SummaryRow
                  label="Avg cycle time"
                  value={overview.data?.avg_cycle_hours.current != null ? `${overview.data.avg_cycle_hours.current}h` : "—"}
                />
                <SummaryRow label="Comments" value={String(overview.data?.comments.current ?? 0)} />
                <SummaryRow label="Work in progress" value={String(overview.data?.wip ?? 0)} />
                <SummaryRow label="Total Engineering Points awarded" value={String(totalPoints)} bold />
                <SummaryRow label="Active contributors" value={String(rows.length)} />
              </tbody>
            </table>

            {/* Leaderboard */}
            <h2 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 8px" }}>Leaderboard</h2>
            {/* Scrolls horizontally on a narrow screen rather than squeezing 8
                columns illegibly — harmless on a real print page, which is
                always wide enough for the table to fit at its natural width. */}
            <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", minWidth: 640, borderCollapse: "collapse", fontSize: 11.5 }}>
              <thead>
                <tr style={{ borderBottom: "1.5px solid #111" }}>
                  <Th align="left" style={{ width: 28 }}>#</Th>
                  <Th align="left">Name</Th>
                  <Th align="right">Points</Th>
                  <Th align="left">Points breakdown</Th>
                  <Th align="right">Closed</Th>
                  <Th align="right">Avg cycle</Th>
                  <Th align="right">Created</Th>
                  <Th align="right">Comments</Th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={8} style={{ padding: "16px 4px", color: "#888" }}>
                      No activity in this period.
                    </td>
                  </tr>
                ) : (
                  rows.map((r, i) => (
                    <tr key={r.actorId} className="report-row" style={{ borderBottom: "1px solid #ddd" }}>
                      <Td align="left">{i + 1}</Td>
                      <Td align="left">{r.name}</Td>
                      <Td align="right" bold>
                        {r.points}
                      </Td>
                      <Td align="left" style={{ color: "#555" }}>
                        {r.breakdown}
                      </Td>
                      <Td align="right">{r.throughput}</Td>
                      <Td align="right">{r.avgCycle != null ? `${r.avgCycle}h` : "—"}</Td>
                      <Td align="right">{r.created}</Td>
                      <Td align="right">{r.comments}</Td>
                    </tr>
                  ))
                )}
              </tbody>
              {rows.length > 0 && (
                <tfoot>
                  <tr style={{ borderTop: "1.5px solid #111" }}>
                    <Td align="left" bold colSpan={2}>
                      Total
                    </Td>
                    <Td align="right" bold>
                      {totalPoints}
                    </Td>
                    <Td align="left">—</Td>
                    <Td align="right" bold>
                      {totalThroughput}
                    </Td>
                    <Td align="right">—</Td>
                    <Td align="right">—</Td>
                    <Td align="right">—</Td>
                  </tr>
                </tfoot>
              )}
            </table>
            </div>

            <p style={{ fontSize: 10, color: "#999", marginTop: 24 }}>
              Points reflect labeled, closed Linear tickets scored against the team&rsquo;s Engineering Points
              rulebook as of the generation time above. Tickets awaiting required labels are not counted and
              are not included in this report.
            </p>
          </>
        )}
      </div>
    </div>
  );
}

function SummaryRow({ label, value, bold = false }: { label: string; value: string; bold?: boolean }) {
  return (
    <tr style={{ borderBottom: "1px solid #eee" }}>
      <td style={{ padding: "4px 0", color: "#555" }}>{label}</td>
      <td style={{ padding: "4px 0", textAlign: "right", fontWeight: bold ? 600 : 400 }}>{value}</td>
    </tr>
  );
}

function Th({
  children,
  align,
  style,
}: {
  children: React.ReactNode;
  align: "left" | "right";
  style?: React.CSSProperties;
}) {
  return (
    <th style={{ padding: "6px 4px", textAlign: align, fontWeight: 600, ...style }}>{children}</th>
  );
}

function Td({
  children,
  align,
  bold = false,
  colSpan,
  style,
}: {
  children: React.ReactNode;
  align: "left" | "right";
  bold?: boolean;
  colSpan?: number;
  style?: React.CSSProperties;
}) {
  return (
    <td
      colSpan={colSpan}
      style={{ padding: "5px 4px", textAlign: align, fontWeight: bold ? 600 : 400, ...style }}
    >
      {children}
    </td>
  );
}
