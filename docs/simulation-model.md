# Simulation Model

All simulated behavior is deterministic and owned by the backend. The same scenario always produces the same probe values, the same evidence text (apart from timestamps) and the same detection timing. Nothing in the simulation uses a random number generator.

Code: `backend/app/services/simulation.py` (engine), `backend/app/services/scenarios.py` (scenarios), `backend/app/collectors/sim_evidence.py` (evidence), `backend/app/services/demos.py` (guided demos).

## Engine

- **State in the database.** Each run is a `simulation_runs` row. Its `state` JSON holds the modeled host: service, filesystem, CPU, interface, PSUs, probe counter, consecutive failures, healthy probes since the last repair, and the list of repairs. Restarting the backend resumes from the stored state.
- **`tick(db, now)`** is a pure function of database state and the supplied clock. The job runner calls it every second with the wall clock. Tests call it with an injected clock (`tests/conftest.py: Clock`).
- **Probe interval** is `RACKOPS_SIM_PROBE_INTERVAL_SECONDS` (default **3 s**). A run is due when `next_tick_at <= now`. Each probe advances `next_tick_at` by exactly one interval.
- **Catch-up.** After downtime, at most `MAX_CATCH_UP = 3` missed probes are replayed. The schedule is then re-anchored to `now + interval` instead of replaying a long outage.
- **Safety cap.** After `MAX_PROBES = 400` probes the run pauses itself, so a forgotten drill does not grow without bound.

### Phases

1. **baseline.** Healthy probes for `baseline_probes`.
2. **fault.** On the first probe after the baseline, `inject(state)` applies the fault and `state.fault_at` is recorded. Each probe evaluates the scenario's `failing(state)` predicate and counts consecutive failures.
3. **incident.** When consecutive failures reach `detect_after_failed` (2 in every scenario), an incident is created with `detected_at` = that probe's timestamp, and the run moves to `awaiting_operator`. Probes continue. After a repair, each non-failing probe increments `healthy_since_repair`; any failing probe resets it to 0.
4. **completed.** Set when the incident is resolved. Reopening the incident moves the run back to `awaiting_operator`.

Every probe writes `metric_observations` rows labeled `SIMULATED` with `source_id = sim:<scenario>:<run>`, and updates the device's `health` (`critical` or `degraded` while failing, `healthy` otherwise).

### Fixed sequences

| Name | Values | Used for |
|---|---|---|
| `LATENCY_MS` | 41, 43, 40, 44, 42, 45, 41, 43, 42, 40 | healthy `/health` latency (ms) |
| `CPU_BASE` | 18, 22, 20, 19, 23, 21, 20, 22 | baseline CPU (%) |
| `CPU_CONTENDED` | 96, 98, 97, 99, 98, 97 | contended CPU (%) |
| `LATENCY_CONTENDED` | 910, 1240, 1180, 1320, 1270, 1190 | latency under contention (ms) |
| `_FS_FILL` | 36.4, 38.6, 39.9, 40.0 GiB of 40 GiB | filesystem fill progression |

Values are indexed by probe number (`n % len`). When the service is down, latency is `NULL` (not collected), not 0.

## Scenarios

`REQUIRED_HEALTHY_PROBES = 2` applies to every scenario. Verification adds a `post_repair_samples` check that passes only after at least one repair has been recorded and at least 2 healthy probes have followed it. Running verification immediately after a repair therefore cannot pass.

| Key | Device | Baseline probes | Inject | Detection rule | Onset |
|---|---|---|---|---|---|
| `svc-stopped` | lab-srv-02 | 4 | `inventory-api` unit inactive, stopped by `maint-cleanup.sh` | GET `/health` fails on 2 consecutive probes | Known. Detection latency is 3.0 s by construction: fault at probe 4, detection at probe 5. |
| `fs-full` | lab-srv-03 | 3 | `/srv/scratch` begins filling (91 % at onset, then 96.5 %, 99.75 %, 100 %) | `fs_used_pct ≥ 95` on 2 consecutive probes | Known. Detected 2 probes after onset (6 s). |
| `cpu-contention` | lab-srv-05 | 3 | runaway `batch-reindex` (32 workers) | CPU > 90 % and latency > 500 ms on 2 consecutive probes | Known (3 s). |
| `nic-down` | lab-srv-01 | 3 | `eth1` loses carrier | `iface_oper_up == 0` on 2 consecutive probes | **Unknown.** Link history is not retained, so `fault_onset_at` is NULL and detection latency is "Unavailable". |
| `psu-failure` | lab-srv-04 | 3 | PSU2 `Health=Critical` | Redfish (fixture) PSU2 health ≠ OK on 2 consecutive polls | Known (3 s). |

### Hypotheses, repairs and verification

| Scenario | Hypotheses (key) | Repair options | Verification checks |
|---|---|---|---|
| `svc-stopped` | `svc_stopped`, `network_path`, `host_down` | `restart_service` (correct); `bounce_iface` (**deliberately wrong**: tests the network hypothesis and does not restore the service) | unit active; TCP 8080 listening; GET /health 200; post-repair samples |
| `fs-full` | `log_growth`, `deleted_open` | `purge_debug_logs` (correct, frees space to 14.7 GiB); `restart_writer` (wrong: frees nothing) | utilization < 85 %; test write succeeds; post-repair samples |
| `cpu-contention` | `runaway_job`, `service_regression` | `stop_batch_job` (correct); `restart_service` (wrong) | CPU < 70 %; latency < 200 ms; runaway process absent; post-repair samples |
| `nic-down` | `cable_unseated`, `switch_port`, `nic_fault` | `reseat_cable` (correct); `restart_networking` (wrong: cannot restore a physical carrier) | carrier LOWER_UP; 10000 Mb/s full duplex; switch port up (modeled); post-repair samples |
| `psu-failure` | `psu_failed`, `feed_loss` | `replace_psu2`, recorded **only** through the spare-parts workflow. A direct repair returns `spare_workflow_required`. | PSU2 health OK; redundancy restored; both PSUs report input; post-repair samples |

A wrong repair moves the incident to `repair_applied`. Verification then fails on a non-sample check, and `verify()` moves the incident back to `investigating`. The incident is never resolved by a wrong fix.

## Evidence rendering

`sim_evidence.collect(collector, state, now, fault_at)` renders realistic command output from the **current** run state, so evidence always agrees with the metrics. Before a repair, `systemctl status` shows `inactive (dead)`; after a correct repair it shows `active (running)` with a new PID. Each item returns:

- `command`: display string only, never executed.
- `output`: verbatim text.
- `observations`: structured facts.
- `interpretation`: what the output shows, not a diagnosis.
- `limitations`: e.g. "Simulated output rendered from scenario state; not collected from hardware."

There are 12 collectors: `systemctl_status`, `journalctl`, `filesystem_usage`, `process_info`, `listening_sockets`, `interface_counters`, `service_reachability`, `http_check`, `switch_port`, `redfish_power`, `sel_log`, `pdu_outlet`. Each scenario marks its runbook-recommended collectors as primary. Addresses use the RFC 5737 documentation ranges.

## Acceptance simulator

Each seeded intake carries a `simulated_hardware` model in the same shape the checks consume (`identity`, `cpu`, `memory`, `storage`, `disk_health`, `nics`, `connectivity`, `kernel_errors`, `redfish`).

- **INT-0001 / lab-srv-06.** Expected 128 GiB and a 10 Gb/s data link. Modeled with 4 × 16 GiB (64 GiB) and the data NIC at 1000 Mb/s behind a 1000BASE-SX SFP. The first run is **FAIL**.
- **INT-0002 / lab-srv-07.** Matches the build sheet, but disk health is `_unsupported` (no root) and there is one corrected AER line. The run is **MANUAL REVIEW**.

Corrections (`services/acceptance.py: CORRECTIONS`) are explicit records labeled `SIMULATED`: `install_dimms` (adds B1–B4) and `replace_transceiver` (data NIC to 10 Gb/s). Each changes only the simulator model, is audited, and is listed in the next run's `corrections_before_run`. Earlier runs are not modified.

## Guided demos

`services/demos.py` defines three demos: `restore-service`, `acceptance-retest` and `replace-component`. Each demo is a `simulation_runs` row with a `demo_key`. **Step completion is derived from stored records**, for example incident status, the number of evidence items, a failed verification, a reservation with status `consumed`, or a return record for `NL-AST-P04B`. A step is therefore complete whether the operator did it in the normal UI or pressed **Next step**. "Next step" calls the same service functions as the UI, with the same validation. Review-only steps record `viewed` in the run state. Steps marked `auto` complete through probes.

## Reset isolation

See [architecture.md#reset-semantics](architecture.md#reset-semantics). In short: deleting a simulation run cascades to everything it owns, `origin = 'simulation'` rows are removed, the seed baseline is re-applied, and imported, local-lab and operator rows are untouched.
