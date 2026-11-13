import asyncio
import json
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, Header, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from .. import serializers as ser
from ..config import get_settings
from ..db import SessionLocal, get_db, get_write_db
from ..deps import actor, require_mutations
from ..models import utcnow
from ..services import acceptance as acc
from ..services import common, demos, inventory as inv, simulation

router = APIRouter(prefix="/api", tags=["platform"])


@router.get("/health")
def health():
    return {"status": "ok", "time": common.dt(utcnow())}


# --------------------------------------------------------------------------- overview


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    devs = db.scalars(select(m.Device).where(m.Device.role.in_(("server", "switch")))).all()
    by_health: dict[str, int] = {}
    for d in devs:
        by_health[d.health] = by_health.get(d.health, 0) + 1
    open_incs = db.scalars(select(m.Incident).where(m.Incident.status != "resolved")).all()
    by_src: dict[str, int] = {}
    for i in open_incs:
        by_src[i.source_type] = by_src.get(i.source_type, 0) + 1
    review = [x for x in db.scalars(select(m.IntakeRecord)).all() if x.status == "manual_review"]
    awaiting = [x for x in db.scalars(select(m.IntakeRecord)).all() if x.status == "awaiting_acceptance"]
    stock = [inv.stock_view(db, x) for x in db.scalars(select(m.SpareStock)).all()]
    low = [x for x in stock if x["low_stock"]]
    recent = db.scalars(select(m.AuditEvent).order_by(m.AuditEvent.occurred_at.desc(), m.AuditEvent.id.desc()).limit(60)).all()
    runs = db.scalars(select(m.AcceptanceRun).order_by(m.AcceptanceRun.id.desc()).limit(6)).all()
    txns = db.scalars(select(m.InventoryTransaction).order_by(m.InventoryTransaction.occurred_at.desc(), m.InventoryTransaction.id.desc()).limit(6)).all()
    latest = db.scalar(select(func.max(m.AuditEvent.occurred_at)))
    return {
        "generated_at": common.dt(utcnow()), "last_change_at": common.dt(latest),
        "devices": {"total": len(devs), "by_health": by_health, "healthy": by_health.get("healthy", 0)},
        "open_incidents": {"total": len(open_incs), "by_source": by_src,
                           "critical": sum(1 for i in open_incs if i.severity == "critical")},
        "acceptance": {"manual_review": len(review), "awaiting": len(awaiting),
                       "manual_review_items": [{"id": x.id, "display_id": x.display_id, "hostname": x.hostname} for x in review]},
        "low_stock": {"total": len(low), "items": low},
        "recent_events": [ser.audit_event(a) for a in recent],
        "acceptance_runs": [ser.run_summary(r) for r in runs],
        "inventory_movements": [ser.txn(t) for t in txns],
        "simulation_active": db.query(m.SimulationRun).filter(m.SimulationRun.status.in_(("running", "awaiting_operator", "paused"))).count(),
    }


@router.get("/search")
def search(q: str = Query(..., min_length=1, max_length=80), db: Session = Depends(get_db)):
    like = f"%{q}%"
    out = []
    for d in db.scalars(select(m.Device).where(or_(m.Device.display_id.ilike(like), m.Device.model.ilike(like))).limit(8)).all():
        out.append({"type": "device", "id": d.id, "label": d.display_id, "sub": f"{d.role} · {d.model}",
                    "route": f"/assets/{d.asset_id}" if d.asset_id else f"/infrastructure?device={d.display_id}"})
    for a in db.scalars(select(m.Asset).where(or_(m.Asset.display_id.ilike(like), m.Asset.serial_number.ilike(like))).limit(8)).all():
        out.append({"type": "asset", "id": a.id, "label": a.display_id, "sub": f"{a.serial_number} · {a.status}", "route": f"/assets/{a.id}"})
    for i in db.scalars(select(m.Incident).where(or_(m.Incident.display_id.ilike(like), m.Incident.title.ilike(like))).limit(8)).all():
        out.append({"type": "incident", "id": i.id, "label": i.display_id, "sub": f"{i.title} · {i.status}", "route": f"/incidents/{i.id}"})
    for x in db.scalars(select(m.IntakeRecord).where(or_(m.IntakeRecord.display_id.ilike(like), m.IntakeRecord.hostname.ilike(like),
                                                         m.IntakeRecord.serial_number.ilike(like))).limit(5)).all():
        out.append({"type": "intake", "id": x.id, "label": x.display_id, "sub": f"{x.hostname} · {x.status}", "route": f"/acceptance/{x.id}"})
    for c in db.scalars(select(m.CableConnection).where(m.CableConnection.label.ilike(like)).limit(5)).all():
        out.append({"type": "cable", "id": c.id, "label": c.label, "sub": c.cable_type, "route": f"/infrastructure?cable={c.id}"})
    return out[:30]


@router.get("/audit")
def audit(db: Session = Depends(get_db), entity_type: Optional[str] = None, entity_id: Optional[int] = None,
          origin: Optional[str] = None, limit: int = Query(100, le=500), offset: int = 0):
    q = select(m.AuditEvent)
    if entity_type:
        q = q.where(m.AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        q = q.where(m.AuditEvent.entity_id == entity_id)
    if origin:
        q = q.where(m.AuditEvent.origin.in_(origin.split(",")))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(m.AuditEvent.occurred_at.desc(), m.AuditEvent.id.desc()).limit(limit).offset(offset)).all()
    return {"items": [ser.audit_event(a) for a in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/simulation/runs")
def sim_runs(db: Session = Depends(get_db)):
    rows = db.scalars(select(m.SimulationRun).order_by(m.SimulationRun.id.desc()).limit(30)).all()
    return [{"id": r.id, "display_id": r.display_id, "scenario_key": r.scenario_key, "demo_key": r.demo_key, "status": r.status,
             "phase": r.phase, "probe_count": r.probe_count, "started_at": common.dt(r.started_at), "incident_id": r.incident_id}
            for r in rows]


def _sim_run(db, ident) -> m.SimulationRun:
    return common.get_or_404(db, m.SimulationRun, ident, "Simulation run")


@router.post("/simulation/runs/{ident}/pause", dependencies=[Depends(require_mutations)])
def sim_pause(ident: str, db: Session = Depends(get_write_db)):
    r = _sim_run(db, ident)
    simulation.pause(db, r)
    db.commit()
    return {"status": r.status}


@router.post("/simulation/runs/{ident}/resume", dependencies=[Depends(require_mutations)])
def sim_resume(ident: str, db: Session = Depends(get_write_db)):
    r = _sim_run(db, ident)
    simulation.resume(db, r)
    db.commit()
    return {"status": r.status}


@router.delete("/simulation/runs/{ident}", dependencies=[Depends(require_mutations)])
def sim_delete(ident: str, db: Session = Depends(get_write_db)):
    simulation.purge_run(db, _sim_run(db, ident))
    db.commit()
    return {"deleted": True}


@router.post("/simulation/reset", dependencies=[Depends(require_mutations)])
def sim_reset(db: Session = Depends(get_write_db)):
    counts = simulation.reset_all(db)
    db.commit()
    return {"reset": True, "removed": counts,
            "preserved": "Imported, local-lab and operator records were not touched."}


# --------------------------------------------------------------------------- demos


@router.get("/demos")
def demo_list(db: Session = Depends(get_db)):
    return [demos.status(db, k) for k in demos.DEMOS]


@router.get("/demos/{key}")
def demo_get(key: str, db: Session = Depends(get_db)):
    if key not in demos.DEMOS:
        raise common.NotFound("Demo", key)
    return demos.status(db, key)


@router.post("/demos/{key}/start", dependencies=[Depends(require_mutations)])
def demo_start(key: str, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    demos.start(db, key, who)
    db.commit()
    return demos.status(db, key)


@router.post("/demos/{key}/next", dependencies=[Depends(require_mutations)])
def demo_next(key: str, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    res = demos.next_step(db, key, who)
    db.commit()
    return res | {"status": demos.status(db, key)}


@router.post("/demos/{key}/view/{step}", dependencies=[Depends(require_mutations)])
def demo_view(key: str, step: str, db: Session = Depends(get_write_db)):
    run = demos._latest(db, key)
    if run is None:
        raise common.DomainError("demo_not_started", "Start the demo first.")
    demos.mark_viewed(db, run, step)
    db.commit()
    return demos.status(db, key)


@router.post("/demos/{key}/pause", dependencies=[Depends(require_mutations)])
def demo_pause(key: str, db: Session = Depends(get_write_db)):
    run = demos._active(db, key)
    if run is None:
        raise common.DomainError("demo_not_started", "No active demo run.")
    if run.next_tick_at is None and run.status == "awaiting_operator" and run.scenario_key == "acceptance-retest":
        run.state = run.state | {"resume_status": run.status}
        run.status = "paused"
    else:
        simulation.pause(db, run)
    db.commit()
    return demos.status(db, key)


@router.post("/demos/{key}/resume", dependencies=[Depends(require_mutations)])
def demo_resume(key: str, db: Session = Depends(get_write_db)):
    run = demos._active(db, key)
    if run is None or run.status != "paused":
        raise common.DomainError("not_paused", "Demo is not paused.")
    if run.scenario_key == "acceptance-retest":
        run.status = run.state.get("resume_status", "awaiting_operator")
    else:
        simulation.resume(db, run)
    db.commit()
    return demos.status(db, key)


@router.post("/demos/{key}/exit", dependencies=[Depends(require_mutations)])
def demo_exit(key: str, db: Session = Depends(get_write_db)):
    demos.exit_demo(db, key)
    db.commit()
    return {"exited": True}


# --------------------------------------------------------------------------- portfolio & settings


@router.get("/profile")
def get_profile(db: Session = Depends(get_db)):
    p = db.scalar(select(m.CandidateProfile).limit(1))
    notes = {n.slug: {"candidate_contribution": n.candidate_contribution, "lessons_learned": n.lessons_learned}
             for n in db.scalars(select(m.ProjectNote)).all()}
    return {"name": p.name, "headline": p.headline, "summary": p.summary, "links": p.links, "operator_name": p.operator_name,
            "project_notes": notes}


@router.put("/profile", dependencies=[Depends(require_mutations)])
def put_profile(body: s.ProfileIn, db: Session = Depends(get_write_db)):
    p = db.scalar(select(m.CandidateProfile).limit(1))
    p.name, p.headline, p.summary, p.links, p.operator_name = body.name, body.headline, body.summary, body.links, body.operator_name
    db.commit()
    return get_profile(db)


@router.put("/projects/{slug}/notes", dependencies=[Depends(require_mutations)])
def put_notes(slug: str, body: s.ProjectNoteIn, db: Session = Depends(get_write_db)):
    n = db.scalar(select(m.ProjectNote).where(m.ProjectNote.slug == slug))
    if n is None:
        raise common.NotFound("Project", slug)
    n.candidate_contribution, n.lessons_learned = body.candidate_contribution, body.lessons_learned
    db.commit()
    return {"slug": slug, "candidate_contribution": n.candidate_contribution, "lessons_learned": n.lessons_learned}


@router.get("/projects/{slug}/results")
def project_results(slug: str, db: Session = Depends(get_db)):
    """Collected results for a case study, separated by source. Nothing here is invented."""
    from ..services import incidents as inc_svc
    if slug == "incident-recovery":
        return inc_svc.aggregate_metrics(db)
    if slug == "server-acceptance":
        runs = db.scalars(select(m.AcceptanceRun).where(m.AcceptanceRun.status == "completed").order_by(m.AcceptanceRun.id)).all()
        by: dict[str, dict] = {}
        for r in runs:
            b = by.setdefault(r.source_type, {"runs": 0, "PASS": 0, "FAIL": 0, "MANUAL_REVIEW": 0, "items": []})
            b["runs"] += 1
            b[r.disposition] += 1
            b["items"].append(ser.run_summary(r))
        return {"by_source": by}
    if slug == "rack-lifecycle":
        from ..services import topology
        return {"cable_issues": topology.cable_audit(db), "power": topology.power_overview(db),
                "reservations": [ser.reservation(r) for r in db.scalars(select(m.Reservation)).all()],
                "returns": [ser.return_record(r) for r in db.scalars(select(m.ReturnRecord)).all()]}
    raise common.NotFound("Project", slug)


@router.get("/settings")
def settings_view(db: Session = Depends(get_db)):
    from ..collectors.redfish import RedfishClient
    from ..livelab import manager
    cfg = get_settings()
    rf = RedfishClient.from_settings()
    counts = {}
    for model in (m.Incident, m.EvidenceItem, m.AcceptanceRun, m.MetricObservation):
        rows = db.execute(select(model.source_type, func.count()).group_by(model.source_type)).all()
        counts[model.__tablename__] = {k: v for k, v in rows}
    enabled = bool(common.get_setting(db, "livelab_enabled", False))
    return {
        "mode": "public_preview" if cfg.public_preview else ("hosted_demo" if cfg.serverless else "local"),
        "bind_host": cfg.bind_host,
        "simulation": {"probe_interval_s": cfg.sim_probe_interval_seconds, "deterministic": True},
        "integrations": {
            "redfish": rf.describe() | {"status": "configured" if rf.mode == "live" else "fixture mode (no endpoint configured)"},
            "netbox": {"status": "configured" if (cfg.netbox_url and cfg.netbox_token) else "unconfigured",
                       "note": "Read-only JSON import of a NetBox device export is available without credentials."},
            "alertmanager": {"status": "enabled" if cfg.alertmanager_webhook_enabled else "disabled",
                             "endpoint": "/api/integrations/alertmanager",
                             "auth": "bearer token required" if cfg.alertmanager_webhook_token else "no token configured"},
            "jira": {"status": "configured" if (cfg.jira_url and cfg.jira_token) else "unconfigured",
                     "note": "File-based export is always available; no ticket is created automatically."},
            "notifications": {"status": "disabled" if not cfg.notifications_enabled else "enabled (no channels implemented)"},
        },
        "livelab": {"enabled": enabled, "status": manager.status() if enabled else None,
                    "state": common.get_setting(db, "livelab_state", {})},
        "source_counts": counts,
    }


@router.post("/settings/livelab", dependencies=[Depends(require_mutations)])
def livelab_toggle(body: s.LiveLabToggleIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    from ..livelab import manager
    if get_settings().serverless:
        raise common.DomainError("unavailable_hosted", "The live-lab target runs a local process and is not available in the hosted demo. Run RackOps Lab locally to use it.", 409)
    common.set_setting(db, "livelab_enabled", body.enabled)
    if body.enabled:
        if not db.scalar(select(m.Device).where(m.Device.display_id == "livelab-target")):
            db.add(m.Device(display_id="livelab-target", hostname="localhost", role="server", manufacturer="This machine",
                            model="Local process (lab target)", u_height=1, mgmt_address="127.0.0.1", health="unknown",
                            health_source="LOCAL_LAB", origin="local_lab", notes="Lab-owned HTTP process on 127.0.0.1. Not racked."))
        manager.start_target()
    common.audit(db, actor=who, action="livelab.toggle", entity_type="setting", entity_id=0, entity_display="livelab",
                 summary=f"Live lab {'enabled' if body.enabled else 'disabled'}", origin="local_lab")
    db.commit()
    return settings_view(db)


@router.post("/livelab/{action}", dependencies=[Depends(require_mutations)])
def livelab_action(action: str, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    from ..livelab import manager
    if not common.get_setting(db, "livelab_enabled", False):
        raise common.DomainError("livelab_disabled", "Enable the live lab in Settings first.")
    if action == "stop":
        try:
            st = manager.stop_target()
        except RuntimeError as e:
            raise common.DomainError("unsafe_stop", str(e))
        state = dict(common.get_setting(db, "livelab_state", {}) or {})
        state["operator_stop_at"] = common.dt(utcnow())
        common.set_setting(db, "livelab_state", state)
        common.audit(db, actor=who, action="livelab.stop", entity_type="setting", entity_id=0, entity_display="livelab",
                     summary="Operator stopped the live-lab target (real outage exercise)", origin="local_lab")
    elif action == "start":
        st = manager.start_target()
    else:
        raise common.NotFound("Live-lab action", action)
    db.commit()
    return st


# --------------------------------------------------------------------------- integrations


@router.post("/integrations/alertmanager")
def alertmanager(body: s.AlertmanagerWebhook, db: Session = Depends(get_write_db), authorization: Optional[str] = Header(None)):
    """Receives Alertmanager webhooks (disabled by default). Alerts become LOCAL_LAB incidents."""
    cfg = get_settings()
    if not cfg.alertmanager_webhook_enabled:
        raise common.DomainError("integration_disabled", "Alertmanager webhook receiver is disabled (RACKOPS_ALERTMANAGER_WEBHOOK_ENABLED).", 403)
    if cfg.alertmanager_webhook_token and authorization != f"Bearer {cfg.alertmanager_webhook_token}":
        raise common.DomainError("unauthorized", "Invalid webhook token.", 401)
    return _ingest_alerts(db, body, source_type="LOCAL_LAB", origin="local_lab")


@router.post("/integrations/alertmanager/sample", dependencies=[Depends(require_mutations)])
def alertmanager_sample(db: Session = Depends(get_write_db)):
    """Imports a bundled Alertmanager sample payload, labeled IMPORTED_SAMPLE."""
    from pathlib import Path
    data = json.loads((Path(__file__).resolve().parent.parent / "fixtures" / "alertmanager_sample.json").read_text())
    return _ingest_alerts(db, s.AlertmanagerWebhook(**data), source_type="IMPORTED_SAMPLE", origin="imported")


def _ingest_alerts(db: Session, body: s.AlertmanagerWebhook, source_type: str, origin: str):
    from datetime import datetime
    from ..services import incidents as inc_svc
    created, updated = [], []
    for a in body.alerts:
        fp = a.fingerprint or f"{a.labels.get('alertname')}:{a.labels.get('instance')}"
        sid = f"alertmanager:{fp}"
        existing = db.scalar(select(m.Incident).where(m.Incident.source_id == sid, m.Incident.status != "resolved"))
        if existing:
            inc_svc._event(db, existing, "note", f"Alertmanager reports status={a.status}", detail={"alert_status": a.status})
            updated.append(existing.display_id)
            continue
        if a.status != "firing":
            continue
        try:
            starts = datetime.fromisoformat(a.startsAt.replace("Z", "+00:00")) if a.startsAt else None
        except ValueError:
            starts = None
        sev = a.labels.get("severity", "major")
        sev = sev if sev in ("critical", "major", "minor") else "major"
        dev = db.scalar(select(m.Device).where(m.Device.display_id == a.labels.get("instance", "").split(":")[0]))
        inc = m.Incident(display_id=common.next_display_id(db, "INC"), title=a.annotations.get("summary") or a.labels.get("alertname", "Alert"),
                         symptom=a.annotations.get("description", ""), severity=sev, status="detected", device_id=dev.id if dev else None,
                         detection_rule=f"Alertmanager rule {a.labels.get('alertname')}", source_type=source_type, source_id=sid,
                         fault_onset_at=None, detected_at=starts or utcnow(), origin=origin)
        db.add(inc)
        db.flush()
        inc_svc._event(db, inc, "fault_onset", "Fault onset unknown. Alert startsAt is when the rule fired, not when the fault began.",
                       at=inc.detected_at, detail={"known": False})
        inc_svc._event(db, inc, "detected", f"Received from Alertmanager ({source_type})", at=inc.detected_at, detail={"labels": a.labels})
        common.audit(db, actor="alertmanager", action="incident.detected", entity_type="incident", entity_id=inc.id,
                     entity_display=inc.display_id, summary=f"{inc.display_id} created from Alertmanager ({source_type})", origin=origin)
        created.append(inc.display_id)
    db.commit()
    return {"created": created, "updated": updated, "source_type": source_type}


@router.post("/integrations/netbox/import", dependencies=[Depends(require_mutations)])
async def netbox_import(file: UploadFile = File(...), db: Session = Depends(get_write_db), who: str = Depends(actor)):
    """Read-only import of a NetBox /api/dcim/devices/ export. Devices are labeled origin=imported and are not racked."""
    raw = await file.read(get_settings().max_upload_bytes + 1)
    if len(raw) > get_settings().max_upload_bytes:
        raise common.DomainError("upload_too_large", "Upload too large.", 413)
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise common.DomainError("invalid_json", f"Not valid JSON: {e}", 422)
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        raise common.DomainError("invalid_netbox", "Expected a NetBox list response with a 'results' array.", 422)
    created, skipped = [], []
    for r in results[:200]:
        name = str(r.get("name") or "")[:60]
        if not name:
            continue
        disp = f"nb-{name}"
        if db.scalar(select(m.Device).where(m.Device.display_id == disp)):
            skipped.append(disp)
            continue
        dtype = (r.get("device_type") or {})
        db.add(m.Device(display_id=disp, hostname=name, role="server", manufacturer=str((dtype.get("manufacturer") or {}).get("name", "Unknown"))[:80],
                        model=str(dtype.get("model", "Unknown"))[:80], u_height=0, health="unknown", health_source="IMPORTED_SAMPLE",
                        origin="imported", notes=f"Imported from NetBox export (id {r.get('id')}). Not placed in a modeled rack."))
        created.append(disp)
    common.audit(db, actor=who, action="netbox.import", entity_type="site", entity_id=0, entity_display="netbox",
                 summary=f"Imported {len(created)} device(s) from NetBox export", origin="imported")
    db.commit()
    return {"created": created, "skipped": skipped}


# --------------------------------------------------------------------------- server-sent events


@router.get("/events")
async def events(request: Request, last_event_id: Optional[int] = Query(None), last_event_header: Optional[str] = Header(None, alias="Last-Event-ID")):
    """SSE stream of persisted events. Reconnecting clients resume from Last-Event-ID."""
    start = last_event_id
    if last_event_header and last_event_header.isdigit():
        start = int(last_event_header)

    def latest_id() -> int:
        with SessionLocal() as db:
            return db.scalar(select(func.max(m.StreamEvent.id))) or 0

    def fetch(after: int) -> list[tuple[int, str, dict]]:
        with SessionLocal() as db:
            rows = db.scalars(select(m.StreamEvent).where(m.StreamEvent.id > after).order_by(m.StreamEvent.id).limit(200)).all()
            return [(r.id, r.topic, r.payload) for r in rows]

    serverless = get_settings().serverless

    async def gen():
        import time
        from ..runner import lazy_tick
        cursor = start if start is not None else await asyncio.to_thread(latest_id)
        yield f"retry: 2000\nid: {cursor}\nevent: hello\ndata: {json.dumps({'resume_from': cursor})}\n\n"
        idle = 0.0
        opened = time.monotonic()
        while True:
            if await request.is_disconnected():
                break
            if serverless:
                if time.monotonic() - opened > 50:  # stay under the function duration limit; EventSource reconnects
                    break
                await asyncio.to_thread(lazy_tick)
            rows = await asyncio.to_thread(fetch, cursor)
            for eid, topic, payload in rows:
                cursor = eid
                yield f"id: {eid}\nevent: {topic}\ndata: {json.dumps(payload)}\n\n"
            if rows:
                idle = 0.0
            else:
                idle += 0.5
                if idle >= 15:
                    idle = 0.0
                    yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def prune_stream_events() -> None:
    with SessionLocal() as db:
        maxid = db.scalar(select(func.max(m.StreamEvent.id))) or 0
        db.execute(delete(m.StreamEvent).where(m.StreamEvent.id < maxid - 20000))
        db.commit()


# --------------------------------------------------------------------------- runbooks & probe series

PRIMARY_HEALTH = {
    "svc-stopped": ("service_up", lambda v: v == 1),
    "fs-full": ("fs_used_pct", lambda v: v is not None and v < 95),
    "cpu-contention": ("cpu_util_pct", lambda v: v is not None and v <= 90),
    "nic-down": ("iface_oper_up", lambda v: v == 1),
    "psu-failure": ("psu_health_ok", lambda v: v == 1),
}


@router.get("/runbooks")
def runbooks(db: Session = Depends(get_db)):
    return [{"slug": r.slug, "title": r.title, "project": r.project, "symptom": r.symptom, "scenario_keys": r.scenario_keys,
             "sections": r.sections, "version": r.version} for r in db.scalars(select(m.Runbook).order_by(m.Runbook.id)).all()]


@router.get("/simulation/runs/{ident}/series")
def sim_series(ident: str, db: Session = Depends(get_db)):
    run = _sim_run(db, ident)
    spec = PRIMARY_HEALTH.get(run.scenario_key)
    if not spec:
        return {"points": [], "metric": None}
    metric, ok = spec
    rows = db.scalars(select(m.MetricObservation).where(m.MetricObservation.simulation_run_id == run.id, m.MetricObservation.metric == metric)
                      .order_by(m.MetricObservation.observed_at).limit(400)).all()
    return {"metric": metric, "source_type": "SIMULATED",
            "points": [{"at": common.dt(r.observed_at), "v": r.value, "ok": ok(r.value)} for r in rows]}
