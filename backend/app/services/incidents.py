"""Incident lifecycle: Detected → Acknowledged → Investigating → Repair applied → Verification → Resolved.

Rules enforced here (not in the UI):
* Resolution requires the latest verification, executed after the latest repair, to have passed.
* A failed verification returns the incident to Investigating; nothing is falsely resolved.
* Reopening preserves the complete prior history (append-only events, verifications, repairs).
"""
from __future__ import annotations

import statistics
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..collectors import sim_evidence
from ..models import utcnow
from . import common, simulation
from .scenarios import REQUIRED_HEALTHY_PROBES, SCENARIOS, apply_repair

TRANSITIONS: dict[str, set[str]] = {
    "detected": {"acknowledged"},
    "acknowledged": {"investigating"},
    "investigating": {"repair_applied"},
    "repair_applied": {"verification", "investigating"},
    "verification": {"resolved", "investigating"},
    "resolved": {"investigating"},  # reopen
}

SEVERITY_RANK = {"critical": 0, "major": 1, "minor": 2}


def _event(db: Session, inc: m.Incident, kind: str, summary: str, *, actor: str = "system",
           at: Optional[datetime] = None, frm: Optional[str] = None, to: Optional[str] = None,
           detail: Optional[dict] = None) -> m.IncidentEvent:
    ev = m.IncidentEvent(kind=kind, summary=summary, actor=actor, occurred_at=at or utcnow(),
                         from_status=frm, to_status=to, detail=detail or {})
    inc.events.append(ev)
    db.flush()
    common.publish(db, "incident", {"incident": inc.display_id, "id": inc.id, "kind": kind, "status": inc.status})
    return ev


def _transition(db: Session, inc: m.Incident, to: str, actor: str, summary: str, at: Optional[datetime] = None,
                detail: Optional[dict] = None) -> None:
    frm = inc.status
    if to not in TRANSITIONS.get(frm, set()):
        raise common.DomainError(
            "invalid_transition",
            f"{inc.display_id} cannot move from {frm.replace('_', ' ')} to {to.replace('_', ' ')}.",
            409, {"from": frm, "to": to, "allowed": sorted(TRANSITIONS.get(frm, set()))},
        )
    inc.status = to
    _event(db, inc, "status", summary, actor=actor, at=at, frm=frm, to=to, detail=detail)
    common.audit(db, actor=actor, action=f"incident.{to}", entity_type="incident", entity_id=inc.id,
                 entity_display=inc.display_id, summary=summary, before={"status": frm}, after={"status": to},
                 origin=inc.origin, simulation_run_id=inc.simulation_run_id, at=at,
                 related=[{"type": "device", "id": inc.device_id, "display": inc.device.display_id}] if inc.device else [])


def _sim_run(db: Session, inc: m.Incident) -> Optional[m.SimulationRun]:
    return db.get(m.SimulationRun, inc.simulation_run_id) if inc.simulation_run_id else None


# --------------------------------------------------------------------------- creation


def create_from_simulation(db: Session, run: m.SimulationRun, sc, state: dict, detected_at: datetime) -> m.Incident:
    from datetime import datetime as _dt
    fault_at = _dt.fromisoformat(state["fault_at"].replace("Z", "+00:00")) if state.get("fault_at") else None
    inc = m.Incident(
        display_id=common.next_display_id(db, "INC"),
        title=sc.title,
        symptom=sc.symptom,
        severity=sc.severity,
        status="detected",
        device_id=run.device_id,
        scenario_key=sc.key,
        runbook_slug=sc.runbook,
        detection_rule=sc.detection_rule,
        source_type="SIMULATED",
        source_id=f"sim:{sc.key}:{run.display_id}",
        simulation_run_id=run.id,
        fault_onset_at=fault_at if sc.onset_known else None,
        detected_at=detected_at,
        origin="simulation",
    )
    db.add(inc)
    db.flush()
    if sc.onset_known and fault_at:
        _event(db, inc, "fault_onset", f"Fault onset (known): {sc.onset_note}", at=fault_at, detail={"known": True})
    else:
        _event(db, inc, "fault_onset", f"Fault onset unknown. {sc.onset_note}", at=detected_at, detail={"known": False})
    _event(db, inc, "detected", f"Detected by rule: {sc.detection_rule}", at=detected_at,
           detail={"rule": sc.detection_rule, "consecutive_failed": state.get("consecutive_failed")})
    for h in sc.hypotheses:
        inc.hypotheses.append(m.Hypothesis(key=h["key"], statement=h["statement"],
                                           discriminating_check=h["discriminating_check"]))
    common.audit(db, actor="detector", action="incident.detected", entity_type="incident", entity_id=inc.id,
                 entity_display=inc.display_id, summary=f"{inc.display_id} detected: {sc.title}",
                 after={"status": "detected", "severity": sc.severity}, origin="simulation",
                 simulation_run_id=run.id, at=detected_at,
                 related=[{"type": "device", "id": run.device_id, "display": sc.device}])
    return inc


# --------------------------------------------------------------------------- actions


def acknowledge(db: Session, inc: m.Incident, actor: str, now: Optional[datetime] = None) -> m.Incident:
    now = now or utcnow()
    _transition(db, inc, "acknowledged", actor, f"Acknowledged by {actor}", at=now)
    inc.acknowledged_at = inc.acknowledged_at or now
    inc.assigned_operator = inc.assigned_operator or actor
    return inc


def start_investigation(db: Session, inc: m.Incident, actor: str, now: Optional[datetime] = None) -> m.Incident:
    _transition(db, inc, "investigating", actor, "Investigation started", at=now or utcnow())
    return inc


def assign(db: Session, inc: m.Incident, operator: str, actor: str) -> m.Incident:
    before = inc.assigned_operator
    inc.assigned_operator = operator
    _event(db, inc, "note", f"Assigned to {operator}", actor=actor)
    common.audit(db, actor=actor, action="incident.assign", entity_type="incident", entity_id=inc.id,
                 entity_display=inc.display_id, summary=f"Assigned to {operator}", before={"assigned": before},
                 after={"assigned": operator}, origin=inc.origin, simulation_run_id=inc.simulation_run_id)
    return inc


def add_note(db: Session, inc: m.Incident, text: str, actor: str) -> m.IncidentEvent:
    return _event(db, inc, "note", text, actor=actor)


EXTERNAL_REPAIR = {"key": "manual_repair", "label": "Record a manual repair",
                   "description": "Operator-performed repair recorded against an external alert. Verification relies on the alert source reporting resolved.",
                   "tests_hypothesis": None, "requires_spare_workflow": False}


def _is_external(inc: m.Incident) -> bool:
    return inc.scenario_key is None


def collectors_for(db: Session, inc: m.Incident) -> list[dict]:
    if _is_external(inc):
        return []
    if inc.source_type == "LOCAL_LAB":
        from ..livelab import manager
        return manager.COLLECTORS_META
    sc = SCENARIOS.get(inc.scenario_key or "")
    primary = sc.primary_collectors if sc else []
    keys = primary + [k for k in sim_evidence.COLLECTORS if k not in primary]
    return [{"key": k, **sim_evidence.COLLECTORS[k], "recommended": k in primary} for k in keys]


def collect_evidence(db: Session, inc: m.Incident, collector: str, actor: str, now: Optional[datetime] = None) -> m.EvidenceItem:
    now = now or utcnow()
    if _is_external(inc):
        raise common.DomainError("no_collectors", "No collectors are connected for externally sourced alerts. Add notes instead.")
    if inc.source_type == "LOCAL_LAB":
        from ..livelab import manager
        data = manager.collect(collector)
        source_id = f"livelab:{collector}"
        origin = "local_lab"
    else:
        run = _sim_run(db, inc)
        if run is None:
            raise common.DomainError("no_simulation", "This simulated incident's run was removed; evidence cannot be collected.")
        fault_at = inc.fault_onset_at
        if fault_at is None and run.state.get("fault_at"):
            fault_at = datetime.fromisoformat(run.state["fault_at"].replace("Z", "+00:00"))
        try:
            data = sim_evidence.collect(collector, run.state, now, fault_at)
        except KeyError:
            raise common.DomainError("unknown_collector", f"Unknown collector '{collector}'", 404)
        source_id = f"sim:{inc.scenario_key}:{run.display_id}:{collector}"
        origin = "simulation"
    ev = m.EvidenceItem(
        display_id=common.next_display_id(db, "EV"), incident_id=inc.id, device_id=inc.device_id, collector=collector,
        command=data["command"], output=data["output"], observations=data.get("observations", {}),
        interpretation=data.get("interpretation", ""), limitations=data.get("limitations", ""),
        source_type=inc.source_type, source_id=source_id, collected_at=now,
        simulation_run_id=inc.simulation_run_id, origin=origin,
    )
    db.add(ev)
    db.flush()
    _event(db, inc, "evidence", f"Evidence collected: {collector} ({ev.display_id})", actor=actor, at=now,
           detail={"evidence_id": ev.id, "evidence": ev.display_id, "collector": collector})
    return ev


def set_hypothesis(db: Session, inc: m.Incident, key: str, status: str, note: str, actor: str) -> m.Hypothesis:
    h = next((h for h in inc.hypotheses if h.key == key), None)
    if h is None:
        raise common.NotFound("Hypothesis", key)
    if status not in ("open", "supported", "refuted"):
        raise common.DomainError("invalid_status", "Hypothesis status must be open, supported or refuted", 422)
    prev = h.status
    h.status, h.note = status, note
    _event(db, inc, "hypothesis", f"Hypothesis '{h.statement}' marked {status}" + (f": {note}" if note else ""),
           actor=actor, detail={"key": key, "from": prev, "to": status})
    return h


def repair_options(db: Session, inc: m.Incident) -> list[dict]:
    if _is_external(inc):
        return [EXTERNAL_REPAIR]
    if inc.source_type == "LOCAL_LAB":
        from ..livelab import manager
        return manager.REPAIRS_META
    sc = SCENARIOS.get(inc.scenario_key or "")
    if not sc:
        return []
    return [{"key": r.key, "label": r.label, "description": r.description, "tests_hypothesis": r.tests_hypothesis,
             "requires_spare_workflow": bool(sc.extra.get("requires_spare_workflow"))} for r in sc.repairs]


def apply_repair_action(db: Session, inc: m.Incident, action_key: str, actor: str, now: Optional[datetime] = None,
                        _from_spare_workflow: bool = False) -> m.RepairAction:
    now = now or utcnow()
    if inc.status != "investigating":
        raise common.DomainError("invalid_transition",
                                 f"Repairs are recorded while investigating; {inc.display_id} is {inc.status.replace('_', ' ')}.")
    if _is_external(inc):
        if action_key != "manual_repair":
            raise common.DomainError("unknown_action", f"Unknown repair action '{action_key}'", 404)
        desc = EXTERNAL_REPAIR["description"]
    elif inc.source_type == "LOCAL_LAB":
        from ..livelab import manager
        desc = manager.apply_repair(action_key)
    else:
        sc = SCENARIOS[inc.scenario_key]
        if sc.extra.get("requires_spare_workflow") and not _from_spare_workflow:
            raise common.DomainError(
                "spare_workflow_required",
                "This repair replaces a physical component. Record it through the spare-parts workflow "
                "(reserve → consume) so inventory and the return queue stay reconciled.", 409)
        run = _sim_run(db, inc)
        try:
            run.state = apply_repair(sc, run.state, action_key)
        except KeyError:
            raise common.DomainError("unknown_action", f"Unknown repair action '{action_key}'", 404)
        desc = next(r.description for r in sc.repairs if r.key == action_key)
    ra = m.RepairAction(action_key=action_key, description=desc, applied_at=now, actor=actor,
                        source_type=inc.source_type)
    inc.repairs.append(ra)
    db.flush()
    inc.repair_applied_at = now
    _transition(db, inc, "repair_applied", actor, f"Repair applied: {desc}", at=now,
                detail={"action_key": action_key, "repair_id": ra.id})
    return ra


def verify(db: Session, inc: m.Incident, actor: str, now: Optional[datetime] = None) -> m.Verification:
    """Execute verification checks against current state. Pressing verify does not itself prove recovery."""
    now = now or utcnow()
    if inc.status not in ("repair_applied", "verification"):
        raise common.DomainError("invalid_transition", "Verification runs after a repair has been applied.")
    last_repair = inc.repairs[-1] if inc.repairs else None
    if _is_external(inc):
        resolved_after = [e for e in inc.events if e.detail.get("alert_status") == "resolved"
                          and last_repair and e.occurred_at >= last_repair.applied_at]
        checks = [{"key": "alert_resolved", "name": "Alert source reports the alert resolved after the repair",
                   "passed": bool(resolved_after), "observed": "resolved" if resolved_after else "no resolved notification received",
                   "expected": "resolved"}]
        source_id = f"{inc.source_id}:verify"
    elif inc.source_type == "LOCAL_LAB":
        from ..livelab import manager
        checks = manager.verify()
        source_id = "livelab:verify"
    else:
        sc = SCENARIOS[inc.scenario_key]
        run = _sim_run(db, inc)
        checks = sc.verify(run.state)
        source_id = f"sim:{sc.key}:{run.display_id}:verify"
    passed = all(c["passed"] for c in checks)
    ver = m.Verification(executed_at=now, after_repair_id=last_repair.id if last_repair else None,
                         passed=passed, checks=checks, source_type=inc.source_type, source_id=source_id)
    inc.verifications.append(ver)
    db.flush()
    if inc.status == "repair_applied":
        _transition(db, inc, "verification", actor, "Verification started", at=now)
    waiting = [c for c in checks if c["key"] == "post_repair_samples" and not c["passed"]]
    other_failed = [c for c in checks if not c["passed"] and c["key"] != "post_repair_samples"]
    if passed:
        inc.verified_at = now
        _event(db, inc, "verification", f"Verification PASSED ({len(checks)}/{len(checks)} checks)", actor=actor, at=now,
               detail={"verification_id": ver.id, "passed": True, "checks": checks})
    elif waiting and not other_failed:
        _event(db, inc, "verification",
               f"Verification incomplete: waiting for {REQUIRED_HEALTHY_PROBES} healthy post-repair probes", actor=actor, at=now,
               detail={"verification_id": ver.id, "passed": False, "checks": checks, "waiting": True})
    else:
        _event(db, inc, "verification",
               f"Verification FAILED: {', '.join(c['name'] for c in other_failed)}", actor=actor, at=now,
               detail={"verification_id": ver.id, "passed": False, "checks": checks})
        _transition(db, inc, "investigating", actor,
                    "Verification failed; returned to investigation (repair did not restore service)", at=now)
    return ver


def resolve(db: Session, inc: m.Incident, actor: str, root_cause: str = "", now: Optional[datetime] = None) -> m.Incident:
    now = now or utcnow()
    last_repair = inc.repairs[-1] if inc.repairs else None
    last_ver = inc.verifications[-1] if inc.verifications else None
    if (last_ver is None or not last_ver.passed or last_repair is None
            or last_ver.after_repair_id != last_repair.id or last_ver.executed_at < last_repair.applied_at):
        raise common.DomainError(
            "verification_required",
            "Resolution requires a passing verification executed after the most recent repair.", 409,
            {"last_verification_passed": bool(last_ver and last_ver.passed)},
        )
    if inc.scenario_key and not root_cause:
        sc = SCENARIOS.get(inc.scenario_key)
        root_cause = sc.root_cause if sc else ""
    inc.root_cause = root_cause or inc.root_cause
    inc.resolved_at = now
    _transition(db, inc, "resolved", actor, "Resolved after verified recovery", at=now,
                detail={"verification_id": last_ver.id})
    run = _sim_run(db, inc)
    if run and run.status in ("running", "awaiting_operator"):
        simulation.complete(db, run, now)
    return inc


def reopen(db: Session, inc: m.Incident, reason: str, actor: str, now: Optional[datetime] = None) -> m.Incident:
    now = now or utcnow()
    if not reason.strip():
        raise common.DomainError("reason_required", "A reason is required to reopen an incident.", 422)
    prior = {"resolved_at": common.dt(inc.resolved_at), "verified_at": common.dt(inc.verified_at)}
    inc.reopen_count += 1
    inc.resolved_at = None
    inc.verified_at = None
    _event(db, inc, "reopened", f"Reopened: {reason}", actor=actor, at=now, detail=prior | {"reason": reason})
    _transition(db, inc, "investigating", actor, "Reopened for further investigation", at=now)
    run = _sim_run(db, inc)
    if run and run.status == "completed":
        run.status, run.next_tick_at = "awaiting_operator", now
    return inc


# --------------------------------------------------------------------------- read models


def next_step(db: Session, inc: m.Incident) -> str:
    s = inc.status
    if s == "detected":
        return "Acknowledge and take ownership."
    if s == "acknowledged":
        return "Start the investigation and open the runbook."
    if s == "investigating":
        ev_count = db.query(m.EvidenceItem).filter(m.EvidenceItem.incident_id == inc.id).count()
        if ev_count == 0:
            return "Collect initial evidence (runbook step 1)."
        if not any(h.status == "supported" for h in inc.hypotheses):
            return "Use discriminating checks to support or refute a hypothesis."
        return "Apply the corrective action for the supported hypothesis."
    if s == "repair_applied":
        return "Run verification checks."
    if s == "verification":
        last = inc.verifications[-1] if inc.verifications else None
        if last and last.passed:
            return "Verification passed. Resolve and write the post-incident summary."
        return "Waiting for post-repair samples. Re-run verification."
    return "Review the post-incident summary."


def queue_sort_key(inc: m.Incident):
    unresolved = inc.status != "resolved"
    critical_open = unresolved and inc.severity == "critical"
    unacked = inc.acknowledged_at is None and unresolved
    return (0 if critical_open else 1, 0 if unresolved else 1, 0 if unacked else 1,
            SEVERITY_RANK.get(inc.severity, 3), inc.detected_at)


def _secs(a: Optional[datetime], b: Optional[datetime]) -> Optional[float]:
    if a is None or b is None:
        return None
    d = (b - a).total_seconds()
    return d if d >= 0 else None


def incident_metrics(inc: m.Incident) -> dict[str, Any]:
    return {
        "detection_latency_s": _secs(inc.fault_onset_at, inc.detected_at),
        "detection_latency_note": None if inc.fault_onset_at else "Unavailable: fault onset unknown",
        "acknowledgment_latency_s": _secs(inc.detected_at, inc.acknowledged_at),
        "repair_interval_s": _secs(inc.detected_at, inc.verified_at) if inc.status == "resolved" else None,
    }


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "median": None, "mean": None}
    return {"count": len(values), "median": round(statistics.median(values), 1), "mean": round(statistics.fmean(values), 1)}


def aggregate_metrics(db: Session) -> dict[str, Any]:
    """Aggregates per source type. Simulated and real drills are NEVER combined."""
    out: dict[str, Any] = {
        "definitions": {
            "detection_latency": "Detection timestamp minus known fault onset. Excluded when onset is unknown.",
            "acknowledgment_latency": "Acknowledgment timestamp minus detection timestamp.",
            "mttr": "MTTR — detection to verified recovery: verification-pass timestamp minus detection, resolved incidents only.",
        },
        "by_source": {},
    }
    incs = db.scalars(select(m.Incident).order_by(m.Incident.detected_at)).all()
    for src in m.SOURCE_TYPES:
        rows = [i for i in incs if i.source_type == src]
        det, ack, rep, drills = [], [], [], []
        for i in rows:
            mt = incident_metrics(i)
            if mt["detection_latency_s"] is not None:
                det.append(mt["detection_latency_s"])
            if mt["acknowledgment_latency_s"] is not None:
                ack.append(mt["acknowledgment_latency_s"])
            if mt["repair_interval_s"] is not None:
                rep.append(mt["repair_interval_s"])
            drills.append({"incident": i.display_id, "id": i.id, "scenario": i.scenario_key, "status": i.status,
                           "detected_at": common.dt(i.detected_at), **mt})
        out["by_source"][src] = {
            "incidents": len(rows),
            "detection_latency_s": _stats(det),
            "acknowledgment_latency_s": _stats(ack),
            "mttr_s": _stats(rep),
            "excluded_unknown_onset": sum(1 for i in rows if i.fault_onset_at is None),
            "drills": drills,
        }
    return out


def _ts(v: Optional[datetime]) -> str:
    return v.strftime("%Y-%m-%d %H:%M:%SZ") if v else "—"


def summary(db: Session, inc: m.Incident) -> dict[str, Any]:
    """Post-incident summary generated from persisted records only."""
    evidence = db.scalars(select(m.EvidenceItem).where(m.EvidenceItem.incident_id == inc.id).order_by(m.EvidenceItem.id)).all()
    mt = incident_metrics(inc)
    lines = [
        f"# Post-incident summary — {inc.display_id}",
        "",
        f"**Source:** {inc.source_type.replace('_', ' ')} (`{inc.source_id}`)",
        f"**Title:** {inc.title}",
        f"**Device:** {inc.device.display_id if inc.device else 'Unknown'}",
        f"**Severity:** {inc.severity}   **Status:** {inc.status}",
        f"**Detection rule:** {inc.detection_rule}",
        "",
        "## Timeline (UTC)",
    ]
    for e in inc.events:
        lines.append(f"- `{_ts(e.occurred_at)}` **{e.kind}** — {e.summary}")
    lines += ["", "## Evidence collected"]
    for e in evidence:
        lines.append(f"- {e.display_id} `{e.collector}` at {_ts(e.collected_at)}: {e.interpretation}")
    lines += ["", "## Hypotheses"]
    for h in inc.hypotheses:
        lines.append(f"- [{h.status}] {h.statement}" + (f": {h.note}" if h.note else ""))
    lines += ["", "## Repairs"]
    for r in inc.repairs:
        lines.append(f"- {_ts(r.applied_at)}: {r.description} ({r.action_key})")
    lines += ["", "## Verification"]
    for v in inc.verifications:
        lines.append(f"- {_ts(v.executed_at)}: {'PASSED' if v.passed else 'NOT PASSED'}: "
                     + "; ".join(f"{c['name']}={'ok' if c['passed'] else 'fail'}" for c in v.checks))
    lines += ["", "## Root cause", inc.root_cause or "Not recorded.", "", "## Measurements (this incident)"]

    def fmt(v):
        return "Unavailable" if v is None else f"{v:.1f} s"
    lines += [
        f"- Detection latency: {fmt(mt['detection_latency_s'])}" + (f" ({mt['detection_latency_note']})" if mt["detection_latency_note"] else ""),
        f"- Acknowledgment latency: {fmt(mt['acknowledgment_latency_s'])}",
        f"- Detection → verified recovery: {fmt(mt['repair_interval_s'])}",
        "",
        "_Generated from stored records. Simulated incidents are drills in a modeled lab, not production events._",
    ]
    return {"markdown": "\n".join(lines), "metrics": mt, "evidence_count": len(evidence),
            "reopen_count": inc.reopen_count, "source_type": inc.source_type}
