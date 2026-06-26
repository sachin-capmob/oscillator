"use client";

// OSCILLATOR's signature control: a waveform date scrubber. Each bar is a period
// (day / week / month) with height = throughput; click a bar — or use the ◀ ▶
// steppers — to focus the whole dashboard on that period. The right edge is "now";
// you cannot scrub into the future.

import { useMemo } from "react";

import { useInsight } from "@/lib/api";
import { useRange } from "@/components/shell";
import { periodLabel, relativeLabel } from "@/lib/dates";
import type { ThroughputResp } from "@/lib/types";

const VISIBLE: Record<string, number> = { day: 24, week: 12, month: 12 };

export function DateScrubber() {
  const { range, anchor, setAnchor } = useRange();
  // No anchor passed → a stable timeline that always ends at "now".
  const { data, loading } = useInsight<ThroughputResp>("throughput", range);

  const ticks = useMemo(() => {
    const series = data?.series ?? [];
    return series.slice(-VISIBLE[range]);
  }, [data, range]);

  const maxVal = useMemo(
    () => Math.max(1, ...ticks.map((t) => t.completed ?? 0)),
    [ticks],
  );

  // Index of the period that currently contains the anchor (last tick <= anchor).
  const selected = useMemo(() => {
    let idx = 0;
    ticks.forEach((t, i) => {
      if (t.period <= anchor) idx = i;
    });
    return idx;
  }, [ticks, anchor]);

  if (loading || ticks.length === 0) {
    return (
      <div className="flex h-[68px] items-end gap-[3px] rounded-tremor-default border border-tremor-border bg-tremor-background/50 px-3 py-2">
        {Array.from({ length: 24 }).map((_, i) => (
          <div
            key={i}
            className="flex-1 animate-pulse rounded-sm bg-tremor-background-subtle"
            style={{ height: `${10 + ((i * 7) % 30)}px` }}
          />
        ))}
      </div>
    );
  }

  const atNow = selected >= ticks.length - 1;
  const stepsFromNow = ticks.length - 1 - selected;
  const sel = ticks[selected];

  const go = (i: number) => setAnchor(ticks[Math.max(0, Math.min(ticks.length - 1, i))].period);

  return (
    <div className="flex items-stretch gap-3 rounded-tremor-default border border-tremor-border bg-tremor-background/50 px-3 py-2 shadow-tremor-card backdrop-blur">
      {/* Readout */}
      <div className="flex min-w-[150px] flex-col justify-center font-mono">
        <span className="text-[11px] uppercase tracking-widest text-tremor-content-subtle">
          {relativeLabel(stepsFromNow, range)} · {sel.completed ?? 0} done
        </span>
        <span
          className="text-tremor-default font-semibold text-tremor-content-strong"
          style={{ textShadow: "0 0 12px rgba(99,102,241,0.55)" }}
        >
          {periodLabel(sel.period, range)}
        </span>
      </div>

      {/* Waveform */}
      <div className="relative flex flex-1 items-end gap-[3px]">
        {/* oscilloscope baseline */}
        <div className="pointer-events-none absolute inset-x-0 top-1/2 border-t border-dashed border-tremor-border/60" />
        {ticks.map((t, i) => {
          const h = 6 + ((t.completed ?? 0) / maxVal) * 38;
          const isSel = i === selected;
          return (
            <button
              key={t.period}
              type="button"
              onClick={() => go(i)}
              title={`${periodLabel(t.period, range)} — ${t.completed ?? 0} completed`}
              className="group relative flex-1 rounded-sm transition-colors"
              style={{ height: `${h}px` }}
            >
              <span
                className={`absolute inset-0 rounded-sm transition-all ${
                  isSel
                    ? "bg-tremor-brand"
                    : "bg-tremor-content-subtle/40 group-hover:bg-tremor-brand-emphasis/60"
                }`}
                style={isSel ? { boxShadow: "0 0 10px 1px rgba(99,102,241,0.7)" } : undefined}
              />
            </button>
          );
        })}
      </div>

      {/* Steppers */}
      <div className="flex items-center gap-1 font-mono">
        <button
          type="button"
          onClick={() => go(selected - 1)}
          disabled={selected <= 0}
          className="rounded-tremor-small border border-tremor-border px-2 py-1 text-tremor-content-emphasis transition-colors hover:bg-tremor-background-subtle disabled:opacity-30"
          aria-label="Previous period"
        >
          ‹
        </button>
        <button
          type="button"
          onClick={() => go(selected + 1)}
          disabled={atNow}
          className="rounded-tremor-small border border-tremor-border px-2 py-1 text-tremor-content-emphasis transition-colors hover:bg-tremor-background-subtle disabled:opacity-30"
          aria-label="Next period"
        >
          ›
        </button>
        <button
          type="button"
          onClick={() => go(ticks.length - 1)}
          disabled={atNow}
          className={`ml-1 rounded-tremor-small px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider transition-colors ${
            atNow
              ? "bg-tremor-brand-faint text-tremor-content-subtle"
              : "bg-tremor-brand text-white hover:bg-tremor-brand-emphasis"
          }`}
        >
          Now
        </button>
      </div>
    </div>
  );
}
