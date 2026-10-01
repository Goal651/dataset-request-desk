# NOTES.md — design decisions, trade-offs, scale

## 1. Design

**Data model.** Six tables. `users` (role enum: client/operator/admin, bcrypt
hashes). `episodes` (unique `episode_id`, quality enum, indexes on `task_name`,
`recorded_at`, `quality` — the analytics access paths). `requests` (client FK,
`episodes_requested`, `deadline`, `status` enum). `assignments` is the join
between requests and episodes plus audit fields (`assigned_by`,
`created_at`, `unassigned_at`). `status_events` is an append-only audit trail
(request FK, from/to status, actor, note, timestamp). `export_jobs` backs the
stretch item (assignment FK, `status`, `attempt`, `error`).

**Where state lives.** The request row's `status` is the single source of
truth for workflow position; every change also appends a `status_events` row,
so the current state is queryable without replaying history and the history is
reconstructable without parsing the current state. "Which episodes belong to
this request" is derived: rows in `assignments` with `unassigned_at IS NULL`.

**Decision 1 — soft-delete assignments.** Unassigning sets `unassigned_at`
instead of deleting. The "one request at a time" rule is then a *partial*
uniqueness constraint — `UNIQUE (episode_id, unassigned_at)` with
`NULLS NOT DISTINCT` — enforced by Postgres, not by check-then-insert code. A
reassigned episode keeps its full trail, and the race between two concurrent
assigns is decided by the database.

**Decision 2 — the status machine as data.** Transitions live in one dict
(`domain.py`): `from → {to: allowed roles}`, consumed by a pure function. The
HTTP layer only adds request lookup, client-scoping, and the audit write. The
one stateful rule — "delivered requires ≥ `episodes_requested` episodes" — is
checked inside the transition endpoint against a `COUNT` in the same
transaction. A pure table is trivially testable and the tests read like the
spec.

**Decision 3 — import policy: normalize where intent is clear, skip with a
reason where it isn't.** Trimming/case-normalizing `ep-00003` → `EP-00003`,
`Good` → `good`, `  Pick Cup ` → `pick cup` is unambiguous. A future date
(2031), `not a date`, `-5`/`999999` seconds, `excellent`, and unknown robot
`arm-99` are *data errors I could guess at but shouldn't*: the row is skipped
and reported with the reason, never silently "fixed". The import is an upsert
keyed on `episode_id` — re-running the same file reports `updated` for rows
already present, `imported` stays 0, nothing duplicates (in-file duplicates
are deduped the same way). Fractional durations (`45.5`) are kept: plausibly
frame rounding, not garbage.

**Stretch: background work.** Each assignment creates one `export_jobs` row;
a worker thread in the API process claims `pending` jobs, sleeps 2–5s, fails
20% of the time, and writes `done`/retry. Safety properties: the attempt
counter increments on claim; a failed attempt flips the row back to `pending`
until `MAX_ATTEMPTS`, then `failed` (operator can retry from the UI);
completion is a guarded update (status must still be `running`), so a crashed
worker leaves the job retryable rather than half-done. With more than one
worker you'd claim via `SELECT ... FOR UPDATE SKIP LOCKED` — noted here, not
built, because one process was enough for the simulation.

## 2. What I deliberately left out (and the next two days)

- **No pagination metadata / infinite scroll polish** in the UI; offset/limit
  exists server-side everywhere.
- **Auth lifecycle is minimal:** one 12h JWT, no refresh token, no revocation
  list. Next: short-lived access tokens + refresh, and a `token_version`
  column so deactivation/role change invalidates outstanding tokens.
- **No login rate limiting** (a per-IP/user throttle would be first).
- **Exports are simulated**; real exports would stream episode files to object
  storage, which mostly changes the worker body, not the retry design.
- **No frontend tests.** The API is thoroughly tested; the UI was exercised
  manually. With two more days: Playwright smoke tests for the three roles'
  main flows.
- **Batch "assign N episodes" as one atomic op** (pick top-N unassigned
  matching a filter). Current UI assigns one at a time; the service function
  would be a transaction around the same rule checks.
- **Analytics rollups.** Straight SQL now (see §5); a pre-aggregated
  daily-per-robot table (or continuous aggregate) is the next step.

## 3. Something that went wrong, and how I found it

After introducing the test suite, the very first run failed with
`relation "users" does not exist` — despite migrations having just "run". I
reproduced with a single test and read the captured output: Alembic reported
`Will assume transactional DDL` with no target database mention. The cause was
in `alembic/env.py`: it *unconditionally* overwrote `sqlalchemy.url` from app
settings, so the `set_main_option(..., drd_test)` call in the test fixture was
silently discarded and migrations ran against the dev database — which already
had tables for the dev flow but not for the freshly created test database.
The fix was to treat the config file value as a default, overridden only when
empty. Lesson: a config-precedence bug looks exactly like a missing-migration
bug; the tell was *which* database Alembic claimed to be running against. I
also made the failure mode louder by pointing the test fixture at a database
name that can't be confused with the dev one.

## 4. Security

- **Passwords:** bcrypt, cost 12 (env-tunable; tests use 4 for speed). Login
  errors are identical for unknown-email and wrong-password, and deactivation
  is checked after the hash check so timing doesn't leak account existence.
- **Tokens:** HS256 JWT, 12h expiry, `sub`/`role`/`iat`/`exp`/`jti`. The role
  claim in the token is treated as advisory: every authorization decision
  re-reads the user from the DB, so role changes and deactivation take effect
  immediately (a deactivated user's token is dead even if unexpired).
- **Authorization is server-side and centralized:** a role-gate dependency on
  every non-public endpoint, plus an ownership check (`_visible_to`) for
  request objects — cross-client access returns 404, not 403, so it doesn't
  leak existence. Admins inherit operator permissions in one place.
- **Input validation:** Pydantic models with length/enum/range constraints on
  every write path; the import caps upload size (10 MB) and validates every
  field per row; all SQL goes through SQLAlchemy's bound parameters (the only
  string literal is `SELECT 1` in the healthcheck).
- **Secrets** come from the environment (`JWT_SECRET`, `DATABASE_URL`);
  compose defaults exist for local dev and are labelled as such.
- **The two vulnerabilities I'd worry about most:** (1) *object-level
  authorization bugs (IDOR)* — an endpoint that forgets the ownership check
  leaks one client's delivery pipeline to another; the mitigation is that
  scoping lives in shared helpers, not per-endpoint code, and tests probe
  cross-client access on read/transition/assign. (2) *Privilege confusion
  between operators and clients on workflow endpoints* — e.g. a client
  replaying a "transition" call with an operator-only target status; the
  transition table encodes allowed roles per edge and is unit-tested
  exhaustively. (Honourable mention: CSV/formula injection if these exports
  ever reach Excel — an export feature would need `=`/`+`/`-`/`@` escaping.)

## 5. Scale: 10× users, 100× episodes (and 5M)

- **10× users (≈ hundreds):** fine. Sessions are stateless JWTs; the DB is the
  bottleneck and connection pooling (SQLAlchemy pool + `pool_pre_ping`)
  covers it. First to hurt would be the per-request `_assigned_counts` and
  `_actor_names` helper queries — they'd become joins or be cached.
- **100× episodes (≈ 200k):** listing/analytics still fine (indexed), but the
  **import is the first thing to break**: it currently loads *all* existing
  `episode_id`s into a dict to make re-runs idempotent — GBs of RAM at
  millions of rows. The fix: upload → `COPY` into a staging table →
  set-based validation → `INSERT ... ON CONFLICT (episode_id) DO UPDATE`,
  reporting from a `RETURNING`/diff query. Same idempotency semantics, one
  pass, constant memory.
- **5M episodes, analytics:** the per-day-per-robot query is a `date_trunc`
  group-by over an indexed range — a date-bounded query stays interactive,
  an unbounded dashboard query scans the table. At 5M I'd maintain a
  rollup table (`day, robot_id, task_name, quality → counts`) updated on
  import (idempotent re-runs make this safe) and serve analytics from it.
  The median uses `PERCENTILE_CONT` over one row per delivered request —
  requests are human-scale (thousands), so it's a non-issue even at 5M
  episodes. Episodes listing for operators stays indexed + paginated.

## 6. AI tooling

I used an AI coding agent (Codebuff) to draft files and run the verification
loop (pytest, `compileall`, Docker). It also mangled a handful of file writes
along the way — duplicated lines, placeholder tokens — which I caught by
read-back and compile checks before anything was committed, and fixed by
hand. Every line here has been executed against a real Postgres through the
39-test suite, and I can walk through any of it — the pure status-machine
table, the `NULLS NOT DISTINCT` assignment constraint, the import upsert, and
the Alembic env-precedence bug in §3 are the parts I'd expect to be probed.
