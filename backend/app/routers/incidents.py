from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from .. import serializers as ser
from ..db import get_db, get_write_db
from ..deps import actor, require_mutations
from ..services import common, incidents as svc, simulation
from ..services.scenarios import SCENARIOS

router = APIRouter(prefix="/api", tags=["incidents"])


@router.get("/scenarios")
def list_scenarios(db: Session = Depends(get_db)):
    out = []
    for sc in SCENARIOS.values():
        run = simulation.active_run_for(db, sc.key)
        out.append({"key": sc.key, "title": sc.title, "project": sc.project, "device": sc.device, "severity": sc.severity,
                    "symptom": sc.symptom, "detection_rule": sc.detection_rule, "onset_known": sc.onset_known,
                    "onset_note": sc.onset_note, "runbook": sc.runbook,
                    "active_run": {"display_id": run.display_id, "status": run.status, "incident_id": run.incident_id,
                                   "demo_key": run.demo_key} if run else None})
    return out


@router.post("/scenarios/{key}/start", dependencies=[Depends(require_mutations)], status_code=201)
def start_scenario(key: str, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    run = simulation.start(db, key, actor=who)
    db.commit()
    return {"simulation_run": run.display_id, "id": run.id, "status": run.status}


@router.get("/incidents", response_model=s.Page)
def list_incidents(
    db: Session = Depends(get_db),
    severity: Optional[str] = None, status: Optional[str] = None, device: Optional[str] = None,
    source: Optional[str] = None, scenario: Optional[str] = None, open_only: bool = False,
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
):
    q = select(m.Incident)
    if severity:
        q = q.where(m.Incident.severity.in_(severity.split(",")))
    if status:
        q = q.where(m.Incident.status.in_(status.split(",")))
    if open_only:
        q = q.where(m.Incident.status != "resolved")
    if source:
        q = q.where(m.Incident.source_type.in_(source.split(",")))
    if scenario:
        q = q.where(m.Incident.scenario_key == scenario)
    if device:
        d = db.scalar(select(m.Device).where(m.Device.display_id == device))
        q = q.where(m.Incident.device_id == (d.id if d else -1))
    rows = sorted(db.scalars(q).all(), key=svc.queue_sort_key)
    items = [ser.incident_summary(db, i) for i in rows[offset: offset + limit]]
    return {"items": items, "total": len(rows), "limit": limit, "offset": offset}


@router.get("/incidents/metrics")
def incident_metrics(db: Session = Depends(get_db)):
    return svc.aggregate_metrics(db)


def _inc(db, ident) -> m.Incident:
    return common.get_or_404(db, m.Incident, ident, "Incident")


@router.get("/incidents/{ident}")
def get_incident(ident: str, db: Session = Depends(get_db)):
    return ser.incident_detail(db, _inc(db, ident))


@router.get("/incidents/{ident}/metrics-series")
def incident_series(ident: str, db: Session = Depends(get_db)):
    inc = _inc(db, ident)
    q = select(m.MetricObservation).where(m.MetricObservation.source_type == inc.source_type)
    if inc.simulation_run_id:
        q = q.where(m.MetricObservation.simulation_run_id == inc.simulation_run_id)
    elif inc.device_id:
        q = q.where(m.MetricObservation.device_id == inc.device_id, m.MetricObservation.observed_at >= inc.detected_at.replace(microsecond=0)
                    - __import__("datetime").timedelta(minutes=5))
    rows = db.scalars(q.order_by(m.MetricObservation.observed_at).limit(2000)).all()
    return {"source_type": inc.source_type, "series": [
        {"metric": r.metric, "value": r.value, "unit": r.unit, "labels": r.labels, "observed_at": common.dt(r.observed_at),
         "source_id": r.source_id} for r in rows]}


@router.post("/incidents/{ident}/transition", dependencies=[Depends(require_mutations)])
def transition(ident: str, body: s.TransitionIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    inc = _inc(db, ident)
    if body.action == "acknowledge":
        svc.acknowledge(db, inc, body.actor or who)
    else:
        svc.start_investigation(db, inc, body.actor or who)
    db.commit()
    return ser.incident_detail(db, inc)


@router.post("/incidents/{ident}/assign", dependencies=[Depends(require_mutations)])
def assign(ident: str, body: s.AssignIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    inc = _inc(db, ident)
    svc.assign(db, inc, body.operator, who)
    db.commit()
    return ser.incident_detail(db, inc)


@router.post("/incidents/{ident}/notes", dependencies=[Depends(require_mutations)])
def note(ident: str, body: s.NoteIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    inc = _inc(db, ident)
    svc.add_note(db, inc, body.text, who)
    db.commit()
    return ser.incident_detail(db, inc)


@router.post("/incidents/{ident}/evidence", dependencies=[Depends(require_mutations)], status_code=201)
def collect(ident: str, body: s.EvidenceCollectIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    inc = _inc(db, ident)
    ev = svc.collect_evidence(db, inc, body.collector, who)
    db.commit()
    return ser.evidence(ev)


@router.post("/incidents/{ident}/hypotheses/{key}", dependencies=[Depends(require_mutations)])
def hypothesis(ident: str, key: str, body: s.HypothesisIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    inc = _inc(db, ident)
    svc.set_hypothesis(db, inc, key, body.status, body.note, who)
    db.commit()
    return ser.incident_detail(db, inc)


@router.post("/incidents/{ident}/repair", dependencies=[Depends(require_mutations)])
def repair(ident: str, body: s.RepairIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    inc = _inc(db, ident)
    svc.apply_repair_action(db, inc, body.action_key, who)
    db.commit()
    return ser.incident_detail(db, inc)


@router.post("/incidents/{ident}/verify", dependencies=[Depends(require_mutations)])
def verify(ident: str, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    inc = _inc(db, ident)
    svc.verify(db, inc, who)
    db.commit()
    return ser.incident_detail(db, inc)


@router.post("/incidents/{ident}/resolve", dependencies=[Depends(require_mutations)])
def resolve(ident: str, body: s.ResolveIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    inc = _inc(db, ident)
    svc.resolve(db, inc, who, body.root_cause)
    db.commit()
    return ser.incident_detail(db, inc)


@router.post("/incidents/{ident}/reopen", dependencies=[Depends(require_mutations)])
def reopen(ident: str, body: s.ReopenIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    inc = _inc(db, ident)
    svc.reopen(db, inc, body.reason, who)
    db.commit()
    return ser.incident_detail(db, inc)


@router.get("/incidents/{ident}/summary")
def summary(ident: str, db: Session = Depends(get_db)):
    return svc.summary(db, _inc(db, ident))


@router.get("/incidents/{ident}/summary.md", response_class=PlainTextResponse)
def summary_md(ident: str, db: Session = Depends(get_db)):
    inc = _inc(db, ident)
    return PlainTextResponse(svc.summary(db, inc)["markdown"], headers={"Content-Disposition": f'attachment; filename="{inc.display_id}-summary.md"'})


@router.get("/incidents/{ident}/export/jira")
def jira_export(ident: str, db: Session = Depends(get_db)):
    """File-based Jira export (no API call). Produces a payload for POST /rest/api/2/issue."""
    inc = _inc(db, ident)
    sm = svc.summary(db, inc)
    payload = {"fields": {"project": {"key": "<PROJECT_KEY>"}, "issuetype": {"name": "Incident"},
                          "summary": f"[{inc.source_type}] {inc.display_id} {inc.title}",
                          "description": sm["markdown"], "labels": ["rackops-lab", inc.source_type.lower()]}}
    return JSONResponse(payload, headers={"Content-Disposition": f'attachment; filename="{inc.display_id}-jira.json"'})
