# Linear Team Activity Dashboard

An internal dashboard that ingests Linear workspace data and visualizes individual
and team activity with daily, weekly, and monthly insights — throughput, cycle time,
WIP, scope change, and collaboration, with week-over-week / month-over-month deltas.

Runs entirely on free tiers (Neon Postgres, GitHub Actions cron, Vercel hobby).

---

## Architecture — cron polling (no webhooks, no always-on server)

```
   ┌───────────────────────── GitHub Actions (cron 3×/day + manual) ─────────────────────────┐
   │  python -m app.jobs.sync                                                                 │
   │                                                                                          │
   │  read watermark ─▶ pull from Linear GraphQL ─▶ normalize ─▶ refresh rollups ─▶ advance   │
   │  (sync_state)      (teams/users full;          (raw_events  (REFRESH MAT.       watermark │
   │                     issues/comments/cycles      then upsert  VIEW CONCURRENTLY) on success│
   │                     by updatedAt > since)       typed tables)                            │
   └───────────────┬──────────────────────────────────────────────────────────────┬─────────┘
                   │                                                                │
                   ▼                                                                ▼
        ┌─────────────────────┐                                      daily_actor_rollup
        │   Neon Postgres      │  actors · issues · issue_history ·   weekly_team_rollup
        │  (raw_events JSONB    │  comments · cycles · sync_state      monthly_team_rollup
        │   + typed tables +    │                                              │
        │   materialized views) │                                              │
        └──────────┬───────────┘                                              │
                   │  GET /api/insights/*  (token-auth, Pydantic-typed)        │
                   ▼                                                           │
        ┌──────────────────────┐      same-origin proxy injects token         │
        │  FastAPI insights API │◀────────────────────────────────────────────┘
        └──────────┬───────────┘
                   ▼
        ┌──────────────────────────┐
        │ Next.js + Tremor dashboard│  Overview · Trends · People · Teams & Cycles
        └──────────────────────────┘
```

**Why cron, not webhooks?** No server needs to stay online to receive events. A
scheduled GitHub Action runs the sync; an incremental `updatedAt > (watermark − 5 min)`
filter keeps each run cheap, and the 5-minute overlap guarantees nothing is missed
between runs. Idempotent upserts make re-runs safe.

> **Polling-granularity caveat.** Because we poll (not stream), intermediate state
> hops that happen *between* two runs are not individually captured — only the net
> change since the last run. Throughput and cycle time therefore rely on Linear's own
> `completedAt` / `startedAt` timestamps (accurate regardless of poll timing); the
> `issue_history` table records the transitions observed at each poll.

---

## Tech stack

| Layer         | Choice                                                       |
| ------------- | ------------------------------------------------------------ |
| Backend       | FastAPI (async), Pydantic v2                                 |
| Database      | Neon Postgres via SQLAlchemy 2.0 (async, asyncpg) + Alembic  |
| Ingestion     | `python -m app.jobs.sync` (Linear GraphQL, cursor-paginated) |
| Scheduler     | GitHub Actions cron (`.github/workflows/sync.yml`)           |
| Frontend      | Next.js (App Router) + TypeScript + Tailwind + Tremor        |

---

## Repository layout

```
monitoring/
├── README.md
├── .github/workflows/sync.yml     cron: pull + normalize + refresh views
├── backend/
│   ├── app/
│   │   ├── main.py                FastAPI app + /health, /ready + insights router
│   │   ├── config.py              settings (.env)
│   │   ├── db.py                  async engine/session + Base
│   │   ├── db_partitions.py       monthly partition manager
│   │   ├── models/                ORM models (incl. sync_state)
│   │   ├── schemas/insights.py    Pydantic API responses
│   │   ├── api/                   insights router + token auth (deps.py)
│   │   ├── linear/client.py       async GraphQL client + DTOs
│   │   ├── services/normalizer.py raw_events landing + upserts + transitions
│   │   └── jobs/sync.py           cron entrypoint (watermark + orchestration)
│   ├── alembic/                   0001 schema · 0002 sync_state · 0003 views
│   └── tests/
└── frontend/
    ├── app/                       Overview / trends / people / teams + proxy route
    ├── components/                shell (nav + range selector), ui helpers
    └── lib/                       api client + types
```

---

## Prerequisites

- **Python 3.11+** and **Node.js 18.18+**
- A free **Neon** Postgres project — <https://neon.tech>
- A **Linear** personal API key — Linear → Settings → Security & access → Personal API keys

---

## Local setup

### 1. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env          # set DATABASE_URL, LINEAR_API_KEY, DASHBOARD_AUTH_TOKEN

alembic upgrade head          # create schema + rollups
python -m app.jobs.sync       # first backfill (watermark is empty → full pull)
uvicorn app.main:app --reload # serve the insights API
```

> Local Postgres without TLS? set `DB_SSL=false`. Neon needs `DB_SSL=true` (default).

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local     # set API_BASE_URL + DASHBOARD_AUTH_TOKEN (match backend)
npm run dev                    # http://localhost:3000
```

The browser only ever talks to the same-origin proxy at `/api/insights/*`
(`app/api/insights/[...path]/route.ts`), which injects the bearer token
server-side — the token is never shipped to the client.

---

## Scheduled sync (GitHub Actions)

`.github/workflows/sync.yml` runs `python -m app.jobs.sync` at **06:00, 13:00, 20:00 UTC**
and on demand. It applies migrations, pulls from Linear, normalizes, and refreshes the
materialized views. A non-zero exit fails the job and leaves the watermark unadvanced.

**Set repo secrets** (Settings → Secrets and variables → Actions → New repository secret):

| Secret           | Value                                  |
| ---------------- | -------------------------------------- |
| `DATABASE_URL`   | Neon connection string                 |
| `LINEAR_API_KEY` | Linear personal API key                |

**Trigger manually:** Actions tab → *Linear Sync* → **Run workflow**, or:

```bash
gh workflow run "Linear Sync"
gh run watch
```

---

## Environment variables

**Backend** (`backend/.env`)

| Variable               | Required | Purpose                                |
| ---------------------- | -------- | -------------------------------------- |
| `DATABASE_URL`         | yes      | Neon Postgres connection string        |
| `LINEAR_API_KEY`       | yes      | GraphQL pull (sent as raw `Authorization`) |
| `DASHBOARD_AUTH_TOKEN` | yes      | Bearer token guarding the insights API |
| `DB_SSL`               | no       | `true` for Neon (default), `false` local |
| `CORS_ORIGINS`         | no       | Comma-separated allowed origins        |

**Frontend** (`frontend/.env.local`) — both server-side only:

| Variable               | Required | Purpose                                |
| ---------------------- | -------- | -------------------------------------- |
| `API_BASE_URL`         | yes      | FastAPI base URL                       |
| `DASHBOARD_AUTH_TOKEN` | yes      | Must equal the backend's token         |

---

## Insights API

All endpoints require `Authorization: Bearer <DASHBOARD_AUTH_TOKEN>` and accept
`?range=day|week|month`.

| Endpoint                      | Returns                                              |
| ----------------------------- | ---------------------------------------------------- |
| `GET /api/insights/overview`  | KPI cards (throughput, cycle time, WIP, open) + deltas |
| `GET /api/insights/throughput`| completed-issues time series                          |
| `GET /api/insights/cycle-time`| avg + median cycle-time series                        |
| `GET /api/insights/wip`       | current WIP + WIP time series                         |
| `GET /api/insights/by-actor`  | per-person throughput / cycle / comments + sparkline  |
| `GET /api/insights/by-team`   | per-team velocity (throughput, cycle, WIP, scope)     |

Interactive docs: <http://localhost:8000/docs>.

---

## Metrics

- **Throughput** — issues completed per actor/team per day/week/month
- **Cycle time** — avg/median `started_at → completed_at`
- **WIP** — issues in a `started` state over time
- **Scope change** — issues attached to a cycle and created after it started
- **Collaboration** — comments authored per actor
- **Trend deltas** — week-over-week / month-over-month % change

---

## Delivery status

1. Repo structure + README ✅
2. Data model + Alembic (monthly-partitioned `raw_events`/`issue_history`) ✅
3. Linear GraphQL client + sync entrypoint ✅
4. Normalizer + watermark (`sync_state`) ✅
5. Materialized views + concurrent refresh ✅
6. Insights API ✅
7. Next.js + Tremor dashboard ✅
8. GitHub Actions cron + docs ✅
