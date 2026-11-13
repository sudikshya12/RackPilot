# Case Study 2: Server Intake & Acceptance

*RackOps Lab, an independent interview lab by [Candidate Name].*

## 1. Problem

A new server has to match its build sheet before it is handed to provisioning. A missing DIMM pair or a 1G optic in a 10G slot is cheap to catch at intake and expensive to find in production.

## 2. Relevance to data center operations

Intake and burn-in validation are core technician tasks. A defensible accept or reject decision needs explicit expected values, recorded observations and evidence, and results that cannot be edited afterwards.

## 3. Implemented workflow

- **Intake record.** Asset tag, serial, hostname, the expected CPU, memory (GiB), storage, NIC count and data-link speed (Mb/s), the intended rack and U (validated against occupied units), the profile, and the source.
- **Run.** The run snapshots the expected configuration, the profile and the observations at start. The backend job runner then executes 10 modular checks: identity, CPU, memory, storage, disk health, NIC inventory, link speed, connectivity, kernel errors, and Redfish health (optional).
- **Results.** Each check returns PASS, FAIL, MANUAL_REVIEW, UNSUPPORTED, SKIPPED or ERROR, with expected value, observed value, unit, evidence, execution time, check version and source.
- **Disposition rules** (`acceptance/checks.py`):
  - a required FAIL gives **FAIL**;
  - a required UNSUPPORTED, SKIPPED, ERROR or unresolved MANUAL_REVIEW gives **MANUAL REVIEW**;
  - otherwise **PASS**.
  Optional checks stay visible and never decide the outcome.
- **Manual review** decisions (accept or reject, with a note and the reviewer) are stored as separate annotations. The stored results never change.
- **Corrections and re-tests.** Simulated corrections are labeled `SIMULATED`. Each re-test is a new immutable run, and any two runs can be diffed side by side.
- **Reports.** A printable HTML report and a JSON export, both rendered from the persisted run. A provisioning handoff checklist is gated on PASS.
- **Collectors.**
  - the simulator,
  - an uploaded Linux collector run (`collectors/rackops_collect.py`, read-only, labeled `LOCAL_LAB` or `IMPORTED_SAMPLE`),
  - a Redfish fixture (`IMPORTED_SAMPLE`),
  - an optional live Redfish endpoint (GET only, TLS verified).

## 4. Architecture

`services/acceptance.py` (intake, runs, corrections, review, handoff, compare, upload sanitizing) · `acceptance/checks.py` · `collectors/redfish.py` · `templates/acceptance_report.html`. UI: `pages/AcceptanceQueue.tsx`, `pages/AcceptanceDetail.tsx`, `pages/Report.tsx`.

## 5. Demonstration

Guided demo **Reject and re-test a misconfigured server**:

1. Review INT-0001: lab-srv-06 is expected to have 128 GiB and a 10 Gb/s data link.
2. Run #1 is **FAIL**: memory 64 GiB and data link 1000 Mb/s.
3. Record two labeled simulated corrections.
4. Run #2 is **PASS**.
5. Compare the two runs. Only memory and link speed changed, and the corrections between the runs are listed.
6. Open the report.

## 6. Collected results

Produced by running the application. Run outcomes, by source, are on **Acceptance** and on the case-study page. The seeded hardware models make the demo outcomes deterministic: INT-0001 fails, then passes after both corrections; INT-0002 goes to MANUAL REVIEW because disk health is unsupported and a corrected AER line needs review.

## 7. Limitations

- The simulator's hardware model is hand-written. Real `dmidecode` and `lsblk` output varies by vendor.
- The Linux collector reads kernel-visible MemTotal (the check applies a 4 % tolerance). SMART and dmesg need root, and without root they are reported as UNSUPPORTED.
- The Redfish fixtures follow the DMTF resource shape, but real BMCs populate different properties. `Oem.RackOpsRole` exists only in this lab.
- No burn-in or stress tests are run (deliberately not automated).

## 8. Candidate contribution

[To be written by the candidate]

## 9. Lessons learned

[To be written by the candidate]

## 10. Reproduction

```bash
cd backend && uv sync && uv run alembic upgrade head && uv run python -m app.seed
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
cd ../frontend && npm ci && npm run dev    # http://127.0.0.1:5173/acceptance
cd ../backend && uv run pytest tests/test_acceptance.py
# On a Linux machine under test:
python3 collectors/rackops_collect.py --data-iface eth1 > observations.json
```
