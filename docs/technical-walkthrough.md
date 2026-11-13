# Technical Walkthrough: Key Implementation Decisions

Paths are relative to the repository root.

## 1. The verification gate

`backend/app/services/incidents.py`

- `apply_repair_action()` is allowed only while the incident is *investigating*. It records a `repair_actions` row and moves the incident to `repair_applied`.
- `verify()` runs the scenario's checks against current state: the simulator state, real live-lab probes, or the alert source. It stores a `verifications` row with `after_repair_id`.
  - If every check passes, it sets `verified_at`.
  - If the only failing check is `post_repair_samples`, the incident stays in *verification* ("waiting").
  - Any other failure moves the incident back to `investigating`.
- `resolve()` raises `verification_required` unless the latest verification **passed**, references the **latest** repair, and executed after it.
- `reopen()` clears `resolved_at` and `verified_at`, stores the prior values in the event detail, and returns to investigating. A new repair and a new verification are then required.
- Tests: `test_resolution_requires_successful_verification`, `test_incorrect_hypothesis_does_not_resolve`, `test_reopening_preserves_history`.

## 2. Ledger-derived stock, write locks and idempotency

`backend/app/services/inventory.py`, `backend/app/db.py`, `backend/app/services/common.py`

- `spare_stock` has no quantity column. `on_hand()` = `SUM(quantity_delta)` and `reserved()` = the sum of active reservations. Stock cannot drift, and deleting simulation-owned ledger rows restores quantities automatically.
- Mutating routes use `get_write_db()`, so their transaction starts with `BEGIN IMMEDIATE`. Inside `reserve()`, the availability read and the insert run under the write lock.
- `consume()` performs all its writes in one transaction: the ledger row, the reservation status, the new asset, the power-input component link, quarantining the failed asset, and the incident repair. Any `DomainError` rolls back all of them (`test_consumption_is_atomic_and_not_repeatable`).
- Three layers block double consumption: the status check (`already_consumed`), the `Idempotency-Key` replay (`idempotent_lookup` and `idempotent_store`), and the DB constraint `UNIQUE(reservation_id, kind)` on `inventory_transactions`.

## 3. Immutable acceptance snapshots

`backend/app/services/acceptance.py`

- `start_run()` copies `expected_snapshot`, `profile_snapshot`, `observed_snapshot` and `corrections_before_run` into the run. Checks run only against these snapshots.
- Completed runs are never updated. Manual reviews go to `manual_reviews`, and `run_effective()` computes the effective disposition without changing stored results.
- Re-tests get a new `run_number` (unique per intake). `compare()` diffs two runs, and reports render from the run record (`test_reports_preserve_source_and_timestamps` mutates the intake and confirms the report is unchanged).

## 4. Disposition rules

`backend/app/acceptance/checks.py: disposition()`

```text
any required FAIL                                         → FAIL
any required UNSUPPORTED | SKIPPED | ERROR | MANUAL_REVIEW → MANUAL_REVIEW
otherwise                                                 → PASS   (optional checks never decide)
```

A missing observation section returns `UNSUPPORTED` with the observed value "Not collected" (`_section()`). An exception raised inside a check becomes `ERROR` (`_execute_check`), never PASS.

## 5. SSE with replay

`backend/app/services/common.py: publish()` writes a `stream_events` row in the same transaction as the change. `backend/app/routers/platform.py: events()` streams rows with `id:` and resumes from `Last-Event-ID` or `?last_event_id=`. `frontend/src/lib/sse.ts` reconnects with backoff, tracks the last ID, debounces query invalidation by topic, and exposes the connection state to the header indicator.

## 6. Deterministic simulation

`backend/app/services/simulation.py: tick(db, now)` advances runs whose `next_tick_at` is due, using fixed sequences from `scenarios.py`. The clock is injected, so tests do not sleep. State is persisted, so restarts are safe. Detection timing is therefore exact; for example, `test_detection_is_deterministic_and_after_two_failed_probes` asserts 3.0 s.

## 7. Reset isolation

`origin` on rows, `simulation_run_id` with `ON DELETE CASCADE`, and `seed.restore_seed_baseline()`. `simulation.reset_all()` deletes simulation runs and simulation-origin rows, then re-applies seed values to seed-owned fields. Imported and local-lab rows survive (`test_reset_is_isolated_to_simulation_data`).

## 8. Topology trace never infers connectivity

`backend/app/services/topology.py: trace()` follows only `cable_connections` rows and explicit `pass_through_id` pairs on patch panels. When no cable is modeled it stops with "nothing beyond is inferred". It reports `complete` only when the path ends on a non-patch-panel device.

## 9. Power independence analysis

`backend/app/services/topology.py: power_analysis()` reports:

- `missing_power_connection` when an input has no outlet,
- `upstream_unknown` when any feed's `upstream_source` is NULL,
- `shared_upstream` when all connected inputs trace to the same upstream source, regardless of PDU names.

Independence is claimed only when there are at least 2 inputs, all connected, with known and distinct upstream sources. The seed includes `nl-r02-pdu-b`, which is named "B" but is fed from UPS-A, to show the difference.
