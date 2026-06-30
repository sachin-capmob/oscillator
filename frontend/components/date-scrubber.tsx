"use client";

// Cadence's waveform date scrubber. Each bar is a period (day / week / month)
// with height = throughput; click a bar — or use the ‹ › steppers — to focus
// the whole dashboard on that period. The right edge is "now"; you cannot
// scrub into the future. Styled to the six-token system: --signal marks the
// selected bar, everything else --edge / --muted. Sharp corners throughout.

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
      <div className="relative flex h-[72px] items-end gap-px py-2">
        <div className="loadbar" aria-hidden />
        {Array.from({ length: 24 }).map((_, i) => (
          <div
            key={i}
            className="flex-1 bg-edge"
            style={{ height: `${8 + ((i * 7) % 26)}px`, opacity: 0.5 }}
          />
        ))}
      </div>
    );
  }

  const atNow = selected >= ticks.length - 1;
  const stepsFromNow = ticks.length - 1 - selected;
  const sel = ticks[selected];

  const go = (i: number) =>
    setAnchor(ticks[Math.max(0, Math.min(ticks.length - 1, i))].period);

  return (
    <div className="flex items-stretch gap-7 py-3.5">
      {/* Readout */}
      <div className="flex min-w-[190px] flex-col justify-center gap-1">
        <span className="eyebrow" style={{ color: stepsFromNow === 0 ? "var(--signal)" : "var(--muted)" }}>
          {relativeLabel(stepsFromNow, range)} · {sel.completed ?? 0} done
        </span>
        <span className="font-mono text-title text-ink">{periodLabel(sel.period, range)}</span>
      </div>

      {/* Waveform */}
      <div className="relative flex flex-1 items-end gap-px py-2">
        {/* baseline */}
        <div className="pointer-events-none absolute inset-x-0 top-1/2 border-t border-edge" />
        {ticks.map((t, i) => {
          const h = 5 + ((t.completed ?? 0) / maxVal) * 38;
          const isSel = i === selected;
          return (
            <button
              key={t.period}
              type="button"
              onClick={() => go(i)}
              title={`${periodLabel(t.period, range)} — ${t.completed ?? 0} completed`}
              className="group relative flex-1"
              style={{ height: "44px" }}
            >
              <span
                className="absolute inset-x-0 bottom-0 transition-colors group-hover:opacity-80"
                style={{
                  height: `${h}px`,
                  background: isSel ? "var(--signal)" : "var(--edge)",
                }}
              />
            </button>
          );
        })}
      </div>

      {/* Steppers */}
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => go(selected - 1)}
          disabled={selected <= 0}
          className="flex h-9 w-9 items-center justify-center border border-edge font-mono text-title text-ink transition-colors hover:bg-edge disabled:opacity-30"
          aria-label="Previous period"
        >
          ‹
        </button>
        <button
          type="button"
          onClick={() => go(selected + 1)}
          disabled={atNow}
          className="flex h-9 w-9 items-center justify-center border border-edge font-mono text-title text-ink transition-colors hover:bg-edge disabled:opacity-30"
          aria-label="Next period"
        >
          ›
        </button>
        <button
          type="button"
          onClick={() => go(ticks.length - 1)}
          disabled={atNow}
          className="ml-1.5 flex h-9 items-center border px-4 text-nav font-medium uppercase tracking-eyebrow transition-colors"
          style={
            atNow
              ? { borderColor: "var(--edge)", color: "var(--muted)" }
              : { borderColor: "var(--signal)", color: "var(--signal)" }
          }
        >
          Now
        </button>
      </div>
    </div>
  );
}
