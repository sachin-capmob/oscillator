# Backend — Linear Team Activity Dashboard

FastAPI service that ingests Linear workspace data via scheduled GraphQL polling
(no webhooks), normalizes it into Postgres, and serves typed activity insights.

> This is the backend package. For the project overview and full setup walkthrough,
> see the [root README](../README.md).

## Stack

- **FastAPI** (async) + **Pydantic v2 / pydantic-settings**
- **SQLAlchemy 2.0** (async, `asyncpg`) + **Alembic** migrations
- **httpx** + **tenacity** — Linear GraphQL client with pagination & backoff
- Ingestion driven by `python -m app.jobs.sync` (run by a GitHub Actions cron)

## Layout

```
backend/
├── app/
│   ├── main.py            # FastAPI app + health/ready + insights router
│   ├── config.py          # Settings (reads .env)
│   ├── db.py              # Async engine/session + declarative Base
│   ├── db_partitions.py   # Monthly partition manager
│   ├── models/            # SQLAlchemy ORM models (incl. sync_state)
│   ├── schemas/           # Pydantic API schemas
│   ├── api/               # insights router + bearer-token auth (deps.py)
│   ├── linear/            # async GraphQL client + DTOs
│   ├── jobs/              # sync.py — cron entrypoint
│   └── services/          # normalizer (raw_events landing + upserts + transitions)
├── alembic/               # 0001 schema · 0002 sync_state · 0003 views
├── tests/
├── pyproject.toml
└── requirements.txt
```

## Quickstart

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env        # then fill in DATABASE_URL, LINEAR_API_KEY, etc.

alembic upgrade head        # create schema (set DB_SSL=false for a local non-TLS Postgres)
uvicorn app.main:app --reload
```

### Migrations

```bash
alembic upgrade head            # apply
alembic downgrade -1            # roll back one revision
alembic revision -m "message"   # new (hand-written) migration
alembic upgrade head --sql      # emit SQL without connecting (offline)
```

`raw_events` and `issue_history` are declared `PARTITION BY RANGE` (monthly) but
their child partitions are created at runtime by `app/db_partitions.py`
(ensure-before-insert) — on app startup and at the start of every sync run — keeping
migrations deterministic.

### Sync (ingestion)

```bash
python -m app.jobs.sync   # empty watermark => full backfill; otherwise incremental
```

One run pulls from Linear, normalizes into the typed tables, and refreshes the
materialized views. The watermark (`sync_state`) advances only on full success.

Verify:

```bash
curl localhost:8000/health   # {"status":"ok","version":"0.1.0"}
curl localhost:8000/ready    # config readiness flags
pytest                       # smoke tests
```

Interactive API docs: <http://localhost:8000/docs>

## Environment variables

| Variable               | Required | Purpose                                          |
| ---------------------- | -------- | ------------------------------------------------ |
| `DATABASE_URL`         | yes      | Neon Postgres connection string                  |
| `LINEAR_API_KEY`       | yes      | Personal API key for GraphQL polling             |
| `DASHBOARD_AUTH_TOKEN` | yes      | Bearer token guarding the insights API           |
| `DB_SSL`               | no       | `true` for Neon (default), `false` for local     |
| `CORS_ORIGINS`         | no       | Comma-separated allowed origins (default localhost) |
| `ENVIRONMENT`          | no       | `development` / `production`                     |

See `.env.example` for the template.
