# Test Results

Only tests that were actually executed are reported as passing.

## Backend (pytest)

```bash
cd backend && uv run pytest
```

**Result (executed during build): 40 passed.** That is 38 test functions; one is parametrized over 3 scenarios.

| File | What it verifies |
|---|---|
| `tests/test_incidents.py` | Detection is deterministic and fires after 2 failed probes (3.0 s latency; latency NULL while down, never 0). Resolution requires a successful verification after the latest repair, and immediate post-repair verification cannot pass. An incorrect hypothesis does not resolve and returns the incident to investigating. Unknown onset gives an unavailable detection latency and is excluded from aggregates. Reopening preserves history. Simulated and LOCAL_LAB metrics are aggregated separately, with no combined aggregate. Evidence carries provenance and tracks state. Invalid transitions are rejected. `fs-full`, `cpu-contention` and `nic-down` each recover end to end. |
| `tests/test_acceptance.py` | A hardware mismatch fails (64 GiB, 1000 Mb/s). Missing required evidence cannot pass (MANUAL REVIEW, then accepted only after manual reviews, while the stored disposition is unchanged). Disposition rules. A missing section is UNSUPPORTED, not zero. A re-test creates a new immutable run and the diff is correct. Reports preserve source and timestamps and ignore later intake edits. Redfish fixture mode works and the client exposes no mutating methods. Uploads are sanitized, size-limited (413) and schema-checked (422). |
| `tests/test_inventory_topology.py` | Reservations cannot exceed stock. An incompatible part needs a reviewed exception. Consumption is atomic (a failure rolls back everything) and cannot repeat. Repeated API requests with an Idempotency-Key do not double-consume. Asset transitions are validated, require information, and are audited. A return needs a reference before shipping. Rack overlap and out-of-bounds placements are rejected. Invalid cable endpoints are rejected (missing, occupied, incompatible) and unlabeled cables warn. Traces follow only modeled links. Shared upstream, missing connection and unknown upstream are flagged. The cable audit finds the seeded defects. |
| `tests/test_demos.py` | Each of the 3 guided demos completes end to end through `next_step`. Reset is isolated to simulation data (imported incidents, operator stock receipts and LOCAL_LAB metrics survive; demo consumption is reverted). Demo restart is repeatable. |
| `tests/test_api.py` | OpenAPI paths exist and the error envelope is consistent. Overview counts match the underlying records. Settings never return credentials. The Alertmanager webhook is disabled by default. Public preview blocks mutations. |

## Frontend / E2E (Playwright)

```bash
cd frontend && npx tsc --noEmit -p .   # typecheck: clean
cd frontend && npx vitest run          # 5 passed (component and format tests)
cd frontend && npm run contrast        # all 20 token pairs meet WCAG AA (4.5:1)
cd frontend && npx playwright test     # 47 passed
```

**Result (executed during build): 47 passed.** Playwright starts an isolated backend (port 8001, `backend/data/e2e.db`) and frontend (port 5174).

| Spec | What it verifies |
|---|---|
| `e2e/demos.spec.ts` | All three guided demos complete end to end through the on-screen control bar. Demo 1: a failed verification is kept in history, the final verification passes, and detection latency is 3.0 s. Demo 2: runs are FAIL then PASS, and the comparison and JSON report are correct. Demo 3: on-hand stock drops by 1, nothing is left reserved, the RMA is visible, and the device audit trail is complete. Reset keeps imported samples. A completed demo collapses to a small dismissible card. |
| `e2e/responsive.spec.ts` | 13 pages × desktop 1440, tablet 834 and mobile 390: each renders with zero horizontal overflow, with a full-page screenshot. Keyboard: the skip link is the first Tab stop, and ⌘/Ctrl+K search works. The legacy `/operations` route redirects to `/`. Dashboard metrics match `/api/overview` and link to the filtered views. Candidate and interview text is absent from operational pages. |

## Screenshots

Saved by the responsive spec to `docs/screenshots/{desktop,tablet,mobile}-<page>.png`: 39 files, regenerated on every run. They were inspected manually during the build, which led to fixes for header overflow on mobile, grid columns sizing to content, case-study sections left invisible by scroll-triggered animation, and a modal drawer blocking the demo controls.
