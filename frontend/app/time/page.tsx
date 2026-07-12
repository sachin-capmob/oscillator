"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRange } from "@/components/shell";
import { EmptyState, Eyebrow, LoadingPanel, Panel, Section } from "@/components/ui";
import type {
  ActorDropdown,
  ActiveTimerResp,
  TimeEntry,
  TimeLogResp,
  TimeSummaryItem,
  TimeSummaryResp,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtDuration(secs: number): string {
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}h ${m.toString().padStart(2, "0")}m`;
  if (m > 0) return `${m}m ${s.toString().padStart(2, "0")}s`;
  return `${s}s`;
}

function fmtHHMMSS(secs: number): string {
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  return [h, m, s].map((v) => v.toString().padStart(2, "0")).join(":");
}

function fmtDatetime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function actorLabel(a: Pick<ActorDropdown, "name" | "email" | "actor_id">): string {
  return a.name ?? a.email ?? `Actor ${a.actor_id}`;
}

// ---------------------------------------------------------------------------
// API helpers (talk to the /api/time/* Next.js proxy)
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`/api/time/${path}`, {
    headers: { "content-type": "application/json" },
    cache: "no-store",
    ...opts,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail ?? `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Live elapsed clock — ticks every second
// ---------------------------------------------------------------------------
function useElapsed(startedAt: string | null): number {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!startedAt) { setElapsed(0); return; }
    const tick = () =>
      setElapsed(Math.max(0, Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000)));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [startedAt]);
  return elapsed;
}

// ---------------------------------------------------------------------------
// Timer display widget
// ---------------------------------------------------------------------------
function ClockDisplay({ startedAt }: { startedAt: string }) {
  const elapsed = useElapsed(startedAt);
  return (
    <div className="flex flex-col items-center gap-1">
      <span
        className="font-mono text-[56px] font-semibold leading-none tabular-nums"
        style={{ color: "var(--signal)", letterSpacing: "-0.02em" }}
      >
        {fmtHHMMSS(elapsed)}
      </span>
      <span className="text-[11px] tracking-widest text-muted uppercase">elapsed</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Clock-in / clock-out panel
// ---------------------------------------------------------------------------
function TimerPanel({
  actors,
  onUpdate,
}: {
  actors: ActorDropdown[];
  onUpdate: () => void;
}) {
  const [selectedId, setSelectedId] = useState<number | null>(
    actors.length > 0 ? actors[0].actor_id : null,
  );
  const [activeEntry, setActiveEntry] = useState<TimeEntry | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Update dropdown selected id when actor list arrives
  useEffect(() => {
    if (actors.length > 0 && selectedId === null) setSelectedId(actors[0].actor_id);
  }, [actors, selectedId]);

  // Fetch active timer whenever actor changes
  const fetchActive = useCallback(async (actorId: number) => {
    try {
      const resp = await apiFetch<ActiveTimerResp>(`active?actor_id=${actorId}`);
      setActiveEntry(resp.entry);
    } catch {
      setActiveEntry(null);
    }
  }, []);

  useEffect(() => {
    if (selectedId === null) return;
    fetchActive(selectedId);
    // Poll every 15s to catch timers started on another device/tab.
    pollRef.current = setInterval(() => fetchActive(selectedId), 15_000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [selectedId, fetchActive]);

  async function handleStart() {
    if (selectedId === null) return;
    setBusy(true);
    setError(null);
    try {
      const entry = await apiFetch<TimeEntry>("start", {
        method: "POST",
        body: JSON.stringify({ actor_id: selectedId, note: note || null }),
      });
      setActiveEntry(entry);
      setNote("");
      onUpdate();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleStop() {
    if (!activeEntry) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`stop/${activeEntry.id}`, {
        method: "POST",
        body: JSON.stringify({ note: note || null }),
      });
      setActiveEntry(null);
      setNote("");
      onUpdate();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const isRunning = activeEntry !== null;
  const selectedActor = actors.find((a) => a.actor_id === selectedId);

  return (
    <div
      className="relative flex flex-col items-center gap-8 rounded-none border border-edge bg-surface px-8 py-10"
      style={{ boxShadow: isRunning ? `0 0 0 1px var(--signal)` : undefined }}
    >
      {/* Running pulse ring */}
      {isRunning && (
        <span
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            borderRadius: "inherit",
            boxShadow: "0 0 24px 0 rgba(var(--signal-rgb), 0.18)",
          }}
        />
      )}

      {/* Person selector */}
      <div className="flex w-full max-w-sm flex-col gap-2">
        <Eyebrow>Who&apos;s clocking {isRunning ? "out" : "in"}?</Eyebrow>
        <div className="relative">
          <select
            id="time-actor-select"
            disabled={isRunning || busy}
            value={selectedId ?? ""}
            onChange={(e) => setSelectedId(Number(e.target.value))}
            className="w-full appearance-none rounded border border-edge bg-void py-2.5 pl-4 pr-9 text-body text-ink focus:outline-none disabled:opacity-50"
            style={{ fontSize: "14px" }}
          >
            {actors.map((a) => (
              <option key={a.actor_id} value={a.actor_id}>
                {actorLabel(a)}
              </option>
            ))}
          </select>
          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2" aria-hidden>
            <svg width="10" height="6" viewBox="0 0 10 6" fill="none">
              <path d="M1 1l4 4 4-4" stroke="var(--muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        </div>
      </div>

      {/* Big clock when running */}
      {isRunning && activeEntry && (
        <div className="flex flex-col items-center gap-1">
          <ClockDisplay startedAt={activeEntry.started_at} />
          <span className="mt-1 text-[12px] text-muted">
            started {fmtDatetime(activeEntry.started_at)}
          </span>
        </div>
      )}

      {/* Note field */}
      <div className="flex w-full max-w-sm flex-col gap-2">
        <Eyebrow>Note (optional)</Eyebrow>
        <input
          id="time-note-input"
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder={isRunning ? "Add a note when stopping…" : "What are you working on?"}
          className="rounded border border-edge bg-void px-4 py-2.5 text-body text-ink placeholder:text-muted focus:outline-none focus:ring-1"
          style={{ fontSize: "14px" }}
          onKeyDown={(e) => {
            if (e.key === "Enter") isRunning ? handleStop() : handleStart();
          }}
        />
      </div>

      {/* Start / Stop button */}
      <button
        id={isRunning ? "time-stop-btn" : "time-start-btn"}
        onClick={isRunning ? handleStop : handleStart}
        disabled={busy || selectedId === null}
        className="flex items-center gap-3 rounded px-8 py-3 text-[14px] font-semibold tracking-wide transition-all disabled:cursor-not-allowed disabled:opacity-50"
        style={{
          background: isRunning ? "var(--negative)" : "var(--signal)",
          color: "#fff",
          minWidth: "180px",
          justifyContent: "center",
        }}
      >
        {busy ? (
          <>
            <SpinIcon />
            {isRunning ? "Stopping…" : "Starting…"}
          </>
        ) : isRunning ? (
          <>
            <StopIcon />
            Stop timer
          </>
        ) : (
          <>
            <PlayIcon />
            Start timer
          </>
        )}
      </button>

      {error && (
        <p className="max-w-sm text-center text-[12px]" style={{ color: "var(--negative)" }}>
          {error}
        </p>
      )}

      {!isRunning && selectedActor && (
        <p className="text-[11px] text-muted">
          {actorLabel(selectedActor)} · idle
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Session log table
// ---------------------------------------------------------------------------
function SessionLogPanel({
  entries,
  total,
  loading,
  page,
  onPage,
}: {
  entries: TimeEntry[];
  total: number;
  loading: boolean;
  page: number;
  onPage: (p: number) => void;
}) {
  const PAGE_SIZE = 20;
  const pages = Math.ceil(total / PAGE_SIZE);

  return (
    <Panel
      loading={loading}
      eyebrow="Log"
      title="Session history"
      subtitle={`${total} session${total !== 1 ? "s" : ""} logged`}
      bodyClassName="p-0"
    >
      {loading ? (
        <div className="p-6">
          <LoadingPanel height="h-64" />
        </div>
      ) : entries.length === 0 ? (
        <EmptyState message="No sessions logged yet. Start a timer above!" />
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-edge">
                  <LogTh align="left">Person</LogTh>
                  <LogTh align="left">Started</LogTh>
                  <LogTh align="left">Stopped</LogTh>
                  <LogTh align="right">Duration</LogTh>
                  <LogTh align="left">Note</LogTh>
                </tr>
              </thead>
              <tbody>
                {entries.map((e, i) => (
                  <tr
                    key={e.id}
                    className="border-b border-edge last:border-b-0"
                    style={{ background: i % 2 === 0 ? "var(--surface)" : "var(--void)" }}
                  >
                    <td className="px-6 py-3 text-body text-ink">
                      {e.actor_name ?? e.actor_email ?? `Actor ${e.actor_id}`}
                    </td>
                    <td className="px-6 py-3 font-mono text-[12px] text-muted">
                      {fmtDatetime(e.started_at)}
                    </td>
                    <td className="px-6 py-3 font-mono text-[12px] text-muted">
                      {e.stopped_at ? fmtDatetime(e.stopped_at) : (
                        <span style={{ color: "var(--signal)" }}>running…</span>
                      )}
                    </td>
                    <td className="px-6 py-3 text-right font-mono text-body text-ink">
                      {e.duration_secs != null ? fmtDuration(e.duration_secs) : "—"}
                    </td>
                    <td className="max-w-[220px] truncate px-6 py-3 text-body text-muted">
                      {e.note ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {pages > 1 && (
            <div className="flex items-center justify-between border-t border-edge px-6 py-3">
              <span className="text-[12px] text-muted">
                Page {page + 1} of {pages}
              </span>
              <div className="flex gap-2">
                <PageBtn disabled={page === 0} onClick={() => onPage(page - 1)}>← Prev</PageBtn>
                <PageBtn disabled={page >= pages - 1} onClick={() => onPage(page + 1)}>Next →</PageBtn>
              </div>
            </div>
          )}
        </>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Summary leaderboard
// ---------------------------------------------------------------------------
function SummaryPanel({ items, loading }: { items: TimeSummaryItem[]; loading: boolean }) {
  if (!loading && items.length === 0) return null;
  const maxSecs = Math.max(1, ...items.map((i) => i.total_secs));

  return (
    <Panel
      loading={loading}
      eyebrow="Summary"
      title="Time logged by person"
      subtitle="All-time totals from completed sessions"
      bodyClassName="p-0"
    >
      {loading ? (
        <div className="p-6"><LoadingPanel height="h-32" /></div>
      ) : (
        <div className="flex flex-col">
          {items.map((item, i) => {
            const name = item.actor_name ?? item.actor_email ?? `Actor ${item.actor_id}`;
            const pct = (item.total_secs / maxSecs) * 100;
            return (
              <div
                key={item.actor_id}
                className="relative flex items-center justify-between border-b border-edge px-6 py-3.5 last:border-b-0"
              >
                <span
                  aria-hidden
                  className="absolute inset-y-0 left-0 z-0 transition-all"
                  style={{ width: `${pct}%`, background: "rgba(var(--signal-rgb), 0.08)" }}
                />
                <span className="relative z-10 text-body text-ink">{name}</span>
                <div className="relative z-10 flex items-center gap-4">
                  <span className="font-mono text-[11px] text-muted">
                    {item.session_count} session{item.session_count !== 1 ? "s" : ""}
                  </span>
                  <span className="min-w-[64px] text-right font-mono text-body text-ink">
                    {fmtDuration(item.total_secs)}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
const PAGE_SIZE = 20;

export default function TimePage() {
  const { refreshKey } = useRange();

  const [actors, setActors] = useState<ActorDropdown[]>([]);
  const [actorsLoading, setActorsLoading] = useState(true);

  const [entries, setEntries] = useState<TimeEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [logLoading, setLogLoading] = useState(true);
  const [page, setPage] = useState(0);

  const [summary, setSummary] = useState<TimeSummaryItem[]>([]);
  const [summaryLoading, setSummaryLoading] = useState(true);

  // Load actors once
  useEffect(() => {
    setActorsLoading(true);
    apiFetch<ActorDropdown[]>("actors")
      .then(setActors)
      .catch(() => setActors([]))
      .finally(() => setActorsLoading(false));
  }, []);

  // Load log
  const fetchLog = useCallback(async (p: number) => {
    setLogLoading(true);
    try {
      const data = await apiFetch<TimeLogResp>(
        `entries?limit=${PAGE_SIZE}&offset=${p * PAGE_SIZE}`
      );
      setEntries(data.entries);
      setTotal(data.total);
    } catch {
      setEntries([]);
    } finally {
      setLogLoading(false);
    }
  }, []);

  // Load summary
  const fetchSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const data = await apiFetch<TimeSummaryResp>("summary");
      setSummary(data.items);
    } catch {
      setSummary([]);
    } finally {
      setSummaryLoading(false);
    }
  }, []);

  useEffect(() => { fetchLog(page); }, [page, fetchLog, refreshKey]);
  useEffect(() => { fetchSummary(); }, [fetchSummary, refreshKey]);

  function handleUpdate() {
    fetchLog(page);
    fetchSummary();
  }

  return (
    <div className="flex flex-col gap-12">
      <Section
        title="Time Tracker"
        description="Clock in and out for any team member. Sessions are stored in the database and shown below."
      >
        {actorsLoading ? (
          <div className="border border-edge bg-surface p-10">
            <LoadingPanel height="h-40" />
          </div>
        ) : actors.length === 0 ? (
          <div className="border border-edge bg-surface p-10">
            <EmptyState message="No team members found. Run a Linear sync first." />
          </div>
        ) : (
          <TimerPanel actors={actors} onUpdate={handleUpdate} />
        )}
      </Section>

      {/* All-time summary */}
      <Section
        title="Time summary"
        description="Total hours logged per person across all sessions."
      >
        <SummaryPanel items={summary} loading={summaryLoading} />
      </Section>

      {/* Full session log */}
      <Section
        title="Session log"
        description="Every completed clock-in / clock-out session, most recent first."
      >
        <SessionLogPanel
          entries={entries}
          total={total}
          loading={logLoading}
          page={page}
          onPage={(p) => { setPage(p); }}
        />
      </Section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Small reusable atoms
// ---------------------------------------------------------------------------
function LogTh({ children, align }: { children: React.ReactNode; align: "left" | "right" }) {
  return (
    <th className={`px-6 py-3.5 ${align === "right" ? "text-right" : "text-left"}`}>
      <Eyebrow>{children}</Eyebrow>
    </th>
  );
}

function PageBtn({
  children,
  disabled,
  onClick,
}: {
  children: React.ReactNode;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="rounded border border-edge px-3 py-1 text-[12px] text-ink transition-colors hover:bg-edge disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  );
}

function PlayIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
      <path d="M3 2l11 6-11 6V2z" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
      <rect x="3" y="3" width="10" height="10" rx="1" />
    </svg>
  );
}

function SpinIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="currentColor"
      style={{ animation: "spin 0.8s linear infinite" }}
    >
      <path d="M13.65 2.35A8 8 0 1 0 15 8h-2a6 6 0 1 1-1.05-3.39L9 7h6V1l-1.35 1.35Z" />
    </svg>
  );
}
