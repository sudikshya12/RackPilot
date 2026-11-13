"""Deterministic simulation engine.

The engine is a pure function of (database state, now). The background runner calls
``tick(db, now)`` once a second, and tests call it with an injected clock. Every state
transition is persisted, so the simulation survives a restart.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models as m
from ..config import get_settings
from ..models import utcnow
from . import common
from .scenarios import SCENARIOS, Scenario

MAX_PROBES = 400          # safety cap: a forgotten drill pauses instead of growing forever
MAX_CATCH_UP = 3          # after downtime, replay at most this many missed probes, then re-anchor

ACTIVE = ("running", "awaiting_operator")


def interval() -> float:
    return get_settings().sim_probe_interval_seconds


def active_run_for(db: Session, scenario_key: str) -> Optional[m.SimulationRun]:
    return db.scalar(
        select(m.SimulationRun).where(
            m.SimulationRun.scenario_key == scenario_key,
            m.SimulationRun.status.in_(("running", "awaiting_operator", "paused")),
        )
    )


def start(db: Session, scenario_key: str, *, demo_key: Optional[str] = None, now: Optional[datetime] = None,
          actor: str = "operator") -> m.SimulationRun:
    now = now or utcnow()
    sc = SCENARIOS.get(scenario_key)
    if sc is None:
        raise common.DomainError("unknown_scenario", f"Unknown scenario '{scenario_key}'", 404)
    existing = active_run_for(db, scenario_key)
    if existing:
        raise common.DomainError(
            "scenario_active",
            f"Scenario {scenario_key} already has an active run ({existing.display_id}). Restart or exit it first.",
            409,
            {"simulation_run": existing.display_id},
        )
    device = db.scalar(select(m.Device).where(m.Device.display_id == sc.device))
    run = m.SimulationRun(
        display_id=common.next_display_id(db, "SIM"),
        scenario_key=sc.key,
        demo_key=demo_key,
        status="running",
        phase="baseline",
        probe_count=0,
        state=sc.initial_state() | {"consecutive_failed": 0},
        started_at=now,
        next_tick_at=now,
        device_id=device.id if device else None,
    )
    db.add(run)
    db.flush()
    if device:
        device.health, device.health_source, device.health_updated_at = "healthy", "SIMULATED", now
    common.audit(db, actor=actor, action="simulation.start", entity_type="simulation_run", entity_id=run.id,
                 entity_display=run.display_id, summary=f"Started scenario '{sc.title}' ({sc.key})",
                 origin="simulation", simulation_run_id=run.id, at=now)
    common.publish(db, "simulation", {"run": run.display_id, "event": "started", "scenario": sc.key})
    return run


def tick(db: Session, now: Optional[datetime] = None) -> int:
    """Advance every due simulation run. Returns number of probes executed."""
    now = now or utcnow()
    runs = db.scalars(
        select(m.SimulationRun).where(m.SimulationRun.status.in_(ACTIVE), m.SimulationRun.next_tick_at <= now)
    ).all()
    count = 0
    step = timedelta(seconds=interval())
    for run in runs:
        done = 0
        while run.next_tick_at is not None and run.next_tick_at <= now and run.status in ACTIVE:
            if done >= MAX_CATCH_UP:
                run.next_tick_at = now + step  # re-anchor rather than replaying a long outage
                break
            at = run.next_tick_at
            _probe(db, run, at)
            run.next_tick_at = at + step
            done += 1
            count += 1
    return count


def _probe(db: Session, run: m.SimulationRun, at: datetime) -> None:
    sc = SCENARIOS[run.scenario_key]
    state = copy.deepcopy(run.state)
    n = run.probe_count
    state["probe"] = n

    if run.phase == "baseline" and n >= sc.baseline_probes:
        sc.inject(state)
        run.phase = "fault"
        state["fault_at"] = common.dt(at)
        common.publish(db, "simulation", {"run": run.display_id, "event": "fault_injected", "scenario": sc.key})
    elif run.phase in ("fault", "incident") and sc.progress:
        sc.progress(state)

    failing = sc.failing(state)
    src = f"sim:{sc.key}:{run.display_id}"
    for metric, value, unit, labels in sc.metrics(state, n):
        db.add(m.MetricObservation(device_id=run.device_id, metric=metric, value=value, unit=unit, labels=labels,
                                   observed_at=at, source_type="SIMULATED", source_id=src, simulation_run_id=run.id))

    if run.phase == "fault":
        state["consecutive_failed"] = state.get("consecutive_failed", 0) + 1 if failing else 0
        if state["consecutive_failed"] >= sc.detect_after_failed:
            from . import incidents  # local import to avoid cycle
            inc = incidents.create_from_simulation(db, run, sc, state, detected_at=at)
            run.incident_id = inc.id
            run.phase = "incident"
            run.status = "awaiting_operator"
    elif run.phase == "incident":
        if not failing and state["repairs"]:
            state["healthy_since_repair"] = state.get("healthy_since_repair", 0) + 1
        else:
            state["healthy_since_repair"] = 0

    _set_device_health(db, run, sc, failing, at)
    run.probe_count = n + 1
    run.state = state
    if run.probe_count >= MAX_PROBES:
        run.status, run.paused_at = "paused", at
        common.publish(db, "simulation", {"run": run.display_id, "event": "auto_paused"})
    common.publish(db, "probe", {"run": run.display_id, "probe": n, "failing": failing, "device_id": run.device_id})


def _set_device_health(db: Session, run: m.SimulationRun, sc: Scenario, failing: bool, at: datetime) -> None:
    if not run.device_id:
        return
    dev = db.get(m.Device, run.device_id)
    target = ("critical" if sc.severity == "critical" else "degraded") if failing else "healthy"
    if dev.health != target:
        dev.health = target
        common.publish(db, "device", {"device_id": dev.id, "health": target})
    dev.health_source, dev.health_updated_at = "SIMULATED", at


def update_state(db: Session, run: m.SimulationRun, new_state: dict) -> None:
    run.state = new_state


def pause(db: Session, run: m.SimulationRun, now: Optional[datetime] = None) -> None:
    if run.status not in ACTIVE:
        raise common.DomainError("not_running", f"{run.display_id} is {run.status}; only running runs can be paused.")
    run.state = run.state | {"resume_status": run.status}
    run.status, run.paused_at = "paused", now or utcnow()
    common.publish(db, "simulation", {"run": run.display_id, "event": "paused"})


def resume(db: Session, run: m.SimulationRun, now: Optional[datetime] = None) -> None:
    if run.status != "paused":
        raise common.DomainError("not_paused", f"{run.display_id} is not paused.")
    now = now or utcnow()
    run.status = run.state.get("resume_status", "running")
    run.paused_at, run.next_tick_at = None, now
    common.publish(db, "simulation", {"run": run.display_id, "event": "resumed"})


def complete(db: Session, run: m.SimulationRun, now: Optional[datetime] = None) -> None:
    run.status, run.completed_at, run.next_tick_at = "completed", now or utcnow(), None
    common.publish(db, "simulation", {"run": run.display_id, "event": "completed"})


def purge_run(db: Session, run: m.SimulationRun) -> None:
    """Delete every record owned by a simulation run (DB-level cascades) and restore seed baselines."""
    from ..seed import restore_seed_baseline

    db.execute(delete(m.SimulationRun).where(m.SimulationRun.id == run.id))
    db.flush()
    db.expire_all()
    restore_seed_baseline(db)
    common.publish(db, "simulation", {"event": "purged"})


def reset_all(db: Session) -> dict:
    """Reset ONLY simulation-owned records. Imported, local-lab and operator records are untouched."""
    from ..seed import restore_seed_baseline

    counts = {}
    for model in (m.Incident, m.AcceptanceRun, m.Reservation, m.InventoryTransaction, m.ReturnRecord,
                  m.EvidenceItem, m.MetricObservation, m.AuditEvent, m.Asset):
        counts[model.__tablename__] = db.query(model).filter(model.simulation_run_id.isnot(None)).count()
    counts["simulation_runs"] = db.query(m.SimulationRun).count()
    db.execute(delete(m.SimulationRun))
    # Rows created with origin=simulation but no run (defensive) are also simulation-owned.
    for model in (m.Incident, m.AcceptanceRun, m.Reservation, m.InventoryTransaction, m.ReturnRecord, m.EvidenceItem, m.Asset):
        db.execute(delete(model).where(model.origin == "simulation"))
    db.execute(delete(m.MetricObservation).where(m.MetricObservation.source_type == "SIMULATED"))
    db.flush()
    db.expire_all()
    restore_seed_baseline(db)
    common.publish(db, "simulation", {"event": "reset"})
    return counts
