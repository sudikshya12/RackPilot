# Known Limitations

These are stated plainly so that nothing in the portfolio overstates what was built or measured.

## Data and evidence

- **Simulated evidence.** Default incident evidence and acceptance observations come from deterministic scenario state and fixtures, not from hardware. Every such record is labeled `SIMULATED`.
- **Modeled topology.** Racks, cables, PDUs and feeds are hand-modeled synthetic documentation, labeled "Modeled lab topology". Nothing is discovered (no LLDP, SNMP or NetBox API).
- **Redfish fixtures are not real BMCs.** They are hand-written in the DMTF resource shape. Real BMCs populate different properties and vendor `Oem` sections, and need authentication and TLS. `Oem.RackOpsRole` is lab-specific. The live Redfish mode is implemented as GET only but was not tested against real hardware.
- **Live lab scope.** The `LOCAL_LAB` incident path covers one lab-owned HTTP process on `127.0.0.1`. It never inspects or modifies host services, filesystems or interfaces, by design.
- **Linux collector.** It reads kernel-visible memory (with a tolerance), not DIMM inventory. SMART/NVMe health and `dmesg` need root; without root they are reported as UNSUPPORTED, so the run goes to MANUAL REVIEW. It is Linux only.

## Platform

- **Single user, no authentication.** SQLite with write serialization (`BEGIN IMMEDIATE`). Concurrency was tested only to the extent that SQLite serializes writers; no multi-user load testing was done. A public deployment must use `RACKOPS_PUBLIC_PREVIEW=true` (read-only) or add authentication.
- **Docker.** The Docker Compose file and the optional Prometheus / Alertmanager / Node Exporter profile were written but **not executed** in the build environment, because Docker was unavailable there. The documented local commands (uv and npm) are the tested path.
- **Integrations.** NetBox is a file-based JSON import only. Jira is a file export only. The Alertmanager webhook is disabled by default and was exercised with a bundled sample payload. No notification channels are implemented.

## Scope boundaries

- **Power analysis** is a documentation consistency check, not an electrical design certification. Loads are modeled estimates.
- **Physical work is simulated.** Workflow completion (reservation, consumption, return record) is real record-keeping. The physical replacement is not.
- **Reset scope.** Demo reset removes simulation-owned records and restores the seed baseline for seed-owned fields only. Operator edits such as cable labels, placements and received stock persist until `uv run python -m app.seed --reset`.
- **No measured improvements.** No before/after comparisons are reported. Aggregates appear only for incidents that actually exist in the database, per source.
- **Not automated, by design.** Disk wipes, firmware updates, host network changes, power cycles and stress tests.
