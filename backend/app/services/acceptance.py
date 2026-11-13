"""Server intake and acceptance.

* A run snapshots the expected config, the profile, and the observations when it starts.
  It is executed by the backend job runner, check by check.
* Completed runs are immutable. Manual-review decisions are separate annotations.
  Re-tests create new runs with a new run number.
* Simulated corrections are explicit, labeled records attached to the intake. They change
  only the simulator's hardware model.
"""
from __future__ import annotations

import copy
import time
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from ..acceptance.checks import REGISTRY, disposition, effective_disposition
from ..collectors.redfish import RedfishClient, collect_observations
from ..models import utcnow
from . import common

COLLECTORS = {
    "simulator": {"label": "Simulator (modeled hardware)", "source_type": "SIMULATED"},
    "linux_upload": {"label": "Uploaded Linux collector output", "source_type": None},  # operator chooses LOCAL_LAB / IMPORTED_SAMPLE
    "redfish_fixture": {"label": "Redfish fixture (DMTF-style sample)", "source_type": "IMPORTED_SAMPLE"},
    "redfish_live": {"label": "Redfish endpoint (read-only)", "source_type": "LOCAL_LAB"},
}

# Labeled simulated corrections keyed by the failing check.
CORRECTIONS: dict[str, dict[str, Any]] = {
    "install_dimms": {
        "check": "memory_capacity",
        "label": "Install 4 × 16 GiB DDR5 RDIMMs in slots B1–B4 (simulated)",
        "physical_action": "Populate empty channel-B slots per the platform population guide; reseat and record serials.",
    },
    "replace_transceiver": {
        "check": "link_speed",
        "label": "Replace 1000BASE-SX SFP on eth1 with a 10GBASE-SR SFP+ (simulated)",
        "physical_action": "Swap the optic for the part on the build sheet; confirm the switch port is configured for 10G.",
    },
}


def _apply_correction_effect(hw: dict, key: str, expected: dict) -> None:
    if key == "install_dimms":
        mem = hw["memory"]
        have = {d["slot"] for d in mem["dimms"]}
        for slot in ("B1", "B2", "B3", "B4"):
            if slot not in have:
                mem["dimms"].append({"slot": slot, "size_gib": 16, "type": "DDR5 RDIMM", "serial": f"SIM-DIMM-{slot}-0099"})
        mem["total_gib"] = float(sum(d["size_gib"] for d in mem["dimms"]))
    elif key == "replace_transceiver":
        for n in hw["nics"]:
            if n.get("role") == "data":
                n["speed_mbps"] = expected["data_link_speed_mbps"]
                n["module"] = "10GBASE-SR SFP+ (SIM-SFP-10G-0042)"


# --------------------------------------------------------------------------- intake


def create_intake(db: Session, data: dict, actor: str) -> m.IntakeRecord:
    profile = db.scalar(select(m.AcceptanceProfile).where(m.AcceptanceProfile.key == data["profile_key"]))
    if profile is None:
        raise common.NotFound("Acceptance profile", data["profile_key"])
    if db.scalar(select(m.IntakeRecord).where(m.IntakeRecord.serial_number == data["serial_number"])):
        raise common.DomainError("duplicate_serial", f"An intake record already exists for serial {data['serial_number']}.")
    rack_id = None
    if data.get("intended_rack"):
        rack = db.scalar(select(m.Rack).where(m.Rack.display_id == data["intended_rack"]))
        if rack is None:
            raise common.NotFound("Rack", data["intended_rack"])
        rack_id = rack.id
        if data.get("intended_position_u"):
            from . import topology
            topology.assert_space_free(db, rack, data["intended_position_u"], data.get("u_height", 1), exclude_device_id=None)
            planned = db.scalar(select(m.IntakeRecord).where(
                m.IntakeRecord.intended_rack_id == rack.id, m.IntakeRecord.intended_position_u == data["intended_position_u"],
                m.IntakeRecord.status != "handed_off"))
            if planned:
                raise common.DomainError("rack_overlap", f"U{data['intended_position_u']} in {rack.display_id} is already planned for "
                                         f"{planned.hostname} ({planned.display_id}).", 409)
    rec = m.IntakeRecord(
        display_id=common.next_display_id(db, "INT"),
        asset_tag=data["asset_tag"], serial_number=data["serial_number"], hostname=data["hostname"],
        expected=data["expected"], intended_rack_id=rack_id, intended_position_u=data.get("intended_position_u"),
        profile_id=profile.id, source_type=data.get("source_type", "SIMULATED"), operator=actor, origin="operator",
        simulated_hardware=data.get("simulated_hardware"),
    )
    db.add(rec)
    db.flush()
    common.audit(db, actor=actor, action="intake.create", entity_type="intake", entity_id=rec.id, entity_display=rec.display_id,
                 summary=f"Intake recorded for {rec.hostname} (serial {rec.serial_number})", after={"expected": rec.expected})
    return rec


def available_corrections(db: Session, intake: m.IntakeRecord) -> list[dict]:
    last = _latest_run(db, intake)
    applied = {c["key"] for c in (intake.simulated_corrections or [])}
    if last is None or last.status != "completed" or intake.simulated_hardware is None:
        return []
    failing = {r.check_key for r in last.results if r.result == "FAIL"}
    return [{"key": k, **v, "applied": k in applied} for k, v in CORRECTIONS.items() if v["check"] in failing or k in applied]


def apply_correction(db: Session, intake: m.IntakeRecord, key: str, actor: str, now: Optional[datetime] = None) -> dict:
    now = now or utcnow()
    if key not in CORRECTIONS:
        raise common.NotFound("Correction", key)
    if intake.simulated_hardware is None:
        raise common.DomainError("not_simulated", "Simulated corrections apply only to intakes with a simulator hardware model.")
    if any(c["key"] == key for c in intake.simulated_corrections or []):
        raise common.DomainError("already_applied", "This correction has already been recorded.")
    hw = copy.deepcopy(intake.simulated_hardware)
    _apply_correction_effect(hw, key, intake.expected)
    before = intake.simulated_hardware
    intake.simulated_hardware = hw
    entry = {"key": key, "label": CORRECTIONS[key]["label"], "physical_action": CORRECTIONS[key]["physical_action"],
             "applied_at": common.dt(now), "actor": actor, "source_type": "SIMULATED"}
    intake.simulated_corrections = [*(intake.simulated_corrections or []), entry]
    run_id = intake.simulation_run_id or _demo_run_id(db)
    common.audit(db, actor=actor, action="intake.simulated_correction", entity_type="intake", entity_id=intake.id,
                 entity_display=intake.display_id, summary=f"Simulated correction recorded: {entry['label']}",
                 before={"memory_gib": before["memory"]["total_gib"]}, after={"memory_gib": hw["memory"]["total_gib"]},
                 origin="simulation", simulation_run_id=run_id, at=now)
    return entry


def _demo_run_id(db: Session) -> Optional[int]:
    run = db.scalar(select(m.SimulationRun).where(m.SimulationRun.demo_key == "acceptance-retest",
                                                  m.SimulationRun.status.in_(("running", "awaiting_operator"))))
    return run.id if run else None


def _latest_run(db: Session, intake: m.IntakeRecord) -> Optional[m.AcceptanceRun]:
    return db.scalar(select(m.AcceptanceRun).where(m.AcceptanceRun.intake_id == intake.id).order_by(m.AcceptanceRun.run_number.desc()).limit(1))


# --------------------------------------------------------------------------- runs


def _observe(db: Session, intake: m.IntakeRecord, collector: str) -> tuple[dict, str, str]:
    if collector == "simulator":
        if intake.simulated_hardware is None:
            raise common.DomainError("no_simulator_model", "This intake has no simulator hardware model.")
        obs = copy.deepcopy(intake.simulated_hardware)
        obs["_meta"] = {"collector": "simulator", "collected_at": common.dt(utcnow()), "host": intake.hostname}
        return obs, "SIMULATED", f"sim:intake:{intake.display_id}"
    if collector == "linux_upload":
        if not intake.uploaded_observations:
            raise common.DomainError("no_upload", "Upload Linux collector output for this intake first.")
        return copy.deepcopy(intake.uploaded_observations), intake.uploaded_source_type or "IMPORTED_SAMPLE", \
            f"upload:{intake.uploaded_observations.get('_meta', {}).get('host', 'unknown')}"
    if collector == "redfish_fixture":
        obs = collect_observations(RedfishClient(None))
        return obs, "IMPORTED_SAMPLE", "redfish-fixture:/redfish/v1/Systems/1"
    if collector == "redfish_live":
        client = RedfishClient.from_settings()
        if client.mode != "live":
            raise common.DomainError("redfish_unconfigured", "Redfish endpoint is not configured (RACKOPS_REDFISH_URL).", 409)
        return collect_observations(client), "LOCAL_LAB", f"redfish:{client.base_url}"
    raise common.DomainError("unknown_collector", f"Unknown collector '{collector}'", 404)


def start_run(db: Session, intake: m.IntakeRecord, collector: str, actor: str, now: Optional[datetime] = None) -> m.AcceptanceRun:
    now = now or utcnow()
    active = db.scalar(select(m.AcceptanceRun).where(m.AcceptanceRun.intake_id == intake.id,
                                                     m.AcceptanceRun.status.in_(("queued", "running"))))
    if active:
        raise common.DomainError("run_active", f"{active.display_id} is still {active.status}.", 409, {"run": active.display_id})
    obs, src, src_id = _observe(db, intake, collector)
    n = (db.scalar(select(func.max(m.AcceptanceRun.run_number)).where(m.AcceptanceRun.intake_id == intake.id)) or 0) + 1
    profile = intake.profile
    sim_run_id = _demo_run_id(db) if src == "SIMULATED" else None
    run = m.AcceptanceRun(
        display_id=common.next_display_id(db, "ACC"), intake=intake, run_number=n, status="queued",
        created_at=now, operator=actor, collector=collector, source_type=src, source_id=src_id,
        expected_snapshot=copy.deepcopy(intake.expected) | {"serial_number": intake.serial_number, "hostname": intake.hostname,
                                                             "asset_tag": intake.asset_tag},
        profile_snapshot={"key": profile.key, "name": profile.name, "version": profile.version, "checks": copy.deepcopy(profile.checks)},
        observed_snapshot=obs,
        corrections_before_run=copy.deepcopy(intake.simulated_corrections or []),
        origin="simulation" if src == "SIMULATED" else ("local_lab" if src == "LOCAL_LAB" else "imported"),
        simulation_run_id=sim_run_id,
    )
    db.add(run)
    db.flush()
    common.audit(db, actor=actor, action="acceptance.run_queued", entity_type="acceptance_run", entity_id=run.id,
                 entity_display=run.display_id, summary=f"Acceptance run #{n} queued for {intake.hostname} using {collector}",
                 origin=run.origin, simulation_run_id=sim_run_id, at=now,
                 related=[{"type": "intake", "id": intake.id, "display": intake.display_id}])
    common.publish(db, "acceptance", {"run": run.display_id, "id": run.id, "status": "queued"})
    return run


def execute_step(db: Session, run: m.AcceptanceRun, max_checks: int = 2, now: Optional[datetime] = None) -> bool:
    """Execute up to ``max_checks`` pending checks. Returns True when the run completed."""
    now = now or utcnow()
    if run.status == "completed":
        return True
    if run.status == "queued":
        run.status, run.started_at = "running", now
    done = {r.check_key for r in run.results}
    pending = [c for c in run.profile_snapshot["checks"] if c["check_key"] not in done]
    for spec in pending[:max_checks]:
        _execute_check(db, run, spec, now)
    db.flush()
    if len(pending) <= max_checks:
        _complete(db, run, now)
        return True
    common.publish(db, "acceptance", {"run": run.display_id, "id": run.id, "status": "running",
                                      "done": len(done) + min(max_checks, len(pending))})
    return False


def _execute_check(db: Session, run: m.AcceptanceRun, spec: dict, now: datetime) -> None:
    check = REGISTRY.get(spec["check_key"])
    t0 = time.perf_counter()
    if check is None:
        res = m.AcceptanceCheckResult(check_key=spec["check_key"], check_name=spec["check_key"], check_version="?",
                                      required=spec["required"], result="ERROR", detail="Check not implemented in this version",
                                      executed_at=now, source_type=run.source_type)
        run.results.append(res)
        return
    try:
        out = check.run(run.expected_snapshot, run.observed_snapshot)
    except Exception as e:  # a buggy check must surface as ERROR, never as PASS
        from ..acceptance.checks import CheckOutcome
        out = CheckOutcome("ERROR", detail=f"{type(e).__name__}: {e}")
    ev = None
    if out.evidence_output:
        ev = m.EvidenceItem(display_id=common.next_display_id(db, "EV"), acceptance_run_id=run.id,
                            device_id=run.intake.device_id, collector=check.key, command=out.evidence_command,
                            output=out.evidence_output[:20000], observations={"result": out.result},
                            interpretation=out.detail or f"{check.name}: {out.result}",
                            limitations="Rendered from the run's observation snapshot." +
                                        (" Simulated hardware model." if run.source_type == "SIMULATED" else ""),
                            source_type=run.source_type, source_id=run.source_id, collected_at=now,
                            simulation_run_id=run.simulation_run_id, origin=run.origin)
        db.add(ev)
        db.flush()
    run.results.append(m.AcceptanceCheckResult(
        check_key=check.key, check_name=check.name, check_version=check.version, required=spec["required"],
        result=out.result, expected_value=out.expected, observed_value=out.observed, unit=out.unit, detail=out.detail,
        evidence_item_id=ev.id if ev else None, executed_at=now, duration_ms=int((time.perf_counter() - t0) * 1000),
        source_type=run.source_type))
    if out.follow_up:
        run.follow_up_actions = [*run.follow_up_actions, *out.follow_up]


def _complete(db: Session, run: m.AcceptanceRun, now: datetime) -> None:
    db.flush()
    db.refresh(run)
    results = [{"check_key": r.check_key, "required": r.required, "result": r.result} for r in run.results]
    run.disposition = disposition(results)
    run.status, run.completed_at = "completed", now
    intake = run.intake
    intake.status = {"PASS": "accepted", "FAIL": "failed", "MANUAL_REVIEW": "manual_review"}[run.disposition]
    common.audit(db, actor=run.operator, action="acceptance.run_completed", entity_type="acceptance_run", entity_id=run.id,
                 entity_display=run.display_id, summary=f"Run #{run.run_number} for {intake.hostname}: {run.disposition}",
                 after={"disposition": run.disposition}, origin=run.origin, simulation_run_id=run.simulation_run_id, at=now,
                 related=[{"type": "intake", "id": intake.id, "display": intake.display_id}])
    common.publish(db, "acceptance", {"run": run.display_id, "id": run.id, "status": "completed", "disposition": run.disposition})


def execute_all(db: Session, run: m.AcceptanceRun, now: Optional[datetime] = None) -> m.AcceptanceRun:
    while not execute_step(db, run, max_checks=50, now=now):
        pass
    return run


def record_manual_review(db: Session, run: m.AcceptanceRun, check_key: str, decision: str, note: str, actor: str) -> m.AcceptanceRun:
    if run.status != "completed":
        raise common.DomainError("run_not_complete", "Manual review is recorded after the run completes.")
    res = next((r for r in run.results if r.check_key == check_key), None)
    if res is None:
        raise common.NotFound("Check result", check_key)
    if res.result not in ("MANUAL_REVIEW", "UNSUPPORTED", "SKIPPED", "ERROR"):
        raise common.DomainError("not_reviewable", f"{check_key} is {res.result}; only non-conclusive results can be reviewed.")
    if decision not in ("accept", "reject"):
        raise common.DomainError("invalid_decision", "Decision must be accept or reject.", 422)
    if not note.strip():
        raise common.DomainError("note_required", "Describe the evidence reviewed.", 422)
    reviews = dict(run.manual_reviews or {})
    reviews[check_key] = {"decision": decision, "note": note, "by": actor, "at": common.dt(utcnow())}
    run.manual_reviews = reviews
    eff = effective_disposition([{"check_key": r.check_key, "required": r.required, "result": r.result} for r in run.results], reviews)
    run.intake.status = {"PASS": "accepted", "FAIL": "failed", "MANUAL_REVIEW": "manual_review"}[eff]
    common.audit(db, actor=actor, action="acceptance.manual_review", entity_type="acceptance_run", entity_id=run.id,
                 entity_display=run.display_id, summary=f"Manual review of {check_key}: {decision}", after=reviews[check_key],
                 origin=run.origin, simulation_run_id=run.simulation_run_id)
    return run


def handoff(db: Session, intake: m.IntakeRecord, checklist: dict[str, bool], actor: str) -> m.IntakeRecord:
    last = _latest_run(db, intake)
    if last is None or last.status != "completed":
        raise common.DomainError("no_completed_run", "No completed acceptance run.")
    eff = run_effective(last)
    if eff != "PASS":
        raise common.DomainError("not_accepted", f"Latest run disposition is {eff}; handoff requires PASS.")
    missing = [k for k in HANDOFF_CHECKLIST if not checklist.get(k)]
    if missing:
        raise common.DomainError("checklist_incomplete", "Complete every handoff checklist item.", 422, {"missing": missing})
    intake.status = "handed_off"
    common.audit(db, actor=actor, action="intake.handoff", entity_type="intake", entity_id=intake.id, entity_display=intake.display_id,
                 summary=f"{intake.hostname} handed off to provisioning after {last.display_id}", after={"checklist": checklist},
                 origin="simulation" if last.source_type == "SIMULATED" else "operator", simulation_run_id=last.simulation_run_id)
    return intake


HANDOFF_CHECKLIST = {
    "labels_applied": "Asset tag and hostname labels applied front and rear",
    "rack_position_recorded": "Rack position recorded in the inventory system",
    "cabling_documented": "Cabling recorded with cable IDs on both ends",
    "bmc_credentials_vaulted": "BMC credentials rotated and stored in the vault (not in this tool)",
    "report_attached": "Acceptance report attached to the build ticket",
}


def run_effective(run: m.AcceptanceRun) -> Optional[str]:
    if run.status != "completed":
        return None
    return effective_disposition([{"check_key": r.check_key, "required": r.required, "result": r.result} for r in run.results],
                                 run.manual_reviews or {})


def compare(a: m.AcceptanceRun, b: m.AcceptanceRun) -> dict:
    ra = {r.check_key: r for r in a.results}
    rb = {r.check_key: r for r in b.results}
    rows = []
    for key in list(dict.fromkeys([*ra.keys(), *rb.keys()])):
        x, y = ra.get(key), rb.get(key)
        rows.append({
            "check_key": key, "check_name": (x or y).check_name, "required": (x or y).required,
            "a": {"result": x.result, "observed": x.observed_value, "unit": x.unit} if x else None,
            "b": {"result": y.result, "observed": y.observed_value, "unit": y.unit} if y else None,
            "changed": (x.result if x else None) != (y.result if y else None) or (x.observed_value if x else None) != (y.observed_value if y else None),
        })
    corrections = [c for c in b.corrections_before_run if c not in a.corrections_before_run]
    return {"a": a.display_id, "b": b.display_id, "a_disposition": a.disposition, "b_disposition": b.disposition,
            "rows": rows, "corrections_between": corrections}


# --------------------------------------------------------------------------- upload validation

ALLOWED_SECTIONS = {"identity", "cpu", "memory", "storage", "disk_health", "nics", "connectivity", "kernel_errors", "redfish", "_meta"}


def sanitize_upload(data: Any) -> dict:
    import re
    if not isinstance(data, dict):
        raise common.DomainError("invalid_upload", "Collector output must be a JSON object.", 422)
    unknown = set(data) - ALLOWED_SECTIONS
    if unknown:
        raise common.DomainError("invalid_upload", f"Unknown sections: {', '.join(sorted(unknown))}", 422)
    secret = re.compile(r"(?i)(password|passwd|token|secret|authorization)\s*[=:]\s*\S+")

    def clean(v, depth=0):
        if depth > 6:
            return None
        if isinstance(v, str):
            return secret.sub(r"\1=[redacted]", v)[:4000]
        if isinstance(v, list):
            return [clean(x, depth + 1) for x in v[:256]]
        if isinstance(v, dict):
            return {str(k)[:64]: clean(x, depth + 1) for k, x in list(v.items())[:128]}
        if isinstance(v, (int, float, bool)) or v is None:
            return v
        return str(v)[:200]

    return clean(data)
