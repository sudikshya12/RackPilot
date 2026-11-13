import json

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from .. import serializers as ser
from ..acceptance.checks import REGISTRY
from ..config import BASE_DIR, get_settings
from ..db import get_db, get_write_db
from ..deps import IdemKey, actor, require_mutations
from ..services import acceptance as svc
from ..services import common

router = APIRouter(prefix="/api/acceptance", tags=["acceptance"])
_env = Environment(loader=FileSystemLoader(str(BASE_DIR / "app" / "templates")), autoescape=select_autoescape(["html"]))


@router.get("/profiles")
def profiles(db: Session = Depends(get_db)):
    out = []
    for p in db.scalars(select(m.AcceptanceProfile)).all():
        out.append({"key": p.key, "name": p.name, "version": p.version, "description": p.description,
                    "checks": [{**c, "name": REGISTRY[c["check_key"]].name if c["check_key"] in REGISTRY else c["check_key"],
                                "description": REGISTRY[c["check_key"]].description if c["check_key"] in REGISTRY else "",
                                "version": REGISTRY[c["check_key"]].version if c["check_key"] in REGISTRY else "?"}
                               for c in p.checks]})
    return out


@router.get("/collectors")
def collectors():
    from ..collectors.redfish import RedfishClient
    rf = RedfishClient.from_settings()
    return [{"key": k, **v, "available": (k != "redfish_live" or rf.mode == "live"),
             "note": "Not configured (RACKOPS_REDFISH_URL)" if (k == "redfish_live" and rf.mode != "live") else ""}
            for k, v in svc.COLLECTORS.items()]


@router.get("/intakes")
def intakes(db: Session = Depends(get_db)):
    rows = db.scalars(select(m.IntakeRecord).order_by(m.IntakeRecord.id)).all()
    return [ser.intake(db, r) for r in rows]


@router.post("/intakes", dependencies=[Depends(require_mutations)], status_code=201)
def create_intake(body: s.IntakeIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    data = body.model_dump()
    data["expected"] = body.expected.model_dump()
    if body.use_simulator_model and body.source_type == "SIMULATED":
        from ..seed import _hw_srv07
        hw = _hw_srv07()
        hw["identity"]["serial_number"] = body.serial_number
        hw["disk_health"] = [{"name": "nvme0n1", "smart_passed": True, "media_errors": 0, "percentage_used": 0}]
        data["simulated_hardware"] = hw
    rec = svc.create_intake(db, data, who)
    db.commit()
    return ser.intake(db, rec)


def _intake(db, ident) -> m.IntakeRecord:
    return common.get_or_404(db, m.IntakeRecord, ident, "Intake")


def _run(db, ident) -> m.AcceptanceRun:
    return common.get_or_404(db, m.AcceptanceRun, ident, "Acceptance run")


@router.get("/intakes/{ident}")
def get_intake(ident: str, db: Session = Depends(get_db)):
    return ser.intake(db, _intake(db, ident))


@router.post("/intakes/{ident}/runs", dependencies=[Depends(require_mutations)], status_code=201)
def start_run(ident: str, body: s.RunStartIn, db: Session = Depends(get_write_db), who: str = Depends(actor),
              idempotency_key: str | None = IdemKey):
    endpoint = f"acceptance.start:{ident}"
    hit = common.idempotent_lookup(db, idempotency_key, endpoint, body.model_dump())
    if hit:
        return JSONResponse(hit[1], status_code=hit[0])
    run = svc.start_run(db, _intake(db, ident), body.collector, who)
    resp = ser.run_summary(run)
    common.idempotent_store(db, idempotency_key, endpoint, body.model_dump(), 201, resp)
    db.commit()
    return resp


@router.post("/intakes/{ident}/corrections", dependencies=[Depends(require_mutations)])
def correction(ident: str, body: s.CorrectionIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    rec = _intake(db, ident)
    svc.apply_correction(db, rec, body.key, who)
    db.commit()
    return ser.intake(db, rec)


@router.post("/intakes/{ident}/upload", dependencies=[Depends(require_mutations)])
async def upload(ident: str, request: Request, file: UploadFile = File(...), source_type: str = Form(...),
                 db: Session = Depends(get_db), who: str = Depends(actor)):
    if source_type not in ("LOCAL_LAB", "IMPORTED_SAMPLE"):
        raise common.DomainError("invalid_source", "source_type must be LOCAL_LAB or IMPORTED_SAMPLE", 422)
    raw = await file.read(get_settings().max_upload_bytes + 1)
    if len(raw) > get_settings().max_upload_bytes:
        raise common.DomainError("upload_too_large", f"Upload exceeds {get_settings().max_upload_bytes // 1024} KiB.", 413)
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise common.DomainError("invalid_json", f"File is not valid JSON: {e}", 422)
    clean = svc.sanitize_upload(data)
    rec = _intake(db, ident)
    rec.uploaded_observations, rec.uploaded_source_type = clean, source_type
    common.audit(db, actor=who, action="intake.upload", entity_type="intake", entity_id=rec.id, entity_display=rec.display_id,
                 summary=f"Uploaded collector output ({source_type}, {len(raw)} bytes)", origin="imported" if source_type == "IMPORTED_SAMPLE" else "local_lab")
    db.commit()
    return ser.intake(db, rec)


@router.post("/intakes/{ident}/handoff", dependencies=[Depends(require_mutations)])
def handoff(ident: str, body: s.HandoffIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    rec = _intake(db, ident)
    svc.handoff(db, rec, body.checklist, who)
    db.commit()
    return ser.intake(db, rec)


@router.get("/runs")
def runs(db: Session = Depends(get_db), limit: int = 50):
    rows = db.scalars(select(m.AcceptanceRun).order_by(m.AcceptanceRun.id.desc()).limit(limit)).all()
    return [ser.run_summary(r) for r in rows]


@router.get("/runs/{ident}")
def get_run(ident: str, db: Session = Depends(get_db)):
    return ser.run_detail(db, _run(db, ident))


@router.post("/runs/{ident}/manual-review", dependencies=[Depends(require_mutations)])
def manual_review(ident: str, body: s.ManualReviewIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    run = _run(db, ident)
    svc.record_manual_review(db, run, body.check_key, body.decision, body.note, who)
    db.commit()
    return ser.run_detail(db, run)


@router.get("/compare")
def compare(a: str, b: str, db: Session = Depends(get_db)):
    return svc.compare(_run(db, a), _run(db, b))


@router.get("/runs/{ident}/report.json")
def report_json(ident: str, db: Session = Depends(get_db)):
    run = _run(db, ident)
    payload = ser.run_detail(db, run) | {"report_generated_from": "persisted acceptance run record",
                                         "handoff_checklist": svc.HANDOFF_CHECKLIST}
    return JSONResponse(payload, headers={"Content-Disposition": f'attachment; filename="{run.display_id}.json"'})


@router.get("/runs/{ident}/report.html", response_class=HTMLResponse)
def report_html(ident: str, db: Session = Depends(get_db)):
    run = _run(db, ident)
    detail = ser.run_detail(db, run)
    html = _env.get_template("acceptance_report.html").render(run=detail, checklist=svc.HANDOFF_CHECKLIST,
                                                              intake_status=run.intake.status)
    return HTMLResponse(html)
