"""Guided demonstrations.

A demo is a SimulationRun carrying a ``demo_key``. Step completion is *derived from records*
(incident status, evidence, reservations, acceptance runs), so the operator may do each step
in the normal UI or press "Next step". Either way, the same backend workflow and its
validation rules run. No step fakes a success state.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..models import utcnow
from . import acceptance as acc
from . import common, incidents, inventory, simulation

DEMOS: dict[str, dict[str, Any]] = {
    "restore-service": {
        "title": "Restore a failed service",
        "project": "incident-recovery",
        "scenario": "svc-stopped",
        "minutes": "2–3",
        "summary": "Baseline → fault → detection → evidence → wrong hypothesis rejected → correct repair → verified recovery → summary.",
    },
    "acceptance-retest": {
        "title": "Reject and re-test a misconfigured server",
        "project": "server-acceptance",
        "scenario": None,
        "minutes": "2–3",
        "summary": "Expected 128 GiB / 10 Gb/s; observed 64 GiB / 1 Gb/s → FAIL → labeled simulated corrections → new immutable run → PASS → diff.",
    },
    "replace-component": {
        "title": "Replace a failed component and reconcile inventory",
        "project": "rack-lifecycle",
        "scenario": "psu-failure",
        "minutes": "2–3",
        "summary": "PSU2 fault → evidence → compatible spare → reserve → consume → return queue → health re-check → audit trail.",
    },
}

DEMO_INTAKE = "INT-0001"
DEMO_REPLACEMENT_SERIAL = "SIM-PSU-SP-0103"


def _active(db: Session, key: str) -> Optional[m.SimulationRun]:
    return db.scalar(select(m.SimulationRun).where(m.SimulationRun.demo_key == key,
                                                   m.SimulationRun.status.in_(("running", "awaiting_operator", "paused")))
                     .order_by(m.SimulationRun.id.desc()))


def _latest(db: Session, key: str) -> Optional[m.SimulationRun]:
    return db.scalar(select(m.SimulationRun).where(m.SimulationRun.demo_key == key).order_by(m.SimulationRun.id.desc()))


def start(db: Session, key: str, actor: str, now: Optional[datetime] = None) -> m.SimulationRun:
    if key not in DEMOS:
        raise common.NotFound("Demo", key)
    now = now or utcnow()
    # Restart semantics: purge any previous run of this demo (simulation-owned records only).
    for old in db.scalars(select(m.SimulationRun).where(m.SimulationRun.demo_key == key)).all():
        simulation.purge_run(db, old)
    spec = DEMOS[key]
    if spec["scenario"]:
        existing = simulation.active_run_for(db, spec["scenario"])
        if existing:
            simulation.purge_run(db, existing)
        run = simulation.start(db, spec["scenario"], demo_key=key, now=now, actor=actor)
    else:
        intake = db.scalar(select(m.IntakeRecord).where(m.IntakeRecord.display_id == DEMO_INTAKE))
        # Simulated runs on the demo intake from earlier manual use are simulation-owned too.
        for r in db.scalars(select(m.AcceptanceRun).where(m.AcceptanceRun.intake_id == intake.id,
                                                          m.AcceptanceRun.source_type == "SIMULATED")).all():
            db.delete(r)
        db.flush()
        from ..seed import restore_seed_baseline
        restore_seed_baseline(db)
        run = m.SimulationRun(display_id=common.next_display_id(db, "SIM"), scenario_key="acceptance-retest", demo_key=key,
                              status="awaiting_operator", phase="operator", state={"viewed": []}, started_at=now, next_tick_at=None,
                              device_id=None)
        db.add(run)
        db.flush()
        common.audit(db, actor=actor, action="simulation.start", entity_type="simulation_run", entity_id=run.id,
                     entity_display=run.display_id, summary="Started guided demo: reject and re-test a misconfigured server",
                     origin="simulation", simulation_run_id=run.id, at=now)
    run.state = run.state | {"viewed": []}
    common.publish(db, "demo", {"demo": key, "event": "started", "run": run.display_id})
    return run


def exit_demo(db: Session, key: str) -> None:
    for old in db.scalars(select(m.SimulationRun).where(m.SimulationRun.demo_key == key)).all():
        simulation.purge_run(db, old)
    common.publish(db, "demo", {"demo": key, "event": "exited"})


def mark_viewed(db: Session, run: m.SimulationRun, step_key: str) -> None:
    viewed = list(run.state.get("viewed", []))
    if step_key not in viewed:
        viewed.append(step_key)
    run.state = run.state | {"viewed": viewed}
    common.publish(db, "demo", {"demo": run.demo_key, "event": "viewed", "step": step_key})


# --------------------------------------------------------------------------- step definitions


def _incident(db: Session, run: m.SimulationRun) -> Optional[m.Incident]:
    return db.get(m.Incident, run.incident_id) if run.incident_id else None


def _evidence_count(db: Session, inc: Optional[m.Incident]) -> int:
    if not inc:
        return 0
    return db.query(m.EvidenceItem).filter(m.EvidenceItem.incident_id == inc.id).count()


def _restore_steps(db: Session, run: m.SimulationRun) -> list[dict]:
    inc = _incident(db, run)
    iid = inc.id if inc else None
    failed_ver = bool(inc and any(any(not c["passed"] and c["key"] != "post_repair_samples" for c in v.checks)
                                  for v in inc.verifications))
    net_refuted = bool(inc and any(h.key == "network_path" and h.status == "refuted" for h in inc.hypotheses))
    return [
        {"key": "baseline", "title": "Establish a healthy baseline",
         "body": "The simulator probes GET /health on lab-srv-02 every 3 s. The first probes are healthy, which sets the baseline.",
         "done": run.phase != "baseline", "auto": True, "route": "/"},
        {"key": "fault", "title": "Introduce the fault",
         "body": "After the baseline probes, the simulator stops inventory-api.service. Onset is recorded, so detection latency can be measured.",
         "done": run.phase in ("fault", "incident") or run.status == "completed", "auto": True, "route": "/"},
        {"key": "detect", "title": "Detect after 2 failed probes",
         "body": "The detection rule needs 2 consecutive failures (about 6 s), which avoids paging on a single dropped probe.",
         "done": inc is not None, "auto": True, "route": f"/incidents/{iid}" if iid else "/incidents"},
        {"key": "ack", "title": "Acknowledge and start the investigation",
         "body": "Take ownership. The acknowledgment timestamp feeds acknowledgment latency.",
         "done": bool(inc and inc.acknowledged_at and inc.status != "acknowledged"), "route": f"/incidents/{iid}" if iid else None},
        {"key": "evidence", "title": "Collect evidence",
         "body": "HTTP check (refused, not timeout), systemctl status, and journal. Observed output is kept separate from interpretation.",
         "done": _evidence_count(db, inc) >= 3, "route": f"/incidents/{iid}" if iid else None},
        {"key": "wrong", "title": "Test an incorrect hypothesis",
         "body": "Try 'network path down' by bouncing eth1. Verification fails because the unit is still dead, and the incident returns to investigating. Nothing is falsely resolved.",
         "done": failed_ver or net_refuted or bool(inc and any(r.action_key == "restart_service" for r in inc.repairs)),
         "optional": True, "route": f"/incidents/{iid}" if iid else None},
        {"key": "repair", "title": "Apply the correct repair",
         "body": "Start inventory-api.service (simulated). The journal showed a scripted `systemctl stop`.",
         "done": bool(inc and any(r.action_key == "restart_service" for r in inc.repairs)), "route": f"/incidents/{iid}" if iid else None},
        {"key": "verify", "title": "Verify recovery",
         "body": "Unit active, port listening, /health 200, plus 2 consecutive healthy probes after the repair. Pressing the button does not prove recovery.",
         "done": bool(inc and inc.verifications and inc.verifications[-1].passed), "route": f"/incidents/{iid}" if iid else None},
        {"key": "resolve", "title": "Resolve and review the post-incident summary",
         "body": "The summary is generated from stored events, evidence and verification records.",
         "done": bool(inc and inc.status == "resolved"), "route": f"/incidents/{iid}?tab=summary" if iid else None},
    ]


def _acceptance_steps(db: Session, run: m.SimulationRun) -> list[dict]:
    intake = db.scalar(select(m.IntakeRecord).where(m.IntakeRecord.display_id == DEMO_INTAKE))
    runs = [r for r in intake.runs if r.simulation_run_id == run.id]
    viewed = set(run.state.get("viewed", []))
    first_fail = next((r for r in runs if r.status == "completed" and r.disposition == "FAIL"), None)
    passed = next((r for r in runs if r.status == "completed" and r.disposition == "PASS"), None)
    applied = {c["key"] for c in intake.simulated_corrections or []}
    base = f"/acceptance/{intake.id}"
    return [
        {"key": "review", "title": "Review the intake record",
         "body": "lab-srv-06 is expected to have 2 CPUs, 128 GiB RAM, 2 × 960 GB NVMe, 2 NICs, and a 10 Gb/s data link.",
         "done": "review" in viewed, "route": base, "view": True},
        {"key": "run1", "title": "Run acceptance #1",
         "body": "The job runner executes 10 modular checks against the simulator's hardware model and snapshots the observations first.",
         "done": first_fail is not None, "route": base},
        {"key": "failures", "title": "Read the failures",
         "body": "Memory 64 GiB (FAIL), data link 1000 Mb/s (FAIL). Required failures produce FAIL. Optional checks stay visible but do not decide the outcome.",
         "done": "failures" in viewed and first_fail is not None, "route": f"{base}?run={first_fail.id}" if first_fail else base, "view": True},
        {"key": "correct", "title": "Apply labeled simulated corrections",
         "body": "Install 4 × 16 GiB DIMMs and replace the 1G SFP with a 10GBASE-SR optic. Each correction is recorded and labeled SIMULATED.",
         "done": {"install_dimms", "replace_transceiver"} <= applied, "route": base},
        {"key": "run2", "title": "Re-test with a new immutable run",
         "body": "Run #2 is a new record. Run #1 stays exactly as it was.",
         "done": passed is not None, "route": base},
        {"key": "compare", "title": "Compare the runs side by side",
         "body": "The diff shows the original failure, the corrections between runs, and the passing re-test.",
         "done": "compare" in viewed and passed is not None,
         "route": f"{base}?compare={first_fail.id},{passed.id}" if (first_fail and passed) else base, "view": True},
        {"key": "report", "title": "Open the printable report",
         "body": "The HTML report and JSON export are rendered from the persisted run, not from the current state.",
         "done": "report" in viewed and passed is not None, "route": f"/acceptance/runs/{passed.id}/report" if passed else base, "view": True},
    ]


def _replace_steps(db: Session, run: m.SimulationRun) -> list[dict]:
    inc = _incident(db, run)
    iid = inc.id if inc else None
    viewed = set(run.state.get("viewed", []))
    res = db.scalars(select(m.Reservation).where(m.Reservation.incident_id == iid)).all() if iid else []
    dev = db.scalar(select(m.Device).where(m.Device.display_id == "lab-srv-04"))
    failed_psu = db.scalar(select(m.Asset).where(m.Asset.display_id == "NL-AST-P04B"))
    rr = db.scalar(select(m.ReturnRecord).where(m.ReturnRecord.failed_asset_id == failed_psu.id)) if failed_psu else None
    return [
        {"key": "detect", "title": "Detect the PSU fault",
         "body": "The modeled BMC poll (Redfish fixture) reports PSU2 Health=Critical twice in a row, which raises the incident.",
         "done": inc is not None, "auto": True, "route": "/"},
        {"key": "open", "title": "Open the affected device and take the incident",
         "body": "lab-srv-04 at NL-R01 U30–31. The device drawer links hardware, power inputs, incidents and lifecycle.",
         "done": bool(inc and inc.status not in ("detected", "acknowledged")), "route": f"/assets/{dev.asset_id}" if dev else None},
        {"key": "evidence", "title": "Review the failure evidence",
         "body": "Redfish Power, SEL, and PDU outlet. The outlet is ON and neighbouring FEED-B loads are healthy, so the feed is not the cause.",
         "done": _evidence_count(db, inc) >= 2, "route": f"/incidents/{iid}" if iid else None},
        {"key": "spare", "title": "Identify a compatible spare",
         "body": "NL-PSU-800P is listed compatible with NL-2U-Storage. NL-PSU-550S is flagged incompatible.",
         "done": "spare" in viewed, "route": f"/spares?device={dev.id}&incident={iid}" if dev and iid else "/spares", "view": True},
        {"key": "reserve", "title": "Reserve it",
         "body": "The reservation reduces available stock but not on-hand stock. Nothing is consumed yet.",
         "done": any(r.status in ("active", "consumed") for r in res), "route": f"/spares?device={dev.id}&incident={iid}" if dev and iid else "/spares"},
        {"key": "consume", "title": "Record the replacement and consume the reservation",
         "body": f"Serial {DEMO_REPLACEMENT_SERIAL} is recorded as installed in PSU2. One atomic transaction writes the ledger, the reservation, both assets, and the incident repair. Physical work is simulated.",
         "done": any(r.status == "consumed" for r in res), "route": f"/spares?device={dev.id}&incident={iid}" if dev and iid else "/spares"},
        {"key": "rma", "title": "Move the failed PSU to the return queue",
         "body": "The return record links the failed serial, the incident, and the evidence. No vendor is contacted.",
         "done": rr is not None, "route": "/returns"},
        {"key": "verify", "title": "Re-run the health check",
         "body": "Verification re-reads the (simulated) Redfish Power resource: PSU2 OK, redundancy restored.",
         "done": bool(inc and inc.verifications and inc.verifications[-1].passed), "route": f"/incidents/{iid}" if iid else None},
        {"key": "audit", "title": "Resolve and show the audit trail",
         "body": "Every material change (reservation, ledger, asset transitions, return, incident) is in the audit log.",
         "done": bool(inc and inc.status == "resolved") and "audit" in viewed,
         "route": f"/assets/{dev.asset_id}?tab=audit" if dev else None},
    ]


STEP_BUILDERS: dict[str, Callable[[Session, m.SimulationRun], list[dict]]] = {
    "restore-service": _restore_steps, "acceptance-retest": _acceptance_steps, "replace-component": _replace_steps,
}


def status(db: Session, key: str) -> dict[str, Any]:
    spec = DEMOS[key]
    run = _latest(db, key)
    if run is None:
        return {"key": key, **spec, "run": None, "steps": [], "current": None, "complete": False}
    steps = STEP_BUILDERS[key](db, run)
    current = next((i for i, s in enumerate(steps) if not s["done"]), None)
    return {"key": key, **spec, "run": {"display_id": run.display_id, "status": run.status, "phase": run.phase,
                                         "probe_count": run.probe_count, "started_at": common.dt(run.started_at),
                                         "incident_id": run.incident_id,
                                         "healthy_since_repair": run.state.get("healthy_since_repair")},
            "steps": steps, "current": current, "complete": current is None}


def next_step(db: Session, key: str, actor: str, now: Optional[datetime] = None) -> dict[str, Any]:
    """Perform the current step through the normal workflow functions, if it is operator-actionable."""
    now = now or utcnow()
    run = _active(db, key) or _latest(db, key)
    if run is None:
        raise common.DomainError("demo_not_started", "Start the demo first.")
    if run.status == "paused":
        raise common.DomainError("demo_paused", "The demo is paused. Resume it to continue.")
    st = status(db, key)
    if st["complete"]:
        return {"message": "Demo complete."}
    step = st["steps"][st["current"]]
    if step.get("auto"):
        return {"message": "Waiting for the simulator: this step completes on its own as probes run."}
    if step.get("view"):
        mark_viewed(db, run, step["key"])
        return {"message": f"Marked '{step['title']}' as reviewed.", "route": step.get("route")}
    return {"message": _perform(db, key, run, step["key"], actor, now), "route": step.get("route")}


def _perform(db: Session, key: str, run: m.SimulationRun, step: str, actor: str, now: datetime) -> str:
    inc = _incident(db, run)
    if key == "restore-service":
        if step == "ack":
            if inc.status == "detected":
                incidents.acknowledge(db, inc, actor, now)
            incidents.start_investigation(db, inc, actor, now)
            return "Acknowledged and investigation started."
        if step == "evidence":
            have = {e.collector for e in db.scalars(select(m.EvidenceItem).where(m.EvidenceItem.incident_id == inc.id)).all()}
            for c in ("http_check", "systemctl_status", "journalctl"):
                if c not in have:
                    incidents.collect_evidence(db, inc, c, actor, now)
            return "Collected HTTP check, systemctl status and journal."
        if step == "wrong":
            incidents.apply_repair_action(db, inc, "bounce_iface", actor, now)
            incidents.verify(db, inc, actor, now)
            incidents.collect_evidence(db, inc, "interface_counters", actor, now)
            incidents.set_hypothesis(db, inc, "network_path", "refuted",
                                     "eth1 has carrier with incrementing counters; verification still fails after the bounce.", actor)
            incidents.set_hypothesis(db, inc, "svc_stopped", "supported",
                                     "systemctl shows inactive (dead) after SIGTERM; journal shows a scripted systemctl stop.", actor)
            return "Bounced eth1. Verification FAILED and the incident is back in investigation. Network hypothesis refuted."
        if step == "repair":
            if inc.status != "investigating":
                raise common.DomainError("not_investigating", "Incident is not in investigation.")
            incidents.apply_repair_action(db, inc, "restart_service", actor, now)
            return "Started inventory-api.service (simulated). Waiting for post-repair probes."
        if step == "verify":
            v = incidents.verify(db, inc, actor, now)
            return "Verification passed." if v.passed else "Verification incomplete. Waiting for 2 healthy post-repair probes; try again in a few seconds."
        if step == "resolve":
            incidents.resolve(db, inc, actor, now=now)
            return "Resolved. Post-incident summary generated."
    if key == "acceptance-retest":
        intake = db.scalar(select(m.IntakeRecord).where(m.IntakeRecord.display_id == DEMO_INTAKE))
        if step in ("run1", "run2"):
            active = next((r for r in intake.runs if r.status in ("queued", "running")), None)
            if active:
                return f"{active.display_id} is still running."
            r = acc.start_run(db, intake, "simulator", actor, now)
            return f"{r.display_id} queued. The job runner executes checks in the background."
        if step == "correct":
            done = {c["key"] for c in intake.simulated_corrections or []}
            for k in ("install_dimms", "replace_transceiver"):
                if k not in done:
                    acc.apply_correction(db, intake, k, actor, now)
            return "Recorded both simulated corrections."
    if key == "replace-component":
        dev = db.scalar(select(m.Device).where(m.Device.display_id == "lab-srv-04"))
        if step == "open":
            if inc.status == "detected":
                incidents.acknowledge(db, inc, actor, now)
            if inc.status == "acknowledged":
                incidents.start_investigation(db, inc, actor, now)
            return "Incident acknowledged; investigation started."
        if step == "evidence":
            for c in ("redfish_power", "sel_log", "pdu_outlet"):
                incidents.collect_evidence(db, inc, c, actor, now)
            incidents.set_hypothesis(db, inc, "feed_loss", "refuted", "Outlet ON; other FEED-B loads draw current.", actor)
            incidents.set_hypothesis(db, inc, "psu_failed", "supported", "PSU2 Health=Critical with input present; SEL failure assertion.", actor)
            return "Collected Redfish Power, SEL and PDU outlet evidence. PSU failure supported; feed loss refuted."
        if step == "reserve":
            stock = db.scalar(select(m.SpareStock).join(m.PartType).where(m.PartType.part_number == "NL-PSU-800P"))
            r = inventory.reserve(db, stock=stock, quantity=1, device=dev, incident=inc,
                                  reason=f"Replace failed PSU2 ({inc.display_id})", actor=actor, now=now)
            return f"Reserved 1 × NL-PSU-800P ({r.display_id})."
        if step == "consume":
            r = db.scalar(select(m.Reservation).where(m.Reservation.incident_id == inc.id, m.Reservation.status == "active"))
            pi = db.scalar(select(m.PowerInput).where(m.PowerInput.device_id == dev.id, m.PowerInput.name == "PSU2"))
            inventory.consume(db, r, actor=actor, replacement_serial=DEMO_REPLACEMENT_SERIAL, power_input_id=pi.id,
                              note="Hot-swap PSU2 (simulated physical work)", now=now)
            return f"Consumed {r.display_id}; {DEMO_REPLACEMENT_SERIAL} recorded in PSU2. Failed unit quarantined."
        if step == "rma":
            failed = db.scalar(select(m.Asset).where(m.Asset.display_id == "NL-AST-P04B"))
            ev = db.scalar(select(m.EvidenceItem).where(m.EvidenceItem.incident_id == inc.id, m.EvidenceItem.collector == "redfish_power"))
            new = db.scalar(select(m.Asset).where(m.Asset.serial_number == DEMO_REPLACEMENT_SERIAL))
            inventory.create_return(db, failed_asset=failed, failure_summary="PSU2 Status.Health=Critical, no output; SEL 'Failure detected'.",
                                    actor=actor, incident=inc, failure_evidence_id=ev.id if ev else None,
                                    replacement_asset_id=new.id if new else None, original_device_id=dev.id)
            return "Return record created; the failed PSU is pending return."
        if step == "verify":
            v = incidents.verify(db, inc, actor, now)
            return "Health check passed." if v.passed else "Waiting for post-repair polls; try again in a few seconds."
        if step == "audit":
            if inc.status != "resolved":
                incidents.resolve(db, inc, actor, now=now)
            mark_viewed(db, run, "audit")
            return "Incident resolved. Open the audit tab to review the full trail."
    return "Nothing to do for this step."
