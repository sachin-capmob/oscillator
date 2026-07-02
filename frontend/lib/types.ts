// Response types mirroring the backend Pydantic schemas (app/schemas/insights.py).

export type Range = "day" | "week" | "month" | "all";

export interface Metric {
  current: number | null;
  previous: number | null;
  delta_pct: number | null;
}

export interface Overview {
  range: Range;
  period_start: string;
  period_end: string;
  throughput: Metric;
  avg_cycle_hours: Metric;
  comments: Metric;
  wip: number;
  open_issues: number;
}

export interface TimePoint {
  period: string;
  value: number | null;
}

export interface DualPoint {
  period: string;
  completed: number;
  created: number;
}

export interface ThroughputResp {
  range: Range;
  unit: string;
  series: DualPoint[];
}

export interface CyclePoint {
  period: string;
  avg_hours: number | null;
  median_hours: number | null;
}

export interface CycleTimeResp {
  range: Range;
  unit: string;
  series: CyclePoint[];
}

export interface WipResp {
  range: Range;
  unit: string;
  current: number;
  series: TimePoint[];
}

export interface ActorStat {
  actor_id: number;
  name: string | null;
  email: string | null;
  avatar_url: string | null;
  throughput: number;
  avg_cycle_hours: number | null;
  comments: number;
  created: number;
  sparkline: number[];
}

export interface ByActorResp {
  range: Range;
  period_start: string;
  period_end: string;
  actors: ActorStat[];
}

export interface ActorThroughputPoint {
  period: string;
  completed: number;
  created: number;
}

export interface ActorThroughputStat {
  actor_id: number;
  name: string | null;
  email: string | null;
  series: ActorThroughputPoint[];
}

export interface ThroughputByActorResp {
  range: Range;
  unit: string;
  actors: ActorThroughputStat[];
}

export interface TeamStat {
  team_id: number;
  name: string | null;
  key: string | null;
  throughput: number;
  avg_cycle_hours: number | null;
  median_cycle_hours: number | null;
  wip: number;
  comments: number;
  scope_added: number;
}

export interface ByTeamResp {
  range: Range;
  period_start: string;
  teams: TeamStat[];
}

export interface AnomalyItem {
  scope: "workspace" | "team" | "actor";
  entity_id: number | null;
  entity_name: string | null;
  metric: string; // throughput | cycle_time | wip | net_flow | created
  period: string;
  direction: "up" | "down";
  severity: "warn" | "critical";
  observed: number;
  baseline: number;
  stddev: number | null;
  z_score: number;
}

export interface AnomaliesResp {
  period: string;
  count: number;
  anomalies: AnomalyItem[];
}

export interface DigestResp {
  range: Range;
  anchor: string;
  summary: string;
  source: "groq" | "template";
  model: string | null;
  anomaly_count: number;
  generated_at: string | null;
  available: boolean;
}
