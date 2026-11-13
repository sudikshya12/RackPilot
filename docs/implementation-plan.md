# RackOps Lab — Implementation Plan & Architecture Decisions

## Starting point

The repository was empty, so there were no conventions to follow. RackOps Lab uses the
suggested stack: FastAPI + SQLAlchemy 2 + Alembic + SQLite on the backend, and React 18 +
TypeScript + Vite + Tailwind + TanStack Query + React Router + Recharts + Framer Motion on the
frontend.

## Smallest complete vertical slice

**Restore a failed service** (Project 1) end to end:
seed → simulation run → deterministic probes → detection → incident → evidence →
runbook → repair (correct or incorrect) → verification gate → resolution → summary.
That slice uses every shared layer: the models, audit log, job runner, SSE stream,
provenance labels, and the UI shell. The other two projects reuse those layers.

## Stages (each one leaves the app runnable)

1. Foundation: models, migration, seed, audit, SSE, job runner, visual system and app shell.
2. Incident workflow: scenarios, evidence collectors, hypotheses, verification gate, metrics.
3. Acceptance workflow: intake, modular checks, immutable runs, reports, diff, Redfish adapter.
4. Rack & inventory: rack elevation, cable trace, power analysis, lifecycle, spares, RMA.
5. Guided demos and case studies.
6. Verification: pytest, Playwright, screenshots, accessibility pass, docs.

## Architectural decisions

| # | Decision | Why |
|---|----------|-----|
| AD-1 | **Simulation state lives in the database** (`simulation_runs.state`), and the runner calls a pure `tick(db, now)` function. | The simulation is deterministic and survives a restart, and tests can drive it with an injected clock instead of sleeping. |
| AD-2 | **No random numbers anywhere.** Simulated metrics come from fixed fixture sequences indexed by probe number. | Credibility: the same drill always produces the same evidence. |
| AD-3 | **Every measurement and evidence row carries `source_type`, `source_id`, `collected_at`, and `simulation_run_id`.** | This provenance is required, and it lets us keep simulated and real aggregates apart. |
| AD-4 | **`origin` column on records** (`seed`, `simulation`, `operator`, `imported`, `local_lab`). | Demo reset deletes only `simulation` rows and restores seed baselines. Imported and local-lab rows are never touched. |
| AD-5 | **Spare stock quantities come from an inventory ledger** (sum of transactions) plus active reservations. They are never stored as a mutable counter. | No drift and no negative stock, and resetting simulation rows corrects stock automatically. |
| AD-6 | **Idempotency keys** on reserve, consume, and run-start endpoints, stored with their first response. | Repeated clicks or retries cannot double-consume stock. |
| AD-7 | **Verification gate:** an incident moves to `resolved` only when the latest verification after the latest repair has `passed = true`. | Pressing a button does not prove recovery. |
| AD-8 | **Acceptance runs snapshot** the expected config, the profile, and the observations at start, and become immutable when they complete. | Reports reflect the persisted run, not the current mutable state. |
| AD-9 | **SSE events are persisted** in `stream_events` with monotonically increasing IDs. | `Last-Event-ID` replay on reconnect, so the UI never misses a transition. |
| AD-10 | **Live lab is opt-in and self-contained:** the backend launches its own tiny HTTP target as a child process (fixed argv, no shell). | This gives a safe, real service-stop exercise without touching host services. |
| AD-11 | **The Redfish adapter is GET-only**, with fixture mode by default and TLS verification on. | No power or firmware actions can exist. |
| AD-12 | **SQLite with `BEGIN IMMEDIATE`** for inventory mutations. | A single writer gives serializable reservation semantics for this single-user app. |
| AD-13 | **Status is never color-only.** Every status chip includes text, and the rack view has a table equivalent. | Accessibility. |
