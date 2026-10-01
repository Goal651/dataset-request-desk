# Dataset Request Desk

Internal platform for a robotics data collection company: clients submit
dataset requests, operators fulfil them by assigning robot episodes, and
clients review the delivery. Built for the technical test in `WORK_TASK.md`.

**Stack:** Python 3.13, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, React
(Vite) frontend. Stretch item chosen: **background work** (simulated export
jobs with safe retries and per-episode status in the UI).

## Quick start

```bash
docker compose up --build -d
# or simply: docker compose up -d   (images build on first run)
```

This starts, in order: Postgres → migrations → seed users → API (+ frontend).

- API:        http://localhost:8000  (docs at `/docs`)
- Frontend:   http://localhost:3000
- Health:     http://localhost:8000/health

### Seed users

| Email                  | Password   | Role     |
|------------------------|------------|----------|
| `admin@example.com`    | `admin123` | admin    |
| `ops1@example.com`     | `ops123`   | operator |
| `ops2@example.com`     | `ops123`   | operator |
| `client-a@example.com` | `client123`| client   |
| `client-b@example.com` | `client123`| client   |

Passwords are bcrypt-hashed at seed time; `seed/users.json` is never read by
the API at runtime.

### Run the tests

```bash
# in containers (database included):
docker compose --profile test up --exit-code-from test test

# or locally, against a Postgres on localhost:5433 (drd/drd):
python -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt
pytest backend/tests
```

The tests spin up a fresh `drd_test` database, run the real Alembic migrations
against it, and wrap every test in a rolled-back transaction. They cover the
four things the brief cares about: authorization rules, status transitions,
assignment rules, and import idempotency.

### Import the example CSV

Via HTTP (operator/admin):

```bash
curl -X POST http://localhost:8000/episodes/import \
  -H "Authorization: Bearer $TOKEN" -F file=@seed/episodes.csv
```

or via the CLI inside the API container:

```bash
docker compose exec api python -m app.cli import /seed/episodes.csv --json
```

Both print a per-row report: `rows_seen / imported / updated / skipped` with a
reason for every skipped row. The import is idempotent — run it twice, the
second run imports nothing.

## API overview

| Endpoint | Who | What |
|---|---|---|
| `POST /auth/login` | anyone | JWT login |
| `GET /auth/me` | any | current user |
| `GET /episodes` | operator, client | list episodes, filter by `task_name`, `quality`, `robot_id`, `unassigned_only` |
| `POST /episodes/import` | operator, admin | idempotent CSV import + report |
| `GET /requests` | any (scoped) | clients see only their own |
| `POST /requests` | client | create a request |
| `GET /requests/{id}` | owner/operator/admin | detail incl. audit trail + export status |
| `POST /requests/{id}/transition` | role per step | move through the status machine |
| `POST /requests/{id}/assignments` | operator, admin | assign an episode |
| `DELETE /requests/{id}/assignments/{id}` | operator, admin | unassign |
| `GET /requests/{id}/exports` | owner/operator/admin | per-episode export status |
| `POST /requests/{id}/exports/{job}/retry` | operator, admin | retry a failed export |
| `GET /analytics` | operator, admin | date-range aggregates (SQL-side) |
| `GET /users`, `POST /users`, `PATCH /users/{id}` | admin | user management |
| `GET /health` | anyone | liveness + DB check |

## Layout

```
backend/
  app/
    main.py         app assembly, request logging middleware, /health
    config.py       env-driven settings
    db.py           engine + session factory
    models.py       SQLAlchemy models (users, episodes, requests, ...)
    domain.py       pure status-machine / role / assignment rules
    security.py     bcrypt + JWT
    deps.py         auth dependencies, role gates
    seed.py         idempotent user seeding
    exporter.py     background export worker (stretch)
    cli.py          `python -m app.cli import file.csv`
    routers/        auth, users, episodes, requests, assignments, exports, analytics
    alembic/        migration environment + versions
  tests/            pytest suite (runs against real Postgres)
frontend/           React + Vite UI
seed/               provided CSV + users.json + large-CSV generator
docker-compose.yml  db / migrate / seed / api / test / frontend
```

See `NOTES.md` for design decisions, trade-offs, and the scale story.
