"""Asset lifecycle, spare parts, reservations, consumption, and returns.

Stock is a ledger: on-hand = SUM(quantity_delta) per stock row, and available = on-hand
minus active reservations. Mutations run inside SQLite ``BEGIN IMMEDIATE`` transactions,
so reservation checks and writes are serialized. Reservation and consumption are separate
steps. Consumption is atomic and cannot happen twice for one reservation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from ..models import utcnow
from . import common

LIFECYCLE: dict[str, set[str]] = {
    "received": {"stored", "installed", "quarantined"},
    "stored": {"installed", "quarantined", "decommissioned"},
    "installed": {"active", "stored", "quarantined", "in_repair"},
    "active": {"in_repair", "quarantined", "pending_return", "decommissioned", "installed"},
    "quarantined": {"in_repair", "pending_return", "stored", "decommissioned"},
    "in_repair": {"active", "installed", "quarantined", "pending_return", "stored"},
    "pending_return": {"returned", "quarantined"},
    "returned": set(),
    "decommissioned": set(),
}

REQUIRED_INFO = {
    "stored": ("location", "A storage location is required."),
    "installed": ("device", "The device the asset is installed in is required."),
    "quarantined": ("note", "A quarantine reason is required."),
    "decommissioned": ("note", "A decommission reason is required."),
}


def transition_asset(db: Session, asset: m.Asset, to: str, actor: str, *, location: Optional[str] = None,
                     device_id: Optional[int] = None, note: str = "", origin: Optional[str] = None,
                     simulation_run_id: Optional[int] = None, at: Optional[datetime] = None,
                     _allow_pending_return: bool = False) -> m.Asset:
    frm = asset.status
    if to not in m.ASSET_STATUSES:
        raise common.DomainError("invalid_status", f"Unknown lifecycle state '{to}'.", 422)
    if to not in LIFECYCLE[frm]:
        raise common.DomainError("invalid_transition", f"{asset.display_id} cannot move from {frm.replace('_', ' ')} to {to.replace('_', ' ')}.",
                                 409, {"allowed": sorted(LIFECYCLE[frm])})
    req = REQUIRED_INFO.get(to)
    if req:
        field, msg = req
        if (field == "location" and not (location or "").strip()) or (field == "device" and not device_id) or \
           (field == "note" and not note.strip()):
            raise common.DomainError("missing_information", msg, 422, {"field": field})
    if to == "pending_return" and not _allow_pending_return:
        has_return = db.scalar(select(m.ReturnRecord).where(m.ReturnRecord.failed_asset_id == asset.id))
        if not has_return:
            raise common.DomainError("return_record_required", "Create a return record to move an asset to pending return.", 422)
    before = {"status": frm, "location": asset.location, "installed_in": asset.installed_in_device_id}
    asset.status = to
    if location is not None:
        asset.location = location
    if to == "installed":
        asset.installed_in_device_id = device_id
    if to in ("stored", "quarantined", "pending_return", "returned", "decommissioned"):
        asset.installed_in_device_id = None
    after = {"status": to, "location": asset.location, "installed_in": asset.installed_in_device_id}
    common.audit(db, actor=actor, action="asset.transition", entity_type="asset", entity_id=asset.id, entity_display=asset.display_id,
                 summary=f"{asset.display_id}: {frm.replace('_', ' ')} → {to.replace('_', ' ')}" + (f" ({note})" if note else ""),
                 before=before, after=after, origin=origin or ("simulation" if simulation_run_id else "operator"),
                 simulation_run_id=simulation_run_id, at=at)
    return asset


# --------------------------------------------------------------------------- stock


def on_hand(db: Session, stock_id: int) -> int:
    return int(db.scalar(select(func.coalesce(func.sum(m.InventoryTransaction.quantity_delta), 0))
                         .where(m.InventoryTransaction.stock_id == stock_id)) or 0)


def reserved(db: Session, stock_id: int) -> int:
    return int(db.scalar(select(func.coalesce(func.sum(m.Reservation.quantity), 0))
                         .where(m.Reservation.stock_id == stock_id, m.Reservation.status == "active")) or 0)


def stock_view(db: Session, s: m.SpareStock) -> dict[str, Any]:
    oh, rs = on_hand(db, s.id), reserved(db, s.id)
    avail = oh - rs
    return {"id": s.id, "display_id": s.display_id, "part_type_id": s.part_type_id, "part_number": s.part_type.part_number,
            "part_name": s.part_type.name, "category": s.part_type.category, "location": s.location,
            "on_hand": oh, "reserved": rs, "available": avail, "reorder_threshold": s.reorder_threshold,
            "low_stock": avail <= s.reorder_threshold,
            "compatible_models": [c.device_model for c in s.part_type.compatibility]}


def compatible_stock(db: Session, device: m.Device, category: Optional[str] = None) -> list[dict]:
    rows = db.scalars(select(m.SpareStock).join(m.PartType)).all()
    out = []
    for s in rows:
        if category and s.part_type.category != category:
            continue
        v = stock_view(db, s)
        v["compatible"] = device.model in v["compatible_models"]
        out.append(v)
    out.sort(key=lambda v: (not v["compatible"], -v["available"]))
    return out


def receive(db: Session, stock: m.SpareStock, qty: int, actor: str, note: str = "", origin: str = "operator",
            simulation_run_id: Optional[int] = None) -> m.InventoryTransaction:
    if qty <= 0:
        raise common.DomainError("invalid_quantity", "Received quantity must be positive.", 422)
    t = m.InventoryTransaction(display_id=common.next_display_id(db, "TXN", 5), stock_id=stock.id, kind="receive",
                               quantity_delta=qty, note=note, actor=actor, origin=origin, simulation_run_id=simulation_run_id)
    db.add(t)
    db.flush()
    common.audit(db, actor=actor, action="stock.receive", entity_type="stock", entity_id=stock.id, entity_display=stock.display_id,
                 summary=f"Received {qty} × {stock.part_type.part_number} into {stock.location}", after={"qty": qty},
                 origin=origin, simulation_run_id=simulation_run_id)
    return t


def reserve(db: Session, *, stock: m.SpareStock, quantity: int, device: Optional[m.Device], incident: Optional[m.Incident],
            reason: str, actor: str, compatibility_exception: bool = False, exception_reviewed_by: str = "",
            exception_note: str = "", now: Optional[datetime] = None) -> m.Reservation:
    now = now or utcnow()
    if quantity <= 0:
        raise common.DomainError("invalid_quantity", "Reservation quantity must be positive.", 422)
    if device is not None:
        compatible = any(c.device_model == device.model for c in stock.part_type.compatibility)
        if not compatible:
            if not compatibility_exception:
                raise common.DomainError(
                    "incompatible_part",
                    f"{stock.part_type.part_number} is not listed as compatible with {device.model}. "
                    "Reserve a compatible part, or record a reviewed compatibility exception.", 409,
                    {"device_model": device.model, "compatible_models": [c.device_model for c in stock.part_type.compatibility]})
            if not exception_reviewed_by.strip() or not exception_note.strip():
                raise common.DomainError("exception_review_required",
                                         "A compatibility exception requires a reviewer and a justification.", 422)
    # Serialized by BEGIN IMMEDIATE: no other writer can change stock between this read and our insert.
    available = on_hand(db, stock.id) - reserved(db, stock.id)
    if quantity > available:
        raise common.DomainError("insufficient_stock",
                                 f"Only {available} × {stock.part_type.part_number} available at {stock.location}.", 409,
                                 {"available": available, "requested": quantity})
    sim_id = incident.simulation_run_id if incident else None
    origin = "simulation" if sim_id else "operator"
    r = m.Reservation(display_id=common.next_display_id(db, "RSV"), stock_id=stock.id, quantity=quantity, status="active",
                      device_id=device.id if device else None, incident_id=incident.id if incident else None, reason=reason,
                      compatibility_exception=compatibility_exception, exception_reviewed_by=exception_reviewed_by,
                      exception_note=exception_note, actor=actor, origin=origin, simulation_run_id=sim_id)
    db.add(r)
    db.flush()
    common.audit(db, actor=actor, action="reservation.create", entity_type="reservation", entity_id=r.id, entity_display=r.display_id,
                 summary=f"Reserved {quantity} × {stock.part_type.part_number} for {device.display_id if device else 'unassigned'}"
                         + (" (REVIEWED COMPATIBILITY EXCEPTION)" if compatibility_exception else ""),
                 after={"available_after": available - quantity}, origin=origin, simulation_run_id=sim_id, at=now,
                 related=[x for x in ([{"type": "device", "id": device.id, "display": device.display_id}] if device else []) +
                          ([{"type": "incident", "id": incident.id, "display": incident.display_id}] if incident else [])])
    common.publish(db, "inventory", {"stock": stock.display_id, "event": "reserved"})
    return r


def release(db: Session, r: m.Reservation, actor: str, note: str = "") -> m.Reservation:
    if r.status != "active":
        raise common.DomainError("reservation_not_active", f"{r.display_id} is {r.status}.")
    r.status, r.released_at = "released", utcnow()
    common.audit(db, actor=actor, action="reservation.release", entity_type="reservation", entity_id=r.id, entity_display=r.display_id,
                 summary=f"Released {r.display_id}" + (f": {note}" if note else ""), origin=r.origin, simulation_run_id=r.simulation_run_id)
    common.publish(db, "inventory", {"stock": r.stock.display_id, "event": "released"})
    return r


def consume(db: Session, r: m.Reservation, *, actor: str, replacement_serial: str, power_input_id: Optional[int] = None,
            failed_asset_id: Optional[int] = None, note: str = "", now: Optional[datetime] = None) -> dict[str, Any]:
    """Atomically: ledger -qty, reservation consumed, replacement asset recorded, failed part removed.

    All writes happen in the caller's single transaction. A failure in any step rolls back all of them.
    """
    now = now or utcnow()
    if r.status == "consumed":
        raise common.DomainError("already_consumed", f"{r.display_id} was already consumed.", 409)
    if r.status != "active":
        raise common.DomainError("reservation_not_active", f"{r.display_id} is {r.status}.")
    if not replacement_serial.strip():
        raise common.DomainError("serial_required", "Record the replacement part's serial number.", 422)
    if db.scalar(select(m.Asset).where(m.Asset.serial_number == replacement_serial)):
        raise common.DomainError("duplicate_serial", f"Serial {replacement_serial} is already recorded on another asset.", 409)
    if on_hand(db, r.stock_id) < r.quantity:
        raise common.DomainError("insufficient_stock", "Ledger shows insufficient on-hand stock.", 409)
    sim_id = r.simulation_run_id
    origin = "simulation" if sim_id else "operator"
    device = db.get(m.Device, r.device_id) if r.device_id else None
    pt = r.stock.part_type

    r.status, r.consumed_at = "consumed", now
    txn = m.InventoryTransaction(display_id=common.next_display_id(db, "TXN", 5), stock_id=r.stock_id, kind="consume",
                                 quantity_delta=-r.quantity, reservation_id=r.id, note=note or f"Consumed for {device.display_id if device else 'n/a'}",
                                 actor=actor, origin=origin, simulation_run_id=sim_id, occurred_at=now)
    db.add(txn)
    new_asset = m.Asset(display_id=common.next_display_id(db, "NL-AST"), serial_number=replacement_serial, asset_type=pt.category,
                        part_type_id=pt.id, manufacturer="Northwind Lab Hardware (fictional)", model=pt.part_number,
                        status="installed", location=device.rack.display_id if device and device.rack else "",
                        installed_in_device_id=device.id if device else None, warranty_status="unknown",
                        notes=f"Installed from {r.display_id}", origin=origin, simulation_run_id=sim_id)
    db.add(new_asset)
    db.flush()
    txn.asset_id = new_asset.id
    common.audit(db, actor=actor, action="reservation.consume", entity_type="reservation", entity_id=r.id, entity_display=r.display_id,
                 summary=f"Consumed {r.display_id}: {pt.part_number} serial {replacement_serial} installed"
                         + (f" in {device.display_id}" if device else ""), after={"txn": txn.display_id, "asset": new_asset.display_id},
                 origin=origin, simulation_run_id=sim_id, at=now)
    common.audit(db, actor=actor, action="asset.create", entity_type="asset", entity_id=new_asset.id, entity_display=new_asset.display_id,
                 summary=f"Recorded replacement {pt.part_number} ({replacement_serial}) as installed", origin=origin,
                 simulation_run_id=sim_id, at=now)

    failed = None
    if power_input_id:
        pi = db.get(m.PowerInput, power_input_id)
        if pi is None or (device and pi.device_id != device.id):
            raise common.DomainError("invalid_power_input", "Power input does not belong to the reserved device.", 422)
        failed_asset_id = failed_asset_id or pi.component_asset_id
        before = pi.component_asset_id
        before_disp = db.get(m.Asset, before).display_id if before else None
        pi.component_asset_id = new_asset.id
        common.audit(db, actor=actor, action="power_input.component_replaced", entity_type="device", entity_id=pi.device_id,
                     entity_display=device.display_id if device else str(pi.device_id),
                     summary=f"{pi.name} component replaced: {before_disp or 'untracked'} → {new_asset.display_id} ({replacement_serial})",
                     before={"component": before_disp}, after={"component": new_asset.display_id, "serial": replacement_serial},
                     origin=origin, simulation_run_id=sim_id, at=now)
    if failed_asset_id:
        failed = db.get(m.Asset, failed_asset_id)
        if failed and failed.status in ("active", "installed", "in_repair"):
            transition_asset(db, failed, "quarantined", actor, location="Returns cage — North Lab", note="Removed as failed; awaiting return",
                             origin=origin, simulation_run_id=sim_id, at=now)
    common.publish(db, "inventory", {"stock": r.stock.display_id, "event": "consumed"})

    # A linked simulated incident gets the physical repair recorded on its timeline.
    if r.incident_id:
        from . import incidents
        inc = db.get(m.Incident, r.incident_id)
        if inc and inc.status == "investigating" and inc.scenario_key:
            from .scenarios import SCENARIOS
            sc = SCENARIOS.get(inc.scenario_key)
            if sc and sc.extra.get("requires_spare_workflow"):
                incidents.apply_repair_action(db, inc, sc.repairs[0].key, actor, now=now, _from_spare_workflow=True)
    return {"reservation": r, "transaction": txn, "replacement_asset": new_asset, "failed_asset": failed}


# --------------------------------------------------------------------------- returns


def create_return(db: Session, *, failed_asset: m.Asset, failure_summary: str, actor: str, incident: Optional[m.Incident] = None,
                  failure_evidence_id: Optional[int] = None, replacement_asset_id: Optional[int] = None,
                  original_device_id: Optional[int] = None, warranty_status: Optional[str] = None) -> m.ReturnRecord:
    if db.scalar(select(m.ReturnRecord).where(m.ReturnRecord.failed_asset_id == failed_asset.id)):
        raise common.DomainError("return_exists", f"{failed_asset.display_id} already has a return record.")
    if not failure_summary.strip():
        raise common.DomainError("summary_required", "Describe the failure.", 422)
    sim_id = incident.simulation_run_id if incident else failed_asset.simulation_run_id
    origin = "simulation" if sim_id else "operator"
    rr = m.ReturnRecord(display_id=common.next_display_id(db, "RMA"), failed_asset_id=failed_asset.id,
                        original_device_id=original_device_id, incident_id=incident.id if incident else None,
                        failure_evidence_id=failure_evidence_id, failure_summary=failure_summary,
                        warranty_status=warranty_status or failed_asset.warranty_status, replacement_asset_id=replacement_asset_id,
                        actor=actor, origin=origin, simulation_run_id=sim_id)
    db.add(rr)
    db.flush()
    if failed_asset.status != "pending_return":
        transition_asset(db, failed_asset, "pending_return", actor, note=f"Return {rr.display_id} opened", origin=origin,
                         simulation_run_id=sim_id, _allow_pending_return=True)
    common.audit(db, actor=actor, action="return.create", entity_type="return", entity_id=rr.id, entity_display=rr.display_id,
                 summary=f"Return {rr.display_id} recorded for {failed_asset.display_id} ({failed_asset.serial_number}). "
                         "No vendor was contacted; this records the return only.",
                 origin=origin, simulation_run_id=sim_id)
    return rr


SHIPPING_FLOW = {
    "awaiting_reference": {"ready_to_ship"},
    "ready_to_ship": {"shipped"},
    "shipped": {"received_by_vendor"},
    "received_by_vendor": {"closed"},
    "closed": set(),
}


def update_return(db: Session, rr: m.ReturnRecord, *, actor: str, shipping_status: Optional[str] = None,
                  return_reference: Optional[str] = None, warranty_status: Optional[str] = None) -> m.ReturnRecord:
    before = {"shipping_status": rr.shipping_status, "return_reference": rr.return_reference}
    if return_reference is not None:
        rr.return_reference = return_reference.strip() or None
    if warranty_status:
        rr.warranty_status = warranty_status
    if shipping_status and shipping_status != rr.shipping_status:
        if shipping_status not in SHIPPING_FLOW.get(rr.shipping_status, set()):
            raise common.DomainError("invalid_transition", f"Cannot move return from {rr.shipping_status} to {shipping_status}.")
        if shipping_status == "ready_to_ship" and not rr.return_reference:
            raise common.DomainError("reference_required", "Record the vendor-issued return reference first.", 422)
        rr.shipping_status = shipping_status
        if shipping_status == "closed":
            transition_asset(db, rr.failed_asset, "returned", actor, note=f"{rr.display_id} closed", origin=rr.origin,
                             simulation_run_id=rr.simulation_run_id)
    common.audit(db, actor=actor, action="return.update", entity_type="return", entity_id=rr.id, entity_display=rr.display_id,
                 summary=f"Return {rr.display_id} updated", before=before,
                 after={"shipping_status": rr.shipping_status, "return_reference": rr.return_reference},
                 origin=rr.origin, simulation_run_id=rr.simulation_run_id)
    return rr
