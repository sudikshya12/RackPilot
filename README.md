# RackOps Lab

**An independent interview lab for data center operations.** It is a working, locally runnable tool with three projects that share one modeled lab:

| # | Project | What it demonstrates | Guided demo |
|---|---------|----------------------|-------------|
| 1 | **Incident Detection & Recovery** | Deterministic fault → detection → evidence → hypotheses → repair → **verification gate** → post-incident summary | Restore a failed service |
| 2 | **Server Intake & Acceptance** | Expected-vs-observed checks, FAIL vs MANUAL REVIEW rules, immutable runs, re-test diff, printable report | Reject and re-test a misconfigured server |
| 3 | **Rack, Cabling & Asset Lifecycle** | Rack elevation, cable trace, power-independence analysis, transactional spares, RMA, full audit trail | Replace a failed PSU and reconcile inventory |

> This is an independent interview lab, not a production system, and it is not affiliated with any employer. All names, serial numbers and addresses are synthetic. Every measurement is labeled **SIMULATED**, **LOCAL LAB** or **IMPORTED SAMPLE**, and these sources are never combined in one aggregate.

---

## Quick start (local, no accounts needed)

Prerequisites: Python 3.12 with [uv](https://docs.astral.sh/uv/), and Node 20+.

```bash
# 1) Backend: API on http://127.0.0.1:8000 (OpenAPI docs at /api/docs)
cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.seed            # repeatable; no-op if already seeded
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2) Frontend: UI on http://127.0.0.1:5173 (proxies /api to the backend)
cd frontend
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. The home page is the operations dashboard. Use **Run demo** (or **Demonstrations** in the sidebar) to start a guided walkthrough. Project background and case studies are under **About & Documentation**.

To rebuild the database from scratch (this deletes *all* records, including imported ones): `uv run python -m app.seed --reset`.
To reset only the demo and drill data, use **Demonstrations → Reset all simulation data**. Imported and local-lab records are kept.

### Docker Compose (alternative)

```bash
cp .env.example .env                               # optional
docker compose up --build                          # UI at http://127.0.0.1:8080
docker compose --profile monitoring up --build     # + Prometheus, Alertmanager, Node Exporter
```

All ports are published on `127.0.0.1` only. *Note: the Compose files were written and YAML-validated but not executed in the build environment, which had no Docker. See [docs/limitations.md](docs/limitations.md).*

---

## The three demo journeys (2–3 minutes each)

Start any of them from **/demo**. A compact control bar at the bottom shows the step and progress, with **Next step**, **Pause**, an expandable step list (**View**, **Restart**), and **Exit** (Shift+N advances). When a demo finishes, the bar becomes a small dismissible card with **View results** and **Close**. Every step runs the real backend workflow, and progress is derived from stored records. You can also do each step by hand in the normal UI.

1. **Restore a failed service**: the baseline probes run, the simulator stops `inventory-api` on lab-srv-02, and two failed probes (3 s interval) raise INC-xxxx. Acknowledge it and collect evidence ("connection refused", unit `inactive (dead)` after SIGTERM, scripted `systemctl stop` in the journal). Then **try the wrong fix** (bounce eth1): verification FAILS and the incident returns to investigating. Start the unit, wait for 2 healthy post-repair probes, verify, resolve, and open the summary.
2. **Reject and re-test**: lab-srv-06 is expected to have 128 GiB and a 10 Gb/s link. It is observed at 64 GiB and 1 Gb/s, so the run FAILS. Record two labeled *simulated* corrections. Run #2 PASSES as a new record, with run #1 kept unchanged. Compare them side by side, then open the HTML report and JSON export.
3. **Replace a failed component**: PSU2 on lab-srv-04 goes Critical (Redfish-shaped fixture). Collect evidence: the feed is present, so it is not a feed problem. Find a compatible spare (NL-PSU-800P; the 550 W switch PSU is flagged as incompatible) and reserve it. Consuming the reservation is one atomic transaction covering the ledger, the replacement asset, the failed-part quarantine, and the incident repair. Open the return record, re-check health, resolve, and read the audit trail.

The full 5-minute interview script, with talking points, is in [docs/demo-script.md](docs/demo-script.md).

---

## Tests (executed during the build)

```bash
cd backend && uv run pytest                # 40 passed: workflow + integrity tests
cd frontend && npx vitest run              # 5 passed: component/format tests
cd frontend && npx playwright test         # 47 passed: 3 demo journeys, reset isolation, completed-demo card,
                                           #   dashboard metrics/links, legacy route redirect, no candidate text,
                                           #   13 pages x 3 viewports with zero horizontal overflow, keyboard access
cd frontend && npm run contrast            # WCAG AA check of the color tokens
```

Playwright starts its own isolated backend (port 8001, `backend/data/e2e.db`) and frontend (port 5174), and saves screenshots to `docs/screenshots/`. Results: [docs/test-results.md](docs/test-results.md).

---

## Where things are

| Path | What |
|------|------|
| `backend/app/models.py` | Shared data model: 30+ tables with provenance, constraints, and indexes |
| `backend/app/services/` | Incidents, simulation engine, scenarios, acceptance, topology, inventory, demos |
| `backend/app/acceptance/checks.py` | Modular checks and disposition rules |
| `backend/app/collectors/` | Simulated evidence, read-only Redfish adapter |
| `backend/app/livelab/` | Optional **real** service-stop drill against a lab-owned process on 127.0.0.1 |
| `backend/alembic/` | Migrations |
| `collectors/rackops_collect.py` | Read-only Linux collector for real hardware (run by the operator, then upload the JSON) |
| `frontend/src/` | React UI (pages, rack elevation, cable trace, demo dock) |
| `docs/` | Architecture, data dictionary, simulation model, runbooks, case studies, demo script, limitations |

### Edit the candidate profile

Go to **Settings → Candidate profile** in the UI. That holds the name, headline, summary, links, and the operator name recorded on actions. The author details appear only on **About & Documentation**, not in the operational interface. *Candidate contribution* and *Lessons learned* are edited on each case-study page (**/projects/…**). They are stored in the database and start empty on purpose: this portfolio does not generate personal reflections.

### Connect real lab equipment (optional)

* **Live service drill (real, LOCAL LAB):** go to Settings → Live lab and enable it. The backend starts its own tiny HTTP target on `127.0.0.1:18081`. "Stop target" causes a real outage, real probes detect it, and recovery is verified with real HTTP checks. Host services are never touched.
* **Linux server acceptance:** on the machine under test, run `python3 collectors/rackops_collect.py --data-iface eth1 > obs.json`, ideally with `sudo` so SMART and dmesg are included. Upload the file on the intake page as *LOCAL LAB* and run with the *Uploaded Linux collector output* collector.
* **Redfish BMC (read-only GETs):** set `RACKOPS_REDFISH_URL`, `_USERNAME` and `_PASSWORD` in `.env`. TLS verification is on by default. There are no power or firmware actions.
* **Prometheus/Alertmanager:** use the `monitoring` Compose profile and set `RACKOPS_ALERTMANAGER_WEBHOOK_ENABLED=true` plus a token.

## Documentation

[Architecture](docs/architecture.md) · [Implementation plan & decisions](docs/implementation-plan.md) · [Data dictionary](docs/data-dictionary.md) · [Simulation model](docs/simulation-model.md) · [Technical walkthrough](docs/technical-walkthrough.md) · [Runbooks](docs/runbooks/) · [Case studies](docs/case-studies/) · [Demo script](docs/demo-script.md) · [Evidence export](docs/evidence-export.md) · [What the candidate should understand](docs/candidate-understanding.md) · [Known limitations](docs/limitations.md) · [Test results](docs/test-results.md)
