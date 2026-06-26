"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { TabGroup, TabList, Tab } from "@tremor/react";

import type { Range } from "@/lib/types";
import { todayUTC } from "@/lib/dates";
import { DateScrubber } from "@/components/date-scrubber";

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
  { href: "/teams", label: "Teams & Cycles" },
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
      <div className="min-h-screen">
        <header className="sticky top-0 z-20 border-b border-tremor-border bg-tremor-background-muted/80 backdrop-blur-md">
          <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-6">
              <Link href="/" className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full bg-tremor-brand shadow-[0_0_12px_2px] shadow-indigo-500/50" />
                <span className="text-tremor-title font-semibold tracking-tight text-tremor-content-strong">
                  OSCILLATOR
                </span>
              </Link>
              <nav className="flex flex-wrap gap-1">
                {NAV.map((item) => {
                  const active = pathname === item.href;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={`rounded-tremor-small px-3 py-1.5 text-tremor-default transition-colors ${
                        active
                          ? "bg-tremor-brand-faint font-medium text-tremor-content-strong ring-1 ring-inset ring-tremor-border"
                          : "text-tremor-content hover:bg-tremor-background-subtle hover:text-tremor-content-emphasis"
                      }`}
                    >
                      {item.label}
                    </Link>
                  );
                })}
              </nav>
            </div>
            <TabGroup
              index={RANGES.indexOf(range)}
              onIndexChange={(i) => setRange(RANGES[i])}
              className="w-fit"
            >
              <TabList variant="solid">
                <Tab>Day</Tab>
                <Tab>Week</Tab>
                <Tab>Month</Tab>
              </TabList>
            </TabGroup>
          </div>
          <div className="mx-auto max-w-7xl px-4 pb-3">
            <DateScrubber />
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
      </div>
    </RangeContext.Provider>
  );
}
