"use client";

// Client-side data access. Requests go to the same-origin Next.js proxy
// (app/api/insights/[...path]/route.ts), which injects the bearer token
// server-side — the token is never exposed to the browser.

import { useEffect, useState } from "react";

import type { Range } from "./types";

export async function fetchInsight<T>(
  path: string,
  range: Range,
  anchor?: string,
): Promise<T> {
  const qs = new URLSearchParams({ range });
  if (anchor) qs.set("anchor", anchor);
  const res = await fetch(`/api/insights/${path}?${qs.toString()}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Request to ${path} failed (${res.status})`);
  }
  return (await res.json()) as T;
}

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

/** Fetch an insights endpoint, re-fetching whenever range, anchor, or refreshKey changes. */
export function useInsight<T>(path: string, range: Range, anchor?: string, refreshKey?: number): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    fetchInsight<T>(path, range, anchor)
      .then((d) => alive && (setData(d), setLoading(false)))
      .catch((e) => alive && (setError(String(e)), setLoading(false)));
    return () => {
      alive = false;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, range, anchor, refreshKey]);

  return { data, loading, error };
}

/** Fetch issues closed by a specific actor in the selected range. */
export async function fetchActorIssues(
  actorId: number,
  range: Range,
  anchor?: string,
) {
  const qs = new URLSearchParams({ actor_id: String(actorId), range });
  if (anchor) qs.set("anchor", anchor);
  const res = await fetch(`/api/insights/actor-issues?${qs.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`actor-issues failed (${res.status})`);
  return res.json();
}
