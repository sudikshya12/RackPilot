"""Backend-owned job runner.

A single asyncio task runs once per second. Each tick:
  1. advances due simulation runs (deterministic probes and fault progression),
  2. executes pending acceptance checks (a few per tick, so progress is visible),
  3. probes the live-lab target, when the operator has enabled it (real, LOCAL_LAB).
Every unit of work commits its own short transaction.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from . import models as m
from .config import get_settings
from .db import write_session
from .models import utcnow
from .services import acceptance, common, simulation

log = logging.getLogger("rackops.runner")
_last_live_probe: dict[str, datetime] = {}


def run_once(now: datetime | None = None) -> None:
    now = now or utcnow()
    with write_session() as db:
        try:
            simulation.tick(db, now)
            db.commit()
        except Exception:  # keep the runner alive; surface in logs
            db.rollback()
            log.exception("simulation tick failed")
    with write_session() as db:
        try:
            for run in db.scalars(select(m.AcceptanceRun).where(m.AcceptanceRun.status.in_(("queued", "running")))
                                  .order_by(m.AcceptanceRun.id)).all():
                acceptance.execute_step(db, run, max_checks=2, now=now)
            db.commit()
        except Exception:
            db.rollback()
            log.exception("acceptance step failed")
    with write_session() as db:
        try:
            if common.get_setting(db, "livelab_enabled", False):
                last = _last_live_probe.get("t")
                if last is None or now - last >= timedelta(seconds=get_settings().sim_probe_interval_seconds):
                    _last_live_probe["t"] = now
                    live_probe(db, now)
                    db.commit()
        except Exception:
            db.rollback()
            log.exception("live-lab probe failed")


def live_probe(db, now: datetime) -> None:
    """Real probe of the lab-owned target. Creates a LOCAL_LAB incident after 2 consecutive failures."""
    from .livelab import manager
    from .services import incidents

    h = manager.health()
    dev = db.scalar(select(m.Device).where(m.Device.display_id == "livelab-target"))
    db.add(m.MetricObservation(device_id=dev.id if dev else None, metric="service_up", value=1.0 if h["ok"] else 0.0, unit="bool",
                               labels={"service": "rackops-lab-target"}, observed_at=now, source_type="LOCAL_LAB",
                               source_id=f"livelab:{h['url']}"))
    if h["latency_ms"] is not None:
        db.add(m.MetricObservation(device_id=dev.id if dev else None, metric="http_latency_ms", value=h["latency_ms"], unit="ms",
                                   labels={"probe": "GET /health"}, observed_at=now, source_type="LOCAL_LAB", source_id=f"livelab:{h['url']}"))
    st = dict(common.get_setting(db, "livelab_state", {}) or {})
    open_inc = db.get(m.Incident, st["open_incident_id"]) if st.get("open_incident_id") else None
    if open_inc and open_inc.status == "resolved":
        open_inc, st["open_incident_id"] = None, None
    manager.note_probe(h["ok"], bool(open_inc and open_inc.repairs))
    st["consecutive_failed"] = 0 if h["ok"] else st.get("consecutive_failed", 0) + 1
    if dev:
        dev.health, dev.health_source, dev.health_updated_at = ("healthy" if h["ok"] else "critical"), "LOCAL_LAB", now
    if not h["ok"] and st["consecutive_failed"] >= 2 and open_inc is None:
        stop_at = st.get("operator_stop_at")
        onset = datetime.fromisoformat(stop_at.replace("Z", "+00:00")) if stop_at else None
        inc = m.Incident(display_id=common.next_display_id(db, "INC"), title="Live lab target not responding",
                         symptom=f"Real GET {h['url']} failing: {h.get('error') or h.get('status_code')}",
                         severity="critical", status="detected", device_id=dev.id if dev else None, scenario_key="livelab-svc",
                         runbook_slug="service-not-responding",
                         detection_rule=f"Real HTTP probe of {h['url']} failed 2 consecutive times",
                         source_type="LOCAL_LAB", source_id=f"livelab:{h['url']}", fault_onset_at=onset, detected_at=now,
                         origin="local_lab")
        db.add(inc)
        db.flush()
        incidents._event(db, inc, "fault_onset",
                         "Fault onset: operator stopped the target from Settings (recorded time)." if onset else
                         "Fault onset unknown: the target stopped without an operator stop being recorded.",
                         at=onset or now, detail={"known": bool(onset)})
        incidents._event(db, inc, "detected", f"Detected by rule: {inc.detection_rule}", at=now)
        inc.hypotheses.append(m.Hypothesis(key="svc_stopped", statement="The lab target process is not running.",
                            discriminating_check="Process check of the lab-started PID; TCP listener check."))
        inc.hypotheses.append(m.Hypothesis(key="port_conflict", statement="Another process holds the port or the target cannot bind.",
                            discriminating_check="Listener present but /health marker missing."))
        common.audit(db, actor="detector", action="incident.detected", entity_type="incident", entity_id=inc.id,
                     entity_display=inc.display_id, summary=f"{inc.display_id} detected (LOCAL LAB)", origin="local_lab", at=now)
        st["open_incident_id"] = inc.id
    common.set_setting(db, "livelab_state", st)
    common.publish(db, "probe", {"livelab": True, "ok": h["ok"]})


async def runner_loop(stop: asyncio.Event) -> None:
    interval = get_settings().runner_tick_seconds
    while not stop.is_set():
        await asyncio.to_thread(run_once)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
