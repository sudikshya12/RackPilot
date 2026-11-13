"""Deterministic incident scenarios.

Each scenario is a pure description:

* ``initial_state``: healthy simulated host state,
* ``inject``: the state change that represents the fault,
* ``metrics(state, n)``: probe ``n`` observations, taken from fixed sequences (no randomness),
* ``failing(state)``: the detection rule's predicate,
* ``repairs``: the corrective actions an operator may apply. Some are deliberately wrong,
  so an incorrect hypothesis can be tested without falsely resolving the incident,
* ``verify(state, healthy_probes_since_repair)``: the checks that prove recovery.

Evidence collectors render text from the *same* state, so evidence stays coherent with the metrics.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

# Fixed sequences indexed by probe number — never random.
LATENCY_MS = [41, 43, 40, 44, 42, 45, 41, 43, 42, 40]
CPU_BASE = [18, 22, 20, 19, 23, 21, 20, 22]
CPU_CONTENDED = [96, 98, 97, 99, 98, 97]
LATENCY_CONTENDED = [910, 1240, 1180, 1320, 1270, 1190]

REQUIRED_HEALTHY_PROBES = 2


def base_state(host: str) -> dict[str, Any]:
    return {
        "host": host,
        "service": {
            "name": "inventory-api",
            "unit": "inventory-api.service",
            "active": True,
            "pid": 2481,
            "port": 8080,
            "stopped_by": None,
        },
        "fs": {"mount": "/srv/scratch", "device": "/dev/nvme1n1p1", "size_gib": 40.0, "used_gib": 18.2, "fill_step": 0},
        "cpu": {"cores": 32, "runaway": False},
        "iface": {"name": "eth1", "carrier": True, "speed_mbps": 10000, "switch_port": "lab-sw-01 Eth1/7", "switch_port_up": True},
        "psu": {"PSU1": "OK", "PSU2": "OK"},
        "probe": 0,
        "healthy_since_repair": 0,
        "repairs": [],
    }


@dataclass
class RepairOption:
    key: str
    label: str
    description: str
    effect: Callable[[dict], None]
    tests_hypothesis: Optional[str] = None


@dataclass
class Scenario:
    key: str
    title: str
    project: str
    device: str
    severity: str
    runbook: str
    symptom: str
    detection_rule: str
    baseline_probes: int
    detect_after_failed: int
    onset_known: bool
    inject: Callable[[dict], None]
    failing: Callable[[dict], bool]
    metrics: Callable[[dict, int], list[tuple[str, Optional[float], str, dict]]]
    verify: Callable[[dict], list[dict]]
    hypotheses: list[dict]
    repairs: list[RepairOption]
    primary_collectors: list[str]
    root_cause: str
    onset_note: str = ""
    progress: Optional[Callable[[dict], None]] = None  # per-probe fault evolution
    extra: dict = field(default_factory=dict)

    def initial_state(self) -> dict:
        return base_state(self.device)


# --------------------------------------------------------------------------- helpers


def _probe_ok_check(state: dict) -> dict:
    n = state.get("healthy_since_repair", 0)
    return {
        "key": "post_repair_samples",
        "name": f"{REQUIRED_HEALTHY_PROBES} consecutive healthy probes after the repair",
        "passed": n >= REQUIRED_HEALTHY_PROBES and bool(state["repairs"]),
        "observed": f"{n} healthy probe(s) since last repair" if state["repairs"] else "No repair recorded yet",
        "expected": f">= {REQUIRED_HEALTHY_PROBES}",
    }


def _fs_pct(state: dict) -> float:
    fs = state["fs"]
    return round(100.0 * fs["used_gib"] / fs["size_gib"], 1)


# --------------------------------------------------------------------------- scenario 1: service stopped


def _svc_inject(s):
    s["service"].update(active=False, stopped_by="maint-cleanup.sh (uid 1004)")


def _svc_failing(s):
    return not s["service"]["active"]


def _svc_metrics(s, n):
    up = s["service"]["active"]
    return [
        ("service_up", 1.0 if up else 0.0, "bool", {"service": "inventory-api"}),
        ("http_latency_ms", float(LATENCY_MS[n % len(LATENCY_MS)]) if up else None, "ms", {"probe": "GET /health"}),
    ]


def _svc_verify(s):
    svc = s["service"]
    return [
        {"key": "unit_active", "name": "systemd unit is active (running)", "passed": svc["active"],
         "observed": "active (running)" if svc["active"] else "inactive (dead)", "expected": "active (running)"},
        {"key": "port_listening", "name": f"TCP {svc['port']} is listening", "passed": svc["active"],
         "observed": "LISTEN 0.0.0.0:8080" if svc["active"] else "no listener", "expected": "LISTEN"},
        {"key": "http_health", "name": "GET /health returns 200", "passed": svc["active"],
         "observed": "HTTP 200" if svc["active"] else "connection refused", "expected": "HTTP 200"},
        _probe_ok_check(s),
    ]


def _restart_service(s):
    s["service"].update(active=True, pid=s["service"]["pid"] + 1113, stopped_by=None)


def _bounce_iface(s):
    s["iface"]["carrier"] = True  # no effect on a stopped service


SVC_STOPPED = Scenario(
    key="svc-stopped",
    title="inventory-api stopped responding",
    project="incident-recovery",
    device="lab-srv-02",
    severity="critical",
    runbook="service-not-responding",
    symptom="HTTP health probe to inventory-api on lab-srv-02 fails (connection refused).",
    detection_rule="GET http://lab-srv-02:8080/health fails on 2 consecutive probes (probe interval 3 s, simulated)",
    baseline_probes=4,
    detect_after_failed=2,
    onset_known=True,
    onset_note="Fault onset is known because the simulator injected it.",
    inject=_svc_inject,
    failing=_svc_failing,
    metrics=_svc_metrics,
    verify=_svc_verify,
    hypotheses=[
        {"key": "svc_stopped", "statement": "The inventory-api process is not running (unit stopped or crashed).",
         "discriminating_check": "systemctl status shows unit state; ss -ltnp shows whether :8080 has a listener."},
        {"key": "network_path", "statement": "The data network path to lab-srv-02 is down (link, switch port, or cabling).",
         "discriminating_check": "ip -s link shows carrier and incrementing counters; other services on the host remain reachable."},
        {"key": "host_down", "statement": "The whole host is down or hung.",
         "discriminating_check": "Management interface responds and journalctl shows recent entries."},
    ],
    repairs=[
        RepairOption("restart_service", "Start inventory-api.service",
                     "Simulated: systemctl start inventory-api.service, then confirm the unit is enabled.",
                     _restart_service, "svc_stopped"),
        RepairOption("bounce_iface", "Bounce data interface eth1",
                     "Simulated: ip link set eth1 down && ip link set eth1 up. Tests the network-path hypothesis.",
                     _bounce_iface, "network_path"),
    ],
    primary_collectors=["http_check", "systemctl_status", "journalctl", "listening_sockets", "interface_counters", "process_info"],
    root_cause="inventory-api.service was stopped by the maintenance cleanup script (maint-cleanup.sh) and was not restarted.",
)


# --------------------------------------------------------------------------- scenario 2: filesystem exhausted

_FS_FILL = [36.4, 38.6, 39.9, 40.0]


def _fs_inject(s):
    s["fs"]["fill_step"] = 0
    s["fs"]["used_gib"] = _FS_FILL[0]


def _fs_progress(s):
    fs = s["fs"]
    if fs.get("cleaned"):
        return
    fs["fill_step"] = min(fs["fill_step"] + 1, len(_FS_FILL) - 1)
    fs["used_gib"] = _FS_FILL[fs["fill_step"]]


def _fs_failing(s):
    return _fs_pct(s) >= 95.0


def _fs_metrics(s, n):
    return [("fs_used_pct", _fs_pct(s), "percent", {"mount": "/srv/scratch"}),
            ("fs_free_gib", round(s["fs"]["size_gib"] - s["fs"]["used_gib"], 1), "GiB", {"mount": "/srv/scratch"})]


def _fs_verify(s):
    pct = _fs_pct(s)
    return [
        {"key": "fs_below_threshold", "name": "/srv/scratch utilization below 85 %", "passed": pct < 85,
         "observed": f"{pct} %", "expected": "< 85 %"},
        {"key": "write_test", "name": "Test write to /srv/scratch succeeds", "passed": pct < 99.9,
         "observed": "wrote 1 MiB test file" if pct < 99.9 else "No space left on device", "expected": "write succeeds"},
        _probe_ok_check(s),
    ]


def _fs_cleanup(s):
    s["fs"].update(used_gib=14.7, cleaned=True)


def _fs_restart(s):
    s["service"]["pid"] += 7  # restarts service; does not free space


FS_FULL = Scenario(
    key="fs-full",
    title="Test filesystem /srv/scratch exhausted",
    project="incident-recovery",
    device="lab-srv-03",
    severity="major",
    runbook="filesystem-capacity",
    symptom="Filesystem /srv/scratch on lab-srv-03 above 95 % and writes failing with ENOSPC.",
    detection_rule="fs_used_pct{mount=/srv/scratch} >= 95 % on 2 consecutive probes (simulated)",
    baseline_probes=3,
    detect_after_failed=2,
    onset_known=True,
    onset_note="Fault onset is the moment the simulator started the runaway log writer.",
    inject=_fs_inject,
    progress=_fs_progress,
    failing=_fs_failing,
    metrics=_fs_metrics,
    verify=_fs_verify,
    hypotheses=[
        {"key": "log_growth", "statement": "A runaway writer (rotated debug logs) filled /srv/scratch.",
         "discriminating_check": "du -xh --max-depth=2 /srv/scratch identifies the largest directories."},
        {"key": "deleted_open", "statement": "Space is held by deleted-but-open files.",
         "discriminating_check": "lsof +L1 lists unlinked open files; df vs du discrepancy."},
    ],
    repairs=[
        RepairOption("purge_debug_logs", "Remove rotated debug logs in /srv/scratch/logs",
                     "Simulated: delete *.log.[0-9]* older than 1 day after confirming they are test artefacts.",
                     _fs_cleanup, "log_growth"),
        RepairOption("restart_writer", "Restart inventory-api to release file handles",
                     "Simulated: systemctl restart inventory-api. Tests the deleted-but-open hypothesis.",
                     _fs_restart, "deleted_open"),
    ],
    primary_collectors=["filesystem_usage", "journalctl", "process_info", "systemctl_status"],
    root_cause="Debug logging left enabled on a test job wrote rotated logs into /srv/scratch/logs until the filesystem filled.",
)


# --------------------------------------------------------------------------- scenario 3: CPU contention


def _cpu_inject(s):
    s["cpu"]["runaway"] = True


def _cpu_failing(s):
    return s["cpu"]["runaway"]


def _cpu_metrics(s, n):
    if s["cpu"]["runaway"]:
        return [("cpu_util_pct", float(CPU_CONTENDED[n % len(CPU_CONTENDED)]), "percent", {}),
                ("http_latency_ms", float(LATENCY_CONTENDED[n % len(LATENCY_CONTENDED)]), "ms", {"probe": "GET /health"})]
    return [("cpu_util_pct", float(CPU_BASE[n % len(CPU_BASE)]), "percent", {}),
            ("http_latency_ms", float(LATENCY_MS[n % len(LATENCY_MS)]), "ms", {"probe": "GET /health"})]


def _cpu_verify(s):
    r = s["cpu"]["runaway"]
    return [
        {"key": "cpu_below", "name": "CPU utilization below 70 % across samples", "passed": not r,
         "observed": "97 %" if r else "~21 %", "expected": "< 70 %"},
        {"key": "latency_ok", "name": "/health latency below 200 ms", "passed": not r,
         "observed": "~1200 ms" if r else "~42 ms", "expected": "< 200 ms"},
        {"key": "runaway_absent", "name": "batch-reindex process no longer running", "passed": not r,
         "observed": "present (PID 7730)" if r else "absent", "expected": "absent"},
        _probe_ok_check(s),
    ]


def _cpu_stop_job(s):
    s["cpu"]["runaway"] = False


CPU_CONTENTION = Scenario(
    key="cpu-contention",
    title="CPU contention degrading inventory-api",
    project="incident-recovery",
    device="lab-srv-05",
    severity="major",
    runbook="cpu-contention",
    symptom="Host CPU pinned near 100 % and inventory-api /health latency above 900 ms.",
    detection_rule="cpu_util_pct > 90 % AND http_latency_ms > 500 ms on 2 consecutive probes (simulated)",
    baseline_probes=3,
    detect_after_failed=2,
    onset_known=True,
    onset_note="Fault onset is the moment the simulator launched the runaway test job.",
    inject=_cpu_inject,
    failing=_cpu_failing,
    metrics=_cpu_metrics,
    verify=_cpu_verify,
    hypotheses=[
        {"key": "runaway_job", "statement": "A runaway batch job is consuming CPU.",
         "discriminating_check": "ps -eo pid,user,%cpu,etime,cmd --sort=-%cpu shows top consumers and their age."},
        {"key": "service_regression", "statement": "inventory-api itself regressed and is spinning.",
         "discriminating_check": "Per-process CPU: is the top consumer inventory-api or something else?"},
    ],
    repairs=[
        RepairOption("stop_batch_job", "Stop runaway batch-reindex test job",
                     "Simulated: systemctl stop batch-reindex.service (owned by the lab test harness).",
                     _cpu_stop_job, "runaway_job"),
        RepairOption("restart_service", "Restart inventory-api",
                     "Simulated: systemctl restart inventory-api. Tests the service-regression hypothesis.",
                     lambda s: s["service"].update(pid=s["service"]["pid"] + 5), "service_regression"),
    ],
    primary_collectors=["process_info", "http_check", "journalctl", "systemctl_status"],
    root_cause="The batch-reindex test job was started with unlimited parallelism (32 workers) and saturated every core.",
)


# --------------------------------------------------------------------------- scenario 4: NIC unavailable


def _nic_inject(s):
    s["iface"]["carrier"] = False


def _nic_failing(s):
    return not s["iface"]["carrier"]


def _nic_metrics(s, n):
    up = s["iface"]["carrier"]
    return [("iface_oper_up", 1.0 if up else 0.0, "bool", {"iface": "eth1"}),
            ("iface_rx_pps", float(1800 + 40 * (n % 5)) if up else 0.0, "packets/s", {"iface": "eth1"})]


def _nic_verify(s):
    up = s["iface"]["carrier"]
    return [
        {"key": "carrier", "name": "eth1 carrier detected (LOWER_UP)", "passed": up,
         "observed": "LOWER_UP" if up else "NO-CARRIER", "expected": "LOWER_UP"},
        {"key": "negotiated", "name": "eth1 negotiated 10000 Mb/s full duplex", "passed": up,
         "observed": "10000Mb/s Full" if up else "Unknown!", "expected": "10000Mb/s Full"},
        {"key": "switch_side", "name": "Switch port lab-sw-01 Eth1/7 oper-up (modeled)", "passed": up,
         "observed": "up" if up else "down (notconnect)", "expected": "up"},
        _probe_ok_check(s),
    ]


def _nic_reseat(s):
    s["iface"].update(carrier=True, switch_port_up=True)


NIC_DOWN = Scenario(
    key="nic-down",
    title="Lab data interface eth1 unavailable",
    project="incident-recovery",
    device="lab-srv-01",
    severity="major",
    runbook="interface-unavailable",
    symptom="lab-srv-01 unreachable on the lab data network (eth1); management interface still responds.",
    detection_rule="iface_oper_up{iface=eth1} == 0 on 2 consecutive probes (simulated)",
    baseline_probes=3,
    detect_after_failed=2,
    onset_known=False,
    onset_note="Link-state history is not retained for this interface, so fault onset is unknown and detection latency is unavailable.",
    inject=_nic_inject,
    failing=_nic_failing,
    metrics=_nic_metrics,
    verify=_nic_verify,
    hypotheses=[
        {"key": "cable_unseated", "statement": "Patch cable CBL-0107 is unseated or damaged.",
         "discriminating_check": "Check link LEDs at both ends; reseat; swap with a known-good tested cable."},
        {"key": "switch_port", "statement": "Switch port lab-sw-01 Eth1/7 is administratively down or err-disabled.",
         "discriminating_check": "Switch-side port status and error-disable reason (network team owns switch config)."},
        {"key": "nic_fault", "statement": "The server NIC or its transceiver has failed.",
         "discriminating_check": "Only after cable and port are ruled out: move to a known-good port; check ethtool -m transceiver DOM."},
    ],
    repairs=[
        RepairOption("reseat_cable", "Reseat patch cable CBL-0107 at the server end",
                     "Simulated physical action: reseat the LC connector and confirm the link LED.", _nic_reseat, "cable_unseated"),
        RepairOption("restart_networking", "Restart host networking",
                     "Simulated: systemctl restart systemd-networkd. Does not restore a physical carrier.",
                     lambda s: None, "nic_fault"),
    ],
    primary_collectors=["interface_counters", "service_reachability", "switch_port", "journalctl"],
    root_cause="Patch cable CBL-0107 was partially unseated at the server end after nearby rack work, so the link lost carrier.",
)


# --------------------------------------------------------------------------- scenario 5: PSU failure (Project 3)


def _psu_inject(s):
    s["psu"]["PSU2"] = "Critical"


def _psu_failing(s):
    return s["psu"]["PSU2"] != "OK"


def _psu_metrics(s, n):
    ok2 = s["psu"]["PSU2"] == "OK"
    return [
        ("psu_output_w", 212.0 if ok2 else 398.0, "W", {"psu": "PSU1", "estimate": "modeled"}),
        ("psu_output_w", 206.0 if ok2 else 0.0, "W", {"psu": "PSU2", "estimate": "modeled"}),
        ("psu_health_ok", 1.0 if ok2 else 0.0, "bool", {"psu": "PSU2"}),
    ]


def _psu_verify(s):
    ok2 = s["psu"]["PSU2"] == "OK"
    return [
        {"key": "psu2_health", "name": "PSU2 Status.Health == OK (Redfish fixture)", "passed": ok2,
         "observed": s["psu"]["PSU2"], "expected": "OK"},
        {"key": "redundancy", "name": "PowerSupply redundancy reports Redundant", "passed": ok2,
         "observed": "Redundant" if ok2 else "NonRedundant", "expected": "Redundant"},
        {"key": "both_inputs", "name": "Both PSUs report input voltage", "passed": ok2,
         "observed": "PSU1 230 V, PSU2 230 V" if ok2 else "PSU2 no input/output", "expected": "both present"},
        _probe_ok_check(s),
    ]


def _psu_replace(s):
    s["psu"]["PSU2"] = "OK"


PSU_FAIL = Scenario(
    key="psu-failure",
    title="PSU2 failure on lab-srv-04",
    project="rack-lifecycle",
    device="lab-srv-04",
    severity="major",
    runbook="psu-replacement",
    symptom="Modeled BMC reports PSU2 Status.Health=Critical; server running on a single PSU (no redundancy).",
    detection_rule="Redfish Power.PowerSupplies[PSU2].Status.Health != OK on 2 consecutive polls (fixture-based)",
    baseline_probes=3,
    detect_after_failed=2,
    onset_known=True,
    onset_note="Onset taken from the simulated SEL entry timestamp written by the simulator.",
    inject=_psu_inject,
    failing=_psu_failing,
    metrics=_psu_metrics,
    verify=_psu_verify,
    hypotheses=[
        {"key": "psu_failed", "statement": "PSU2 module has failed internally.",
         "discriminating_check": "Redfish/SEL: PSU2 reports a fault while its input feed is present (other loads on PDU-B outlet group are healthy)."},
        {"key": "feed_loss", "statement": "PSU2's upstream feed or PDU outlet lost power.",
         "discriminating_check": "Check the PDU-B outlet and other devices on FEED-B. If they are healthy, the feed is not the cause."},
    ],
    repairs=[
        RepairOption("replace_psu2", "Replace PSU2 with reserved compatible spare",
                     "Recorded through the spare-parts workflow: reserve → consume → return the failed unit. Simulated physical swap.",
                     _psu_replace, "psu_failed"),
    ],
    primary_collectors=["redfish_power", "sel_log", "pdu_outlet"],
    root_cause="PSU2 module internal failure (modeled). Input feed present; other FEED-B loads healthy.",
    extra={"requires_spare_workflow": True},
)


SCENARIOS: dict[str, Scenario] = {s.key: s for s in (SVC_STOPPED, FS_FULL, CPU_CONTENTION, NIC_DOWN, PSU_FAIL)}


def apply_repair(scenario: Scenario, state: dict, action_key: str) -> dict:
    opt = next((r for r in scenario.repairs if r.key == action_key), None)
    if opt is None:
        raise KeyError(action_key)
    new = copy.deepcopy(state)
    opt.effect(new)
    new["repairs"].append(action_key)
    new["healthy_since_repair"] = 0
    return new


def probe_time(started: datetime, n: int, interval: float) -> datetime:
    return started + timedelta(seconds=interval * n)
