from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from .. import serializers as ser
from ..db import get_db, get_write_db
from ..deps import IdemKey, actor, require_mutations
from ..services import common, inventory as inv, topology as topo

router = APIRouter(prefix="/api", tags=["infrastructure"])


# --------------------------------------------------------------------------- topology


@router.get("/sites")
def sites(db: Session = Depends(get_db)):
    return [{"id": x.id, "display_id": x.display_id, "name": x.name, "description": x.description,
             "racks": [r.display_id for r in x.racks], "basis": "Modeled lab topology"} for x in db.scalars(select(m.Site)).all()]


def _device_card(db: Session, d: m.Device) -> dict:
    open_incs = db.scalars(select(m.Incident).where(m.Incident.device_id == d.id, m.Incident.status != "resolved")).all()
    intake = db.scalar(select(m.IntakeRecord).where(m.IntakeRecord.device_id == d.id)) if d.role == "server" else None
    return ser.device_ref(d) | {
        "hostname": d.hostname, "u_height": d.u_height, "face": d.face, "manufacturer": d.manufacturer,
        "health_source": d.health_source, "health_updated_at": common.dt(d.health_updated_at),
        "asset_id": d.asset_id, "asset": d.asset.display_id if d.asset else None, "serial": d.asset.serial_number if d.asset else None,
        "open_incidents": [{"id": i.id, "display_id": i.display_id, "severity": i.severity, "status": i.status, "source_type": i.source_type}
                           for i in open_incs],
        "acceptance": intake.status if intake else None, "power_findings": topo.power_analysis(db, d)["findings"] if d.role in ("server", "switch") else [],
        "origin": d.origin,
    }


@router.get("/racks")
def racks(db: Session = Depends(get_db)):
    out = []
    for r in db.scalars(select(m.Rack).order_by(m.Rack.display_id)).all():
        el = topo.elevation(db, r)
        reserved = db.scalars(select(m.IntakeRecord).where(m.IntakeRecord.intended_rack_id == r.id,
                                                           m.IntakeRecord.status != "handed_off")).all()
        out.append({"id": r.id, "display_id": r.display_id, "name": r.name, "row": r.row, "u_height": r.u_height,
                    "site": r.site.display_id, "free_units": el["free_count"], "basis": "Modeled lab topology",
                    "devices": [_device_card(db, d) for d in el["devices"]],
                    "planned": [{"intake_id": x.id, "intake": x.display_id, "hostname": x.hostname, "position_u": x.intended_position_u,
                                 "u_height": 1, "status": x.status} for x in reserved if x.intended_position_u]})
    return out


@router.get("/devices")
def devices(db: Session = Depends(get_db), role: Optional[str] = None, health: Optional[str] = None):
    q = select(m.Device).order_by(m.Device.display_id)
    if role:
        q = q.where(m.Device.role.in_(role.split(",")))
    if health:
        q = q.where(m.Device.health.in_(health.split(",")))
    return [_device_card(db, d) for d in db.scalars(q).all()]


@router.get("/devices/{ident}")
def device(ident: str, db: Session = Depends(get_db)):
    d = common.get_or_404(db, m.Device, ident, "Device")
    cables = db.scalars(select(m.CableConnection).where(or_(
        m.CableConnection.a_interface_id.in_([i.id for i in d.interfaces]),
        m.CableConnection.b_interface_id.in_([i.id for i in d.interfaces])))).all()
    incs = db.scalars(select(m.Incident).where(m.Incident.device_id == d.id).order_by(m.Incident.detected_at.desc())).all()
    intakes = db.scalars(select(m.IntakeRecord).where(or_(m.IntakeRecord.device_id == d.id,
                                                          m.IntakeRecord.asset_id == d.asset_id))).all() if d.asset_id else []
    components = db.scalars(select(m.Asset).where(m.Asset.installed_in_device_id == d.id, m.Asset.id != (d.asset_id or -1))).all()
    # Complete trail: the device, its components (current and returned), and every incident,
    # reservation and return record linked to it.
    asset_ids = {a.id for a in components} | ({d.asset_id} if d.asset_id else set())
    returns = db.scalars(select(m.ReturnRecord).where(m.ReturnRecord.original_device_id == d.id)).all()
    asset_ids |= {r.failed_asset_id for r in returns} | {r.replacement_asset_id for r in returns if r.replacement_asset_id}
    res_ids = [r.id for r in db.scalars(select(m.Reservation).where(m.Reservation.device_id == d.id)).all()]
    stock_ids = [r.stock_id for r in db.scalars(select(m.Reservation).where(m.Reservation.device_id == d.id)).all()]
    inc_ids = [i.id for i in incs]
    conds = [(m.AuditEvent.entity_type == "device") & (m.AuditEvent.entity_id == d.id), m.AuditEvent.entity_display == d.display_id]
    if asset_ids:
        conds.append((m.AuditEvent.entity_type == "asset") & (m.AuditEvent.entity_id.in_(asset_ids)))
    if res_ids:
        conds.append((m.AuditEvent.entity_type == "reservation") & (m.AuditEvent.entity_id.in_(res_ids)))
    if returns:
        conds.append((m.AuditEvent.entity_type == "return") & (m.AuditEvent.entity_id.in_([r.id for r in returns])))
    if inc_ids:
        conds.append((m.AuditEvent.entity_type == "incident") & (m.AuditEvent.entity_id.in_(inc_ids)))
    audit = db.scalars(select(m.AuditEvent).where(or_(*conds)).order_by(m.AuditEvent.occurred_at.desc(), m.AuditEvent.id.desc()).limit(200)).all()
    return _device_card(db, d) | {
        "mgmt_address": d.mgmt_address, "notes": d.notes,
        "interfaces": [{"id": i.id, "name": i.name, "kind": i.kind, "connector": i.connector_type, "speed_capability_mbps": i.speed_capability_mbps,
                        "mac": i.mac_address, "description": i.description, "pass_through_id": i.pass_through_id} for i in d.interfaces],
        "cables": [ser.cable(c) for c in cables],
        "power": topo.power_analysis(db, d),
        "incidents": [ser.incident_summary(db, i) for i in incs],
        "acceptance": [ser.intake(db, x) for x in intakes],
        "asset_detail": ser.asset(d.asset) if d.asset else None,
        "components": [ser.asset(a) for a in components],
        "audit": [ser.audit_event(a) for a in audit],
    }


@router.post("/devices/{ident}/place", dependencies=[Depends(require_mutations)])
def place(ident: str, body: s.PlaceIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    d = common.get_or_404(db, m.Device, ident, "Device")
    topo.place_device(db, d, body.rack, body.position_u, who)
    db.commit()
    return _device_card(db, d)


@router.get("/cables")
def cables(db: Session = Depends(get_db)):
    return [ser.cable(c) for c in db.scalars(select(m.CableConnection).order_by(m.CableConnection.label)).all()]


@router.get("/cables/audit")
def cable_audit(db: Session = Depends(get_db)):
    return {"issues": topo.cable_audit(db), "basis": "Modeled lab topology"}


@router.post("/cables", dependencies=[Depends(require_mutations)], status_code=201)
def create_cable(body: s.CableIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    c, warnings = topo.create_cable(db, body.model_dump(), who)
    db.commit()
    return ser.cable(c) | {"warnings": warnings}


@router.post("/cables/{cid}/label", dependencies=[Depends(require_mutations)])
def label(cid: int, body: s.CableLabelIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    c = db.get(m.CableConnection, cid)
    if c is None:
        raise common.NotFound("Cable", cid)
    topo.label_cable(db, c, body.label, who)
    db.commit()
    return ser.cable(c)


@router.get("/interfaces/{iid}/trace")
def trace(iid: int, db: Session = Depends(get_db)):
    return topo.trace(db, iid)


@router.get("/power")
def power(db: Session = Depends(get_db)):
    return topo.power_overview(db)


# --------------------------------------------------------------------------- assets


@router.get("/assets")
def assets(db: Session = Depends(get_db), status: Optional[str] = None, asset_type: Optional[str] = None, q: Optional[str] = None):
    query = select(m.Asset).order_by(m.Asset.display_id)
    if status:
        query = query.where(m.Asset.status.in_(status.split(",")))
    if asset_type:
        query = query.where(m.Asset.asset_type.in_(asset_type.split(",")))
    if q:
        like = f"%{q}%"
        query = query.where(or_(m.Asset.display_id.ilike(like), m.Asset.serial_number.ilike(like), m.Asset.model.ilike(like)))
    return [ser.asset(a) for a in db.scalars(query).all()]


@router.get("/assets/{ident}")
def asset(ident: str, db: Session = Depends(get_db)):
    a = common.get_or_404(db, m.Asset, ident, "Asset")
    audit = db.scalars(select(m.AuditEvent).where(m.AuditEvent.entity_type == "asset", m.AuditEvent.entity_id == a.id)
                       .order_by(m.AuditEvent.occurred_at)).all()
    dev = db.scalar(select(m.Device).where(m.Device.asset_id == a.id))
    rr = db.scalar(select(m.ReturnRecord).where(m.ReturnRecord.failed_asset_id == a.id))
    return ser.asset(a) | {"audit": [ser.audit_event(x) for x in audit], "device_id": dev.id if dev else None,
                           "device": dev.display_id if dev else None, "return_record": ser.return_record(rr) if rr else None,
                           "allowed_transitions": sorted(inv.LIFECYCLE.get(a.status, set())),
                           "required_info": {k: v[1] for k, v in inv.REQUIRED_INFO.items()}}


@router.post("/assets/{ident}/transition", dependencies=[Depends(require_mutations)])
def asset_transition(ident: str, body: s.AssetTransitionIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    a = common.get_or_404(db, m.Asset, ident, "Asset")
    inv.transition_asset(db, a, body.to, who, location=body.location, device_id=body.device_id, note=body.note,
                         simulation_run_id=a.simulation_run_id)
    db.commit()
    return ser.asset(a)


# --------------------------------------------------------------------------- spares


@router.get("/spares")
def spares(db: Session = Depends(get_db), device_id: Optional[int] = None):
    if device_id:
        d = db.get(m.Device, device_id)
        if d is None:
            raise common.NotFound("Device", device_id)
        return {"device": ser.device_ref(d), "stock": inv.compatible_stock(db, d)}
    return {"device": None, "stock": [inv.stock_view(db, x) for x in db.scalars(select(m.SpareStock).order_by(m.SpareStock.display_id)).all()]}


@router.post("/spares/{sid}/receive", dependencies=[Depends(require_mutations)])
def receive(sid: int, body: s.ReceiveIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    st = db.get(m.SpareStock, sid)
    if st is None:
        raise common.NotFound("Stock", sid)
    inv.receive(db, st, body.quantity, who, body.note)
    db.commit()
    return inv.stock_view(db, st)


@router.get("/reservations")
def reservations(db: Session = Depends(get_db), status: Optional[str] = None, incident_id: Optional[int] = None):
    q = select(m.Reservation).order_by(m.Reservation.id.desc())
    if status:
        q = q.where(m.Reservation.status.in_(status.split(",")))
    if incident_id:
        q = q.where(m.Reservation.incident_id == incident_id)
    return [ser.reservation(r) for r in db.scalars(q).all()]


@router.post("/reservations", dependencies=[Depends(require_mutations)], status_code=201)
def reserve(body: s.ReserveIn, db: Session = Depends(get_write_db), who: str = Depends(actor), idempotency_key: Optional[str] = IdemKey):
    endpoint = "reservations.create"
    hit = common.idempotent_lookup(db, idempotency_key, endpoint, body.model_dump())
    if hit:
        return JSONResponse(hit[1], status_code=hit[0])
    st = db.get(m.SpareStock, body.stock_id)
    if st is None:
        raise common.NotFound("Stock", body.stock_id)
    dev = db.get(m.Device, body.device_id) if body.device_id else None
    inc = db.get(m.Incident, body.incident_id) if body.incident_id else None
    r = inv.reserve(db, stock=st, quantity=body.quantity, device=dev, incident=inc, reason=body.reason, actor=who,
                    compatibility_exception=body.compatibility_exception, exception_reviewed_by=body.exception_reviewed_by,
                    exception_note=body.exception_note)
    resp = ser.reservation(r)
    common.idempotent_store(db, idempotency_key, endpoint, body.model_dump(), 201, resp)
    db.commit()
    return resp


@router.post("/reservations/{rid}/release", dependencies=[Depends(require_mutations)])
def release(rid: int, body: s.ReleaseIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    r = db.get(m.Reservation, rid)
    if r is None:
        raise common.NotFound("Reservation", rid)
    inv.release(db, r, who, body.note)
    db.commit()
    return ser.reservation(r)


@router.post("/reservations/{rid}/consume", dependencies=[Depends(require_mutations)])
def consume(rid: int, body: s.ConsumeIn, db: Session = Depends(get_write_db), who: str = Depends(actor),
            idempotency_key: Optional[str] = IdemKey):
    endpoint = f"reservations.consume:{rid}"
    hit = common.idempotent_lookup(db, idempotency_key, endpoint, body.model_dump())
    if hit:
        return JSONResponse(hit[1], status_code=hit[0])
    r = db.get(m.Reservation, rid)
    if r is None:
        raise common.NotFound("Reservation", rid)
    out = inv.consume(db, r, actor=who, replacement_serial=body.replacement_serial, power_input_id=body.power_input_id,
                      failed_asset_id=body.failed_asset_id, note=body.note)
    resp = {"reservation": ser.reservation(out["reservation"]), "transaction": ser.txn(out["transaction"]),
            "replacement_asset": ser.asset(out["replacement_asset"]),
            "failed_asset": ser.asset(out["failed_asset"]) if out["failed_asset"] else None}
    common.idempotent_store(db, idempotency_key, endpoint, body.model_dump(), 200, resp)
    db.commit()
    return resp


@router.get("/inventory/transactions")
def transactions(db: Session = Depends(get_db), limit: int = Query(50, le=500)):
    rows = db.scalars(select(m.InventoryTransaction).order_by(m.InventoryTransaction.occurred_at.desc(), m.InventoryTransaction.id.desc()).limit(limit)).all()
    return [ser.txn(t) for t in rows]


# --------------------------------------------------------------------------- returns


@router.get("/returns")
def returns(db: Session = Depends(get_db)):
    return [ser.return_record(r) for r in db.scalars(select(m.ReturnRecord).order_by(m.ReturnRecord.id.desc())).all()]


@router.post("/returns", dependencies=[Depends(require_mutations)], status_code=201)
def create_return(body: s.ReturnIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    a = db.get(m.Asset, body.failed_asset_id)
    if a is None:
        raise common.NotFound("Asset", body.failed_asset_id)
    inc = db.get(m.Incident, body.incident_id) if body.incident_id else None
    rr = inv.create_return(db, failed_asset=a, failure_summary=body.failure_summary, actor=who, incident=inc,
                           failure_evidence_id=body.failure_evidence_id, replacement_asset_id=body.replacement_asset_id,
                           original_device_id=body.original_device_id, warranty_status=body.warranty_status)
    db.commit()
    return ser.return_record(rr)


@router.patch("/returns/{rid}", dependencies=[Depends(require_mutations)])
def update_return(rid: int, body: s.ReturnUpdateIn, db: Session = Depends(get_write_db), who: str = Depends(actor)):
    rr = db.get(m.ReturnRecord, rid)
    if rr is None:
        raise common.NotFound("Return", rid)
    inv.update_return(db, rr, actor=who, shipping_status=body.shipping_status, return_reference=body.return_reference,
                      warranty_status=body.warranty_status)
    db.commit()
    return ser.return_record(rr)
