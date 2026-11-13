"""ORM → API payloads. Provenance fields are always included for measurements and evidence."""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .services import acceptance as acc
from .services import incidents as inc_svc
from .services.common import dt


def device_ref(d: Optional[m.Device]) -> Optional[dict]:
    if d is None:
        return None
    return {"id": d.id, "display_id": d.display_id, "role": d.role, "model": d.model, "health": d.health,
            "rack": d.rack.display_id if d.rack else None, "position_u": d.position_u}


def incident_summary(db: Session, i: m.Incident) -> dict:
    run = db.get(m.SimulationRun, i.simulation_run_id) if i.simulation_run_id else None
    return {
        "id": i.id, "display_id": i.display_id, "title": i.title, "severity": i.severity, "status": i.status, "symptom": i.symptom,
        "device": device_ref(i.device), "scenario_key": i.scenario_key, "source_type": i.source_type, "source_id": i.source_id,
        "detected_at": dt(i.detected_at), "fault_onset_at": dt(i.fault_onset_at), "acknowledged_at": dt(i.acknowledged_at),
        "resolved_at": dt(i.resolved_at), "assigned_operator": i.assigned_operator, "next_step": inc_svc.next_step(db, i),
        "reopen_count": i.reopen_count, "simulation_run": run.display_id if run else None,
        "simulation_status": run.status if run else None, "demo_key": run.demo_key if run else None,
        "origin": i.origin,
    }


def evidence(e: m.EvidenceItem) -> dict:
    return {"id": e.id, "display_id": e.display_id, "collector": e.collector, "command": e.command, "output": e.output,
            "observations": e.observations, "interpretation": e.interpretation, "limitations": e.limitations,
            "source_type": e.source_type, "source_id": e.source_id, "collected_at": dt(e.collected_at),
            "simulation_run_id": e.simulation_run_id, "incident_id": e.incident_id, "acceptance_run_id": e.acceptance_run_id,
            "device_id": e.device_id}


def incident_detail(db: Session, i: m.Incident) -> dict:
    out = incident_summary(db, i)
    ev = db.scalars(select(m.EvidenceItem).where(m.EvidenceItem.incident_id == i.id).order_by(m.EvidenceItem.id)).all()
    run = db.get(m.SimulationRun, i.simulation_run_id) if i.simulation_run_id else None
    out.update({
        "detection_rule": i.detection_rule, "runbook_slug": i.runbook_slug, "root_cause": i.root_cause,
        "repair_applied_at": dt(i.repair_applied_at), "verified_at": dt(i.verified_at),
        "events": [{"id": e.id, "kind": e.kind, "occurred_at": dt(e.occurred_at), "actor": e.actor, "summary": e.summary,
                    "from_status": e.from_status, "to_status": e.to_status, "detail": e.detail} for e in i.events],
        "hypotheses": [{"id": h.id, "key": h.key, "statement": h.statement, "discriminating_check": h.discriminating_check,
                        "status": h.status, "note": h.note} for h in i.hypotheses],
        "repairs": [{"id": r.id, "action_key": r.action_key, "description": r.description, "applied_at": dt(r.applied_at),
                     "actor": r.actor, "source_type": r.source_type} for r in i.repairs],
        "verifications": [{"id": v.id, "executed_at": dt(v.executed_at), "passed": v.passed, "checks": v.checks,
                           "after_repair_id": v.after_repair_id, "source_type": v.source_type, "source_id": v.source_id}
                          for v in i.verifications],
        "evidence": [evidence(e) for e in ev],
        "collectors": inc_svc.collectors_for(db, i),
        "repair_options": inc_svc.repair_options(db, i),
        "metrics": inc_svc.incident_metrics(i),
        "simulation": {"display_id": run.display_id, "status": run.status, "phase": run.phase, "probe_count": run.probe_count,
                       "healthy_since_repair": run.state.get("healthy_since_repair", 0), "demo_key": run.demo_key} if run else None,
        "allowed_transitions": sorted(inc_svc.TRANSITIONS.get(i.status, set())),
    })
    return out


def asset(a: m.Asset) -> dict:
    return {"id": a.id, "display_id": a.display_id, "serial_number": a.serial_number, "asset_type": a.asset_type,
            "manufacturer": a.manufacturer, "model": a.model, "status": a.status, "location": a.location,
            "installed_in": device_ref(a.installed_in), "warranty_status": a.warranty_status, "warranty_end": dt(a.warranty_end),
            "part_number": a.part_type.part_number if a.part_type else None, "notes": a.notes, "origin": a.origin,
            "simulation_run_id": a.simulation_run_id}


def run_summary(r: m.AcceptanceRun) -> dict:
    counts: dict[str, int] = {}
    for x in r.results:
        counts[x.result] = counts.get(x.result, 0) + 1
    return {"id": r.id, "display_id": r.display_id, "intake_id": r.intake_id, "intake": r.intake.display_id,
            "hostname": r.intake.hostname, "run_number": r.run_number, "status": r.status, "disposition": r.disposition,
            "effective_disposition": acc.run_effective(r), "created_at": dt(r.created_at), "started_at": dt(r.started_at),
            "completed_at": dt(r.completed_at), "operator": r.operator, "collector": r.collector, "source_type": r.source_type,
            "source_id": r.source_id, "counts": counts, "checks_total": len(r.profile_snapshot.get("checks", [])),
            "checks_done": len(r.results), "origin": r.origin}


def run_detail(db: Session, r: m.AcceptanceRun) -> dict:
    out = run_summary(r)
    ev = {e.id: e for e in db.scalars(select(m.EvidenceItem).where(m.EvidenceItem.acceptance_run_id == r.id)).all()}
    out.update({
        "expected_snapshot": r.expected_snapshot, "profile_snapshot": r.profile_snapshot, "observed_snapshot": r.observed_snapshot,
        "corrections_before_run": r.corrections_before_run, "manual_reviews": r.manual_reviews, "follow_up_actions": r.follow_up_actions,
        "results": [{"id": x.id, "check_key": x.check_key, "check_name": x.check_name, "check_version": x.check_version,
                     "required": x.required, "result": x.result, "expected_value": x.expected_value, "observed_value": x.observed_value,
                     "unit": x.unit, "detail": x.detail, "executed_at": dt(x.executed_at), "duration_ms": x.duration_ms,
                     "source_type": x.source_type, "evidence": evidence(ev[x.evidence_item_id]) if x.evidence_item_id in ev else None}
                    for x in r.results],
    })
    return out


def intake(db: Session, rec: m.IntakeRecord) -> dict:
    runs = [run_summary(r) for r in rec.runs]
    return {"id": rec.id, "display_id": rec.display_id, "asset_tag": rec.asset_tag, "serial_number": rec.serial_number,
            "hostname": rec.hostname, "expected": rec.expected, "intended_rack": rec.intended_rack.display_id if rec.intended_rack else None,
            "intended_position_u": rec.intended_position_u, "profile": {"key": rec.profile.key, "name": rec.profile.name,
                                                                         "version": rec.profile.version, "checks": rec.profile.checks},
            "source_type": rec.source_type, "status": rec.status, "operator": rec.operator, "created_at": dt(rec.created_at),
            "has_simulator_model": rec.simulated_hardware is not None, "simulated_corrections": rec.simulated_corrections or [],
            "has_upload": rec.uploaded_observations is not None, "uploaded_source_type": rec.uploaded_source_type,
            "available_corrections": acc.available_corrections(db, rec), "runs": runs, "origin": rec.origin,
            "handoff_checklist": acc.HANDOFF_CHECKLIST}


def reservation(r: m.Reservation) -> dict:
    return {"id": r.id, "display_id": r.display_id, "stock_id": r.stock_id, "stock": r.stock.display_id,
            "part_number": r.stock.part_type.part_number, "part_name": r.stock.part_type.name, "quantity": r.quantity,
            "status": r.status, "device": device_ref(r.device), "incident_id": r.incident_id, "reason": r.reason,
            "compatibility_exception": r.compatibility_exception, "exception_reviewed_by": r.exception_reviewed_by,
            "exception_note": r.exception_note, "actor": r.actor, "created_at": dt(r.created_at), "consumed_at": dt(r.consumed_at),
            "released_at": dt(r.released_at), "origin": r.origin}


def txn(t: m.InventoryTransaction) -> dict:
    return {"id": t.id, "display_id": t.display_id, "occurred_at": dt(t.occurred_at), "stock": t.stock.display_id,
            "part_number": t.stock.part_type.part_number, "kind": t.kind, "quantity_delta": t.quantity_delta,
            "reservation_id": t.reservation_id, "asset_id": t.asset_id, "note": t.note, "actor": t.actor, "origin": t.origin}


def return_record(r: m.ReturnRecord) -> dict:
    return {"id": r.id, "display_id": r.display_id, "failed_asset": asset(r.failed_asset),
            "replacement_asset": asset(r.replacement_asset) if r.replacement_asset else None,
            "original_device": device_ref(r.original_device), "incident_id": r.incident_id,
            "failure_evidence_id": r.failure_evidence_id, "failure_summary": r.failure_summary, "warranty_status": r.warranty_status,
            "return_reference": r.return_reference, "shipping_status": r.shipping_status, "actor": r.actor,
            "created_at": dt(r.created_at), "updated_at": dt(r.updated_at), "origin": r.origin}


def audit_event(a: m.AuditEvent) -> dict:
    return {"id": a.id, "occurred_at": dt(a.occurred_at), "actor": a.actor, "action": a.action, "entity_type": a.entity_type,
            "entity_id": a.entity_id, "entity_display": a.entity_display, "summary": a.summary, "before": a.before, "after": a.after,
            "related": a.related, "origin": a.origin, "simulation_run_id": a.simulation_run_id}


def cable(c: m.CableConnection) -> dict:
    def end(i: m.DeviceInterface):
        return {"interface_id": i.id, "interface": i.name, "device_id": i.device_id, "device": i.device.display_id,
                "connector": i.connector_type, "kind": i.kind, "rack": i.device.rack.display_id if i.device.rack else None}
    return {"id": c.id, "label": c.label, "cable_type": c.cable_type, "a": end(c.a_interface), "b": end(c.b_interface),
            "intended_speed_mbps": c.intended_speed_mbps, "length_m": c.length_m, "status": c.status, "notes": c.notes, "origin": c.origin}
