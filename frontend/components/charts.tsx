"use client";

// Raw Recharts charts styled entirely to the six-token system — no Tremor.
// cartesianGrid: --edge @ 0.4 opacity, no chart border, area fill is the one
// permitted gradient (--signal 15% → transparent), tooltip via <ChartTooltip>.

import {
  Area,
  AreaChart as RAreaChart,
  Bar,
  BarChart as RBarChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ChartTooltip } from "@/components/ui";

const AXIS_TICK = { fill: "var(--muted)", fontSize: 10, fontFamily: "var(--font-mono)" };
const GRID_STROKE = "rgba(28, 35, 51, 0.4)"; // --edge @ 0.4

export interface SeriesDef {
  key: string;
  name: string;
  // "signal" → the mint accent + gradient fill; "edge" → muted gray line/fill.
  tone: "signal" | "edge";
}

// Resolve tone → concrete color. The "edge" tone uses a lighter gray than the
// raw --edge token so a secondary series stays legible against --surface.
function color(tone: SeriesDef["tone"]): string {
  return tone === "signal" ? "var(--signal)" : "#5a6478";
}

/* -------------------------------------------------------------------------- */
/* Area chart — up to two series. Primary series gets the gradient fill.      */
/* -------------------------------------------------------------------------- */
export function AreaChart({
  data,
  index,
  series,
  height = 288,
  valueSuffix = "",
}: {
  data: Record<string, unknown>[];
  index: string;
  series: SeriesDef[];
  height?: number;
  valueSuffix?: string;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RAreaChart data={data} margin={{ top: 16, right: 20, bottom: 4, left: 4 }}>
        <defs>
          <linearGradient id="fill-signal" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--signal)" stopOpacity={0.15} />
            <stop offset="100%" stopColor="var(--signal)" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="fill-edge" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#5a6478" stopOpacity={0.1} />
            <stop offset="100%" stopColor="#5a6478" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID_STROKE} vertical={false} />
        <XAxis
          dataKey={index}
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={{ stroke: "var(--edge)" }}
          minTickGap={24}
        />
        <YAxis
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
          width={36}
          allowDecimals={false}
        />
        <Tooltip
          cursor={{ stroke: "var(--edge)" }}
          content={<ChartTooltip valueSuffix={valueSuffix} />}
        />
        {series.map((s) => (
          <Area
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.name}
            stroke={color(s.tone)}
            strokeWidth={1.5}
            fill={`url(#fill-${s.tone})`}
            fillOpacity={1}
            dot={false}
            activeDot={{ r: 3, fill: color(s.tone), strokeWidth: 0 }}
            connectNulls
            isAnimationActive={false}
          />
        ))}
      </RAreaChart>
    </ResponsiveContainer>
  );
}

/* -------------------------------------------------------------------------- */
/* Line chart — same axes, no fill. For cycle-time style trend pairs.         */
/* -------------------------------------------------------------------------- */
export function LineChart({
  data,
  index,
  series,
  height = 288,
  valueSuffix = "",
}: {
  data: Record<string, unknown>[];
  index: string;
  series: SeriesDef[];
  height?: number;
  valueSuffix?: string;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RAreaChart data={data} margin={{ top: 16, right: 20, bottom: 4, left: 4 }}>
        <CartesianGrid stroke={GRID_STROKE} vertical={false} />
        <XAxis
          dataKey={index}
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={{ stroke: "var(--edge)" }}
          minTickGap={24}
        />
        <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} width={36} />
        <Tooltip
          cursor={{ stroke: "var(--edge)" }}
          content={<ChartTooltip valueSuffix={valueSuffix} />}
        />
        {series.map((s) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.name}
            stroke={color(s.tone)}
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 3, fill: color(s.tone), strokeWidth: 0 }}
            connectNulls
            isAnimationActive={false}
          />
        ))}
      </RAreaChart>
    </ResponsiveContainer>
  );
}

/* -------------------------------------------------------------------------- */
/* Bar chart — sharp corners, --signal / gray. `horizontal` lays the bars on  */
/* their side (category on the Y axis) — better for ranking long labels like  */
/* people's names side by side.                                               */
/* -------------------------------------------------------------------------- */
export function BarChart({
  data,
  index,
  series,
  height = 288,
  horizontal = false,
  categoryWidth = 120,
}: {
  data: Record<string, unknown>[];
  index: string;
  series: SeriesDef[];
  height?: number;
  horizontal?: boolean;
  categoryWidth?: number;
}) {
  if (horizontal) {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <RBarChart
          data={data}
          layout="vertical"
          margin={{ top: 8, right: 24, bottom: 4, left: 4 }}
          barCategoryGap="28%"
        >
          <CartesianGrid stroke={GRID_STROKE} horizontal={false} />
          <XAxis
            type="number"
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={{ stroke: "var(--edge)" }}
            allowDecimals={false}
          />
          <YAxis
            type="category"
            dataKey={index}
            tick={{ ...AXIS_TICK, fontFamily: "var(--font-sans)" }}
            tickLine={false}
            axisLine={false}
            width={categoryWidth}
            interval={0}
          />
          <Tooltip cursor={{ fill: "rgba(28,35,51,0.3)" }} content={<ChartTooltip />} />
          {series.map((s) => (
            <Bar key={s.key} dataKey={s.key} name={s.name} fill={color(s.tone)} isAnimationActive={false} />
          ))}
        </RBarChart>
      </ResponsiveContainer>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RBarChart data={data} margin={{ top: 16, right: 20, bottom: 4, left: 4 }}>
        <CartesianGrid stroke={GRID_STROKE} vertical={false} />
        <XAxis
          dataKey={index}
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={{ stroke: "var(--edge)" }}
          interval={0}
        />
        <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} width={36} allowDecimals={false} />
        <Tooltip cursor={{ fill: "rgba(28,35,51,0.3)" }} content={<ChartTooltip />} />
        {series.map((s) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            name={s.name}
            fill={color(s.tone)}
            isAnimationActive={false}
          />
        ))}
      </RBarChart>
    </ResponsiveContainer>
  );
}
