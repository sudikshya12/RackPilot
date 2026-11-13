# Case Study 1: Incident Detection & Recovery

*RackOps Lab, an independent interview lab by [Candidate Name]. All data is synthetic or labeled by source.*

## 1. Problem

When a service or host component fails, a technician has to detect it quickly, collect evidence, tell a correct fix apart from a plausible wrong one, and **prove** that the system has recovered. Closing a ticket because a command ran is not proof.

## 2. Relevance to data center operations

Technicians are often the first responders for host-level faults: stopped services, full disks, runaway processes, lost links. Structured evidence, explicit hypotheses and verified recovery shorten escalations and keep the timestamps honest for MTTR reporting.

## 3. Implemented workflow

Lifecycle: **Detected → Acknowledged → Investigating → Repair applied → Verification → Resolved** (reopen returns to Investigating).

- Four reproducible scenarios: `svc-stopped`, `fs-full`, `cpu-contention`, `nic-down`. A fifth, `psu-failure`, is used by Project 3. All are deterministic; see [simulation-model.md](../simulation-model.md).
- Twelve evidence collectors. Each record carries its output, an interpretation, its limitations, the source, and the collection time.
- Hypotheses, each with a **discriminating check**, are marked supported or refuted separately from the evidence.
- Every scenario includes a deliberately wrong repair. Applying it makes verification fail, and the incident returns to Investigating.
- **Resolution gate.** `resolve()` accepts only a verification that passed and was executed after the most recent repair.
- Metrics per incident and per source:
  - detection latency = detected − known onset (unavailable when onset is unknown),
  - acknowledgment latency,
  - MTTR, defined as detection to verified recovery.
- A post-incident summary is generated from stored records, with Markdown and Jira-payload exports.
- An optional **live lab** (`LOCAL_LAB`): a real HTTP process owned by the lab, on `127.0.0.1`. The operator can stop it from Settings; it is then detected by real probes and verified by real HTTP checks.

## 4. Architecture

`services/incidents.py` (lifecycle, gate, metrics, summary) · `services/scenarios.py` + `services/simulation.py` (deterministic engine) · `collectors/sim_evidence.py` · `livelab/manager.py` · `runner.py` (job runner) · SSE via `stream_events`. UI: `pages/IncidentQueue.tsx`, `pages/IncidentWorkspace.tsx`.

## 5. Demonstration

Guided demo **Restore a failed service** (`/demo`):

1. Healthy baseline.
2. Fault injected.
3. Detection after 2 failed probes.
4. Acknowledge.
5. Collect evidence.
6. Bounce `eth1`; verification **fails**.
7. Start the unit.
8. Wait for 2 healthy probes; verification passes.
9. Resolve and read the summary.

## 6. Collected results

Results are produced by running the application. They are shown on **Incidents → Recovery measurements** and on the case-study page, split by source. Nothing is pre-filled.

Deterministic by construction: in `svc-stopped`, the fault is injected at probe 4 and detected at probe 5 with a 3 s interval, so **detection latency is 3.0 s** (asserted in `tests/test_incidents.py`). In `nic-down`, onset is unknown and detection latency is *Unavailable*. Acknowledgment latency and MTTR depend on operator actions and are recorded per drill.

No improvement percentages are reported. A comparison would need a recorded baseline and later runs of the same scenario.

## 7. Limitations

- Simulated evidence is rendered from scenario state, not collected from hardware.
- Live-lab coverage is limited to one lab-owned HTTP process. It does not inspect or change host services.
- Alertmanager-sourced incidents have no collectors. Their verification relies on a later "resolved" notification.

## 8. Candidate contribution

[To be written by the candidate]

## 9. Lessons learned

[To be written by the candidate]

## 10. Reproduction

```bash
cd backend && uv sync && uv run alembic upgrade head && uv run python -m app.seed
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
cd ../frontend && npm ci && npm run dev    # http://127.0.0.1:5173/demo
cd ../backend && uv run pytest tests/test_incidents.py
```
