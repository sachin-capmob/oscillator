"use client";

import { useCallback, useEffect, useState } from "react";
import { useRange } from "@/components/shell";
import { Segmented } from "@/components/segmented";
import { EmptyState, ErrorState, Eyebrow, LoadingPanel, Panel, Section } from "@/components/ui";
import type { ActorDropdown, CustomIssue, CustomIssueListResp, CustomIssueStatus } from "@/lib/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STATUS_OPTIONS: { value: CustomIssueStatus; label: string }[] = [
  { value: "unstarted", label: "Unstarted" },
  { value: "started", label: "In progress" },
  { value: "completed", label: "Completed" },
  { value: "canceled", label: "Canceled" },
];

function statusLabel(s: CustomIssueStatus): string {
  return STATUS_OPTIONS.find((o) => o.value === s)?.label ?? s;
}

function statusColor(s: CustomIssueStatus): string {
  switch (s) {
    case "completed":
      return "var(--signal)";
    case "canceled":
      return "var(--negative)";
    case "started":
      return "var(--ink)";
    default:
      return "var(--muted)";
  }
}

function assigneeLabel(i: Pick<CustomIssue, "assignee_name" | "assignee_email" | "assignee_id">): string {
  if (i.assignee_name) return i.assignee_name;
  if (i.assignee_email) return i.assignee_email;
  return i.assignee_id != null ? `Actor ${i.assignee_id}` : "Unassigned";
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// ---------------------------------------------------------------------------
// API helpers (talk to the /api/custom-issues/* Next.js proxy)
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`/api/custom-issues/${path}`, {
    headers: { "content-type": "application/json" },
    cache: "no-store",
    ...opts,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail ?? `Request failed (${res.status})`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Create issue form
// ---------------------------------------------------------------------------
function CreateIssuePanel({
  actors,
  onCreated,
}: {
  actors: ActorDropdown[];
  onCreated: () => void;
}) {
  const [title, setTitle] = useState("");
  const [assigneeId, setAssigneeId] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate() {
    if (!title.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch("create", {
        method: "POST",
        body: JSON.stringify({
          title: title.trim(),
          assignee_id: assigneeId === "" ? null : assigneeId,
          status: "unstarted",
        }),
      });
      setTitle("");
      setAssigneeId("");
      onCreated();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6 border border-edge bg-surface px-8 py-8">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:gap-4">
        <div className="flex flex-1 flex-col gap-2">
          <Eyebrow>What needs tracking?</Eyebrow>
          <input
            id="issue-title-input"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Set up AWS account"
            className="rounded border border-edge bg-void px-4 py-2.5 text-body text-ink placeholder:text-muted focus:outline-none focus:ring-1"
            style={{ fontSize: "14px" }}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleCreate();
            }}
          />
        </div>

        <div className="flex w-full flex-col gap-2 sm:w-56">
          <Eyebrow>Assignee</Eyebrow>
          <div className="relative">
            <select
              id="issue-assignee-select"
              value={assigneeId}
              onChange={(e) => setAssigneeId(e.target.value === "" ? "" : Number(e.target.value))}
              className="w-full appearance-none rounded border border-edge bg-void py-2.5 pl-4 pr-9 text-body text-ink focus:outline-none"
              style={{ fontSize: "14px" }}
            >
              <option value="">Unassigned</option>
              {actors.map((a) => (
                <option key={a.actor_id} value={a.actor_id}>
                  {a.name ?? a.email ?? `Actor ${a.actor_id}`}
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

        <button
          id="issue-create-btn"
          onClick={handleCreate}
          disabled={busy || !title.trim()}
          className="rounded px-6 py-2.5 text-[14px] font-semibold tracking-wide transition-all disabled:cursor-not-allowed disabled:opacity-50"
          style={{ background: "var(--signal)", color: "#fff" }}
        >
          {busy ? "Creating…" : "Create"}
        </button>
      </div>

      {error && (
        <p className="text-[12px]" style={{ color: "var(--negative)" }}>
          {error}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Issue row — inline update / complete / delete
// ---------------------------------------------------------------------------
function IssueRow({
  issue,
  actors,
  even,
  onChanged,
}: {
  issue: CustomIssue;
  actors: ActorDropdown[];
  even: boolean;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);

  async function patch(body: Record<string, unknown>) {
    setBusy(true);
    try {
      await apiFetch(`${issue.id}`, { method: "PATCH", body: JSON.stringify(body) });
      onChanged();
    } catch {
      // surfaced via the panel-level refresh; keep the row responsive
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    setBusy(true);
    try {
      await apiFetch(`${issue.id}`, { method: "DELETE" });
      onChanged();
    } catch {
      setBusy(false);
    }
  }

  return (
    <div
      className="flex flex-col gap-3 border-b border-edge px-6 py-4 last:border-b-0 sm:flex-row sm:items-center sm:gap-4"
      style={{ background: even ? "var(--surface)" : "var(--void)", opacity: busy ? 0.5 : 1 }}
    >
      {/* Identifier + title */}
      <div className="flex min-w-0 flex-1 items-center gap-3">
        {issue.identifier && (
          <span
            className="shrink-0 rounded px-2 py-0.5 font-mono text-[11px] font-medium"
            style={{ background: "rgba(var(--signal-rgb), 0.12)", color: "var(--signal)" }}
          >
            {issue.identifier}
          </span>
        )}
        <span className="truncate text-body text-ink">{issue.title}</span>
      </div>

      {/* Assignee dropdown */}
      <div className="relative shrink-0">
        <select
          disabled={busy}
          value={issue.assignee_id ?? ""}
          onChange={(e) => patch({ assignee_id: e.target.value === "" ? null : Number(e.target.value) })}
          className="w-40 appearance-none rounded border border-edge bg-void py-1.5 pl-3 pr-7 text-[12px] text-ink focus:outline-none disabled:opacity-50"
        >
          <option value="">Unassigned</option>
          {actors.map((a) => (
            <option key={a.actor_id} value={a.actor_id}>
              {a.name ?? a.email ?? `Actor ${a.actor_id}`}
            </option>
          ))}
        </select>
        <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2" aria-hidden>
          <svg width="9" height="5" viewBox="0 0 10 6" fill="none">
            <path d="M1 1l4 4 4-4" stroke="var(--muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </div>

      {/* Status dropdown */}
      <div className="relative shrink-0">
        <select
          disabled={busy}
          value={issue.status}
          onChange={(e) => patch({ status: e.target.value })}
          className="w-36 appearance-none rounded border border-edge bg-void py-1.5 pl-3 pr-7 text-[12px] focus:outline-none disabled:opacity-50"
          style={{ color: statusColor(issue.status) }}
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2" aria-hidden>
          <svg width="9" height="5" viewBox="0 0 10 6" fill="none">
            <path d="M1 1l4 4 4-4" stroke="var(--muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </div>

      {/* Dates */}
      <span className="shrink-0 font-mono text-[11px] text-muted" style={{ minWidth: "72px" }}>
        {issue.status === "completed" ? fmtDate(issue.completed_at) : fmtDate(issue.created_at)}
      </span>

      {/* Complete shortcut + delete */}
      <div className="flex shrink-0 items-center gap-2">
        {issue.status !== "completed" && (
          <button
            disabled={busy}
            onClick={() => patch({ status: "completed" })}
            className="rounded border border-edge px-2.5 py-1 text-[11px] text-ink transition-colors hover:bg-edge disabled:cursor-not-allowed disabled:opacity-40"
          >
            Complete
          </button>
        )}
        <button
          disabled={busy}
          onClick={handleDelete}
          aria-label="Delete issue"
          className="rounded border border-edge px-2.5 py-1 text-[11px] transition-colors hover:bg-edge disabled:cursor-not-allowed disabled:opacity-40"
          style={{ color: "var(--negative)" }}
        >
          Delete
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function IssuesPage() {
  const { refreshKey } = useRange();

  const [actors, setActors] = useState<ActorDropdown[]>([]);
  const [issues, setIssues] = useState<CustomIssue[]>([]);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<ActorDropdown[]>("actors")
      .then(setActors)
      .catch(() => setActors([]));
  }, []);

  const fetchIssues = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = statusFilter === "all" ? "" : `?status=${statusFilter}`;
      const data = await apiFetch<CustomIssueListResp>(`list${qs}`);
      setIssues(data.issues);
      setTotal(data.total);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchIssues();
  }, [fetchIssues, refreshKey]);

  return (
    <div className="flex flex-col gap-12">
      <Section
        title="Issues"
        description="Track work that doesn't live in Linear — e.g. setting up AWS. Counts toward throughput, WIP, and per-person/team tallies everywhere else in the dashboard."
      >
        <CreateIssuePanel actors={actors} onCreated={fetchIssues} />
      </Section>

      <Section title="All custom issues" description={`${total} issue${total !== 1 ? "s" : ""} tracked`}>
        <Panel
          loading={loading}
          eyebrow="Filter"
          title="Custom issue log"
          action={
            <Segmented
              options={[{ value: "all", label: "All" }, ...STATUS_OPTIONS]}
              value={statusFilter}
              onChange={setStatusFilter}
            />
          }
          bodyClassName="p-0"
        >
          {error ? (
            <div className="p-6">
              <ErrorState message={error} />
            </div>
          ) : loading ? (
            <div className="p-6">
              <LoadingPanel height="h-64" />
            </div>
          ) : issues.length === 0 ? (
            <EmptyState message="No custom issues yet. Create one above." />
          ) : (
            <div className="flex flex-col">
              {issues.map((issue, i) => (
                <IssueRow
                  key={issue.id}
                  issue={issue}
                  actors={actors}
                  even={i % 2 === 0}
                  onChanged={fetchIssues}
                />
              ))}
            </div>
          )}
        </Panel>
      </Section>
    </div>
  );
}
