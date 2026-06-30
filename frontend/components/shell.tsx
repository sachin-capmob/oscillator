"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";

import type { Range } from "@/lib/types";
import { todayUTC } from "@/lib/dates";
import { DateScrubber } from "@/components/date-scrubber";
import { Segmented } from "@/components/segmented";

const RANGES: Range[] = ["day", "week", "month"];

interface RangeCtx {
  range: Range;
  setRange: (r: Range) => void;
  anchor: string; // YYYY-MM-DD — the day/week/month the dashboard is focused on
  setAnchor: (d: string) => void;
}
const RangeContext = createContext<RangeCtx>({
  range: "week",
  setRange: () => {},
  anchor: todayUTC(),
  setAnchor: () => {},
});

export function useRange(): RangeCtx {
  return useContext(RangeContext);
}

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/trends", label: "Trends" },
  { href: "/people", label: "People" },
  { href: "/teams", label: "Cycles" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [range, setRangeState] = useState<Range>("week");
  const [anchor, setAnchor] = useState<string>(todayUTC());

  useEffect(() => {
    // URL params win (deep-linkable), then fall back to the saved range.
    const params = new URLSearchParams(window.location.search);
    const urlRange = params.get("range") as Range | null;
    const urlAnchor = params.get("anchor");
    const saved = window.localStorage.getItem("range") as Range | null;
    if (urlRange && RANGES.includes(urlRange)) setRangeState(urlRange);
    else if (saved && RANGES.includes(saved)) setRangeState(saved);
    if (urlAnchor && /^\d{4}-\d{2}-\d{2}$/.test(urlAnchor)) setAnchor(urlAnchor);
  }, []);

  const setRange = (r: Range) => {
    setRangeState(r);
    window.localStorage.setItem("range", r);
  };

  return (
    <RangeContext.Provider value={{ range, setRange, anchor, setAnchor }}>
      <div className="min-h-screen bg-void">
        {/* Top navigation rail — 56px, --edge bottom border only. Inner content
            is centered to the same max-width gutter as the page body. */}
        <header className="sticky top-0 z-30 h-14 border-b border-edge bg-void">
          <div className="mx-auto flex h-full max-w-[1600px] items-stretch px-6 lg:px-10">
            <Link
              href="/"
              className="-ml-1 flex items-center gap-3 pr-10 text-[14px] font-semibold tracking-eyebrow text-ink"
            >
              <span
                className="inline-block h-2 w-2"
                style={{ background: "var(--signal)" }}
                aria-hidden
              />
              OSCILLATOR
            </Link>
            <nav className="flex items-stretch gap-1">
              {NAV.map((item) => {
                const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="relative flex items-center px-5 text-nav font-medium transition-colors hover:text-ink"
                    style={{ color: active ? "var(--ink)" : "var(--muted)" }}
                  >
                    {item.label}
                    {active && (
                      <span
                        className="absolute inset-x-4 -bottom-px h-0.5"
                        style={{ background: "var(--signal)" }}
                        aria-hidden
                      />
                    )}
                  </Link>
                );
              })}
            </nav>
          </div>
        </header>

        {/* Command bar — 52px, --surface; range selector + scrubber share the
            centered gutter so controls line up with the content below. */}
        <div className="sticky top-14 z-20 border-b border-edge bg-surface">
          <div className="mx-auto flex h-[52px] max-w-[1600px] items-center px-6 lg:px-10">
            <Eyebrowed label="RANGE">
              <Segmented
                options={[
                  { value: "day", label: "Day" },
                  { value: "week", label: "Week" },
                  { value: "month", label: "Month" },
                ]}
                value={range}
                onChange={(v) => setRange(v as Range)}
              />
            </Eyebrowed>
          </div>
        </div>

        {/* Date scrubber strip — the secondary control rail */}
        <div className="border-b border-edge bg-void">
          <div className="mx-auto max-w-[1600px] px-6 lg:px-10">
            <DateScrubber />
          </div>
        </div>

        {/* Content — centered, generous gutters + vertical rhythm so panels
            breathe instead of bleeding edge-to-edge. */}
        <main className="mx-auto min-h-[60vh] max-w-[1600px] px-6 py-8 lg:px-10 lg:py-10">
          {children}
        </main>
      </div>
    </RangeContext.Provider>
  );
}

function Eyebrowed({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3.5">
      <span className="eyebrow">{label}</span>
      {children}
    </div>
  );
}
