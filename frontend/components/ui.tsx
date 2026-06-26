"use client";

import { BadgeDelta, Card, Flex, Text } from "@tremor/react";
import type { Color, DeltaType } from "@tremor/react";

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function LoadingState() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {[0, 1, 2, 3].map((i) => (
        <Card key={i} className="animate-pulse">
          <div className="h-3 w-24 rounded bg-tremor-background-subtle" />
          <div className="mt-4 h-8 w-16 rounded bg-tremor-background-subtle" />
        </Card>
      ))}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <Card decoration="left" decorationColor="rose">
      <Text className="font-medium text-rose-400">Could not load data</Text>
      <Text className="mt-1 text-tremor-content">{message}</Text>
    </Card>
  );
}

export function EmptyState({ message = "No data for this range yet." }: { message?: string }) {
  return (
    <Card>
      <Flex className="h-32" justifyContent="center" alignItems="center">
        <Text className="text-tremor-content-subtle">{message}</Text>
      </Flex>
    </Card>
  );
}

function deltaType(pct: number | null): DeltaType {
  if (pct === null) return "unchanged";
  if (pct > 5) return "increase";
  if (pct > 0) return "moderateIncrease";
  if (pct < -5) return "decrease";
  if (pct < 0) return "moderateDecrease";
  return "unchanged";
}

export function KpiCard({
  title,
  value,
  unit,
  deltaPct,
  accent = "indigo",
  invertDelta = false,
}: {
  title: string;
  value: string | number;
  unit?: string;
  deltaPct?: number | null;
  accent?: Color;
  // For metrics where "down is good" (e.g. cycle time), flip the badge color.
  invertDelta?: boolean;
}) {
  const showDelta = deltaPct !== undefined && deltaPct !== null;
  let dt = deltaType(deltaPct ?? null);
  if (invertDelta && showDelta) {
    const flip: Record<DeltaType, DeltaType> = {
      increase: "decrease",
      moderateIncrease: "moderateDecrease",
      decrease: "increase",
      moderateDecrease: "moderateIncrease",
      unchanged: "unchanged",
    };
    dt = flip[dt];
  }
  return (
    <Card decoration="top" decorationColor={accent} className="ring-tremor-border">
      <Flex alignItems="start" className="gap-2">
        <Text className="uppercase tracking-wide text-tremor-content-subtle">{title}</Text>
        {showDelta && (
          <BadgeDelta deltaType={dt} size="xs">
            {deltaPct! > 0 ? "+" : ""}
            {deltaPct}%
          </BadgeDelta>
        )}
      </Flex>
      <p className="mt-3 flex items-baseline gap-1.5">
        <span className="text-3xl font-semibold tracking-tight text-tremor-content-strong">
          {value}
        </span>
        {unit ? <span className="text-tremor-default text-tremor-content">{unit}</span> : null}
      </p>
    </Card>
  );
}
