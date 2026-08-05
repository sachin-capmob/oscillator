"use client";

// The "i" trigger + popup that answers "how was this score calculated?" —
// pulls the raw points_events ledger for one actor and renders each row as
// the label combination that produced it (e.g. type:infra + size:m → 7),
// award/reversal/bonus color-coded, summing to the same total shown beside
// the trigger.

import { useEffect, useState } from "react";

import { fetchPointsLedger } from "@/lib/api";
import { EmptyState, ErrorState, LoadingPanel, Modal } from "@/components/ui";
import type { PointsLedgerEntry, Range } from "@/lib/types";

function labelsFor(entry: PointsLedgerEntry): string[] {
  const raw = entry.label_state;
  if (Array.isArray(raw)) return raw;
  if (raw && typeof raw === "object") return Object.keys(raw);
  return [];
}

const KIND_COLOR: Record<string, string> = {
  award: "var(--xp-teal, var(--signal))",
  bonus: "var(--xp-amber)",
  reversal: "var(--negative)",
};

const KIND_LABEL: Record<string, string> = {
  award: "awarded",
  bonus: "bonus",
  reversal: "reverted",
};

function EntryRow({ entry }: { entry: PointsLedgerEntry }) {
  const labels = labelsFor(entry);
  const color = KIND_COLOR[entry.event_kind] ?? "var(--ink)";
  return (
    <div className="flex items-start gap-4 border-b border-edge px-6 py-4 last:border-b-0">
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex items-center gap-2">
          {entry.identifier && (
            <span
              className="shrink-0 rounded px-1.5 py-0.5 font-mono text-[11px] font-medium"
              style={{ background: "rgba(var(--signal-rgb), 0.12)", color: "var(--signal)" }}
            >
              {entry.identifier}
            </span>
          )}
          <span className="truncate text-body text-ink">{entry.title ?? "(untitled)"}</span>
        </div>
        {labels.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            {labels.map((label, i) => (
              <span key={label} className="flex items-center gap-1.5">
                {i > 0 && <span className="text-[11px] text-muted">+</span>}
                <span
                  className="rounded px-1.5 py-0.5 text-[10px] font-medium"
                  style={{ background: "var(--edge)", color: "var(--muted)" }}
                >
                  {label}
                </span>
              </span>
            ))}
          </div>
        )}
        {/* rule_key already encodes the category (e.g. "bug_fix:infra:critical",
            "infra:size:m", "flat:review") — show it alone rather than
            repeating the category name twice. */}
        <span className="font-mono text-[11px] text-muted">
          {entry.rule_key ?? entry.category}
        </span>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        <span className="font-mono text-body font-medium" style={{ color }}>
          {entry.points > 0 ? "+" : ""}
          {entry.points}
        </span>
        <span className="font-mono text-[10px] uppercase tracking-eyebrow text-muted">
          {KIND_LABEL[entry.event_kind] ?? entry.event_kind}
        </span>
      </div>
    </div>
  );
}

function BreakdownBody({
  actorId,
  range,
  anchor,
}: {
  actorId: number;
  range: Range;
  anchor?: string;
}) {
  const [entries, setEntries] = useState<PointsLedgerEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setEntries(null);
    setError(null);
    fetchPointsLedger(actorId, range, anchor)
      .then((d) => alive && setEntries(d.entries))
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, [actorId, range, anchor]);

  if (error) {
    return (
      <div className="p-6">
        <ErrorState message={error} />
      </div>
    );
  }
  if (entries === null) {
    return (
      <div className="p-6">
        <LoadingPanel height="h-40" />
      </div>
    );
  }
  if (entries.length === 0) {
    return <EmptyState message="No scored tickets in this range yet." />;
  }

  const total = entries.reduce((s, e) => s + e.points, 0);
  // Oldest first, so the ledger reads top-to-bottom as "how the total built up".
  const ordered = [...entries].sort((a, b) => a.effective_at.localeCompare(b.effective_at));

  return (
    <div className="flex flex-col">
      {ordered.map((entry) => (
        <EntryRow key={entry.id} entry={entry} />
      ))}
      <div className="flex items-center justify-between border-t border-edge px-6 py-4">
        <span className="font-mono text-[11px] uppercase tracking-eyebrow text-muted">Total</span>
        <span className="font-mono text-title font-medium" style={{ color: "var(--xp-amber)" }}>
          {total}
        </span>
      </div>
    </div>
  );
}

/** Small "i" info button — click opens a popup breaking down exactly which
 * label combinations on which tickets add up to this person's score. */
export function PointsBreakdownButton({
  actorId,
  name,
  range,
  anchor,
}: {
  actorId: number;
  name: string;
  range: Range;
  anchor?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen(true);
        }}
        aria-label={`How ${name}'s score is calculated`}
        title="How is this calculated?"
        className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-edge text-[10px] leading-none text-muted hover:border-signal hover:text-ink"
      >
        i
      </button>
      {open && (
        <Modal
          title={`How ${name}'s score is calculated`}
          subtitle="Each ticket's labels at the moment it was scored, and the points they resolved to."
          onClose={() => setOpen(false)}
        >
          <BreakdownBody actorId={actorId} range={range} anchor={anchor} />
        </Modal>
      )}
    </>
  );
}
