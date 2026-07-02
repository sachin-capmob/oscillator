"use client";

// Narrative digest banner + "Attention" anomaly panel. Both read from the
// derived-analytics endpoints (/digest, /anomalies) produced by the cron sync.
// Styling stays on the CADENCE six-token system: --signal for the accent,
// --negative reserved for critical flags.

import { useInsight } from "@/lib/api";
import { useRange } from "@/components/shell";
import { Eyebrow, Panel } from "@/components/ui";
import type { AnomaliesResp, AnomalyItem, DigestResp } from "@/lib/types";

const METRIC_LABEL: Record<string, string> = {
  throughput: "Throughput",
  cycle_time: "Cycle time",
  wip: "WIP",
  net_flow: "Net flow",
  created: "Created",
  comments: "Comments",
};

function metricLabel(m: string): string {
  return METRIC_LABEL[m] ?? m.replace(/_/g, " ");
}

/* -------------------------------------------------------------------------- */
/* Digest banner — a single narrative paragraph above the KPI row.            */
/* -------------------------------------------------------------------------- */
export function DigestBanner() {
  const { range, anchor } = useRange();
  const { data, loading } = useInsight<DigestResp>("digest", range, anchor);

  // Nothing generated yet (pre-first-sync) → render nothing, don't nag.
  if (!loading && (!data || !data.available)) return null;

  return (
    <div className="relative flex flex-col gap-2.5 border border-edge bg-surface px-6 py-5">
      {loading && <div className="loadbar" aria-hidden />}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <span
            aria-hidden
            className="inline-block h-3 w-px shrink-0"
            style={{ background: "var(--signal)" }}
          />
          <Eyebrow>Digest</Eyebrow>
        </div>
        {data && (
          <span className="font-mono text-[11px] text-muted">
            {data.source === "groq" ? data.model ?? "groq" : "auto-summary"}
          </span>
        )}
      </div>
      <p className="text-body leading-relaxed text-ink">
        {loading ? "Summarizing this period…" : data?.summary}
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Attention panel — ranked list of flagged anomalies for the period.         */
/* -------------------------------------------------------------------------- */
export function AttentionPanel() {
  const { range, anchor } = useRange();
  const { data, loading } = useInsight<AnomaliesResp>("anomalies", range, anchor);

  const items = data?.anomalies ?? [];

  // Hide entirely when there is nothing to flag — the absence is the signal.
  if (!loading && items.length === 0) return null;

  return (
    <Panel
      loading={loading}
      eyebrow="Attention"
      title="Anomalies"
      subtitle={`${items.length} flagged vs. recent baselines`}
      bodyClassName="p-0"
    >
      <div className="flex flex-col">
        {items.map((a, i) => (
          <AnomalyRow key={`${a.scope}-${a.entity_id}-${a.metric}-${i}`} a={a} />
        ))}
      </div>
    </Panel>
  );
}

function AnomalyRow({ a }: { a: AnomalyItem }) {
  const critical = a.severity === "critical";
  const color = critical ? "var(--negative)" : "var(--signal)";
  const arrow = a.direction === "up" ? "▲" : "▼";
  const who = a.entity_name ?? (a.scope === "workspace" ? "Workspace" : a.scope);
  const deltaPct =
    a.baseline !== 0 ? Math.round(((a.observed - a.baseline) / a.baseline) * 100) : null;

  return (
    <div className="flex items-center gap-4 border-b border-edge px-6 py-4 last:border-b-0">
      <span
        aria-hidden
        className="inline-block h-8 w-0.5 shrink-0"
        style={{ background: color, opacity: critical ? 1 : 0.6 }}
      />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex items-center gap-2">
          <span className="truncate text-body text-ink">{who}</span>
          <span className="font-mono text-[11px] uppercase tracking-eyebrow text-muted">
            {a.scope}
          </span>
        </div>
        <span className="text-body text-muted">
          {metricLabel(a.metric)} {a.direction === "up" ? "rose" : "fell"} to{" "}
          <span className="font-mono text-ink">{a.observed}</span> (baseline{" "}
          <span className="font-mono">{a.baseline}</span>)
        </span>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-0.5">
        <span className="font-mono text-body" style={{ color }}>
          {arrow} {deltaPct !== null ? `${deltaPct > 0 ? "+" : ""}${deltaPct}%` : `${a.observed}`}
        </span>
        <span className="font-mono text-[11px] text-muted">z {a.z_score}</span>
      </div>
    </div>
  );
}
