"""Rack placement, cable modeling, and power-topology analysis.

Connectivity is never inferred. A path follows only modeled cables and modeled
patch-panel pass-throughs. Power "redundancy" is only reported as independent when two
inputs trace to different, known upstream sources. Different PDU names alone prove nothing.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models as m
from . import common

# Modeled connector compatibility: interface connector -> acceptable cable types
CABLE_COMPAT = {
    "RJ45": {"cat6", "cat6a"},
    "SFP+": {"om4-lc-lc", "dac-sfp+", "os2-lc-lc"},  # via transceiver (fiber) or DAC
    "LC": {"om4-lc-lc", "os2-lc-lc"},
    "QSFP28": {"dac-qsfp28", "mpo-12"},
}


def assert_space_free(db: Session, rack: m.Rack, position_u: int, u_height: int, exclude_device_id: Optional[int]) -> None:
    if u_height < 1:
        return
    if position_u < 1 or position_u + u_height - 1 > rack.u_height:
        raise common.DomainError("out_of_bounds",
                                 f"U{position_u}–U{position_u + u_height - 1} is outside {rack.display_id} (1–{rack.u_height}U).", 422)
    want = set(range(position_u, position_u + u_height))
    devs = db.scalars(select(m.Device).where(m.Device.rack_id == rack.id, m.Device.position_u.isnot(None))).all()
    for d in devs:
        if d.id == exclude_device_id or d.u_height < 1:
            continue
        occ = set(range(d.position_u, d.position_u + d.u_height))
        if want & occ:
            raise common.DomainError("rack_overlap",
                                     f"U{min(want & occ)} in {rack.display_id} is occupied by {d.display_id}.", 409,
                                     {"conflict_device": d.display_id, "units": sorted(want & occ)})


def place_device(db: Session, device: m.Device, rack_display: str, position_u: int, actor: str) -> m.Device:
    rack = common.get_or_404(db, m.Rack, rack_display, "Rack")
    assert_space_free(db, rack, position_u, device.u_height, exclude_device_id=device.id)
    before = {"rack": device.rack.display_id if device.rack else None, "position_u": device.position_u}
    device.rack_id, device.position_u = rack.id, position_u
    common.audit(db, actor=actor, action="device.place", entity_type="device", entity_id=device.id,
                 entity_display=device.display_id, summary=f"Placed {device.display_id} at {rack.display_id} U{position_u}",
                 before=before, after={"rack": rack.display_id, "position_u": position_u})
    return device


def elevation(db: Session, rack: m.Rack) -> dict[str, Any]:
    devs = db.scalars(select(m.Device).where(m.Device.rack_id == rack.id)).all()
    occupied = set()
    for d in devs:
        if d.position_u and d.u_height:
            occupied |= set(range(d.position_u, d.position_u + d.u_height))
    free = [u for u in range(1, rack.u_height + 1) if u not in occupied]
    return {"devices": devs, "free_units": free, "free_count": len(free)}


# --------------------------------------------------------------------------- cables


def validate_cable(db: Session, a_id: int, b_id: int, cable_type: str, label: Optional[str],
                   exclude_cable_id: Optional[int] = None) -> list[dict]:
    """Return blocking errors (raise) and warnings (return)."""
    a, b = db.get(m.DeviceInterface, a_id), db.get(m.DeviceInterface, b_id)
    if a is None or b is None:
        raise common.DomainError("missing_endpoint", "Both cable endpoints must reference modeled interfaces.", 422,
                                 {"a_found": a is not None, "b_found": b is not None})
    if a.id == b.id:
        raise common.DomainError("same_endpoint", "A cable cannot connect an interface to itself.", 422)
    for iface in (a, b):
        q = select(m.CableConnection).where(or_(m.CableConnection.a_interface_id == iface.id,
                                                m.CableConnection.b_interface_id == iface.id))
        if exclude_cable_id:
            q = q.where(m.CableConnection.id != exclude_cable_id)
        existing = db.scalar(q)
        if existing:
            raise common.DomainError("endpoint_occupied",
                                     f"{iface.device.display_id} {iface.name} is already used by cable {existing.label or f'#{existing.id} (unlabeled)'}.",
                                     409)
    for iface in (a, b):
        allowed = CABLE_COMPAT.get(iface.connector_type)
        if allowed is not None and cable_type not in allowed:
            raise common.DomainError("incompatible_connector",
                                     f"Cable type {cable_type} does not fit {iface.connector_type} on {iface.device.display_id} {iface.name}.",
                                     422, {"allowed": sorted(allowed)})
    warnings = []
    if not label:
        warnings.append({"code": "unlabeled", "message": "Cable has no label. Label both ends before closing the work."})
    return warnings


def create_cable(db: Session, data: dict, actor: str) -> tuple[m.CableConnection, list[dict]]:
    warnings = validate_cable(db, data["a_interface_id"], data["b_interface_id"], data["cable_type"], data.get("label"))
    if data.get("label") and db.scalar(select(m.CableConnection).where(m.CableConnection.label == data["label"])):
        raise common.DomainError("duplicate_label", f"Cable label {data['label']} already exists.", 409)
    c = m.CableConnection(label=data.get("label") or None, cable_type=data["cable_type"], a_interface_id=data["a_interface_id"],
                          b_interface_id=data["b_interface_id"], intended_speed_mbps=data.get("intended_speed_mbps"),
                          length_m=data.get("length_m"), status=data.get("status", "connected"), origin="operator")
    db.add(c)
    db.flush()
    common.audit(db, actor=actor, action="cable.create", entity_type="cable", entity_id=c.id, entity_display=c.label or f"cable#{c.id}",
                 summary=f"Recorded cable {c.label or '(unlabeled)'}", after={"a": c.a_interface_id, "b": c.b_interface_id, "type": c.cable_type})
    return c, warnings


def label_cable(db: Session, cable: m.CableConnection, label: str, actor: str) -> m.CableConnection:
    if db.scalar(select(m.CableConnection).where(m.CableConnection.label == label, m.CableConnection.id != cable.id)):
        raise common.DomainError("duplicate_label", f"Cable label {label} already exists.", 409)
    before = cable.label
    cable.label = label
    common.audit(db, actor=actor, action="cable.label", entity_type="cable", entity_id=cable.id, entity_display=label,
                 summary=f"Labeled cable #{cable.id} as {label}", before={"label": before}, after={"label": label})
    return cable


def _cable_on(db: Session, iface_id: int) -> Optional[m.CableConnection]:
    return db.scalar(select(m.CableConnection).where(or_(m.CableConnection.a_interface_id == iface_id,
                                                         m.CableConnection.b_interface_id == iface_id)))


def _iface_ref(i: m.DeviceInterface) -> dict:
    return {"interface_id": i.id, "device_id": i.device_id, "device": i.device.display_id, "interface": i.name,
            "kind": i.kind, "connector": i.connector_type, "role": i.device.role}


def trace(db: Session, start_iface_id: int, max_hops: int = 8) -> dict[str, Any]:
    start = db.get(m.DeviceInterface, start_iface_id)
    if start is None:
        raise common.NotFound("Interface", start_iface_id)
    hops: list[dict] = [{"type": "endpoint", **_iface_ref(start)}]
    seen = {start.id}
    cur = start
    complete = False
    note = ""
    for _ in range(max_hops):
        cable = _cable_on(db, cur.id)
        if cable is None:
            note = f"No modeled cable on {cur.device.display_id} {cur.name}. The path ends here; nothing beyond is inferred."
            break
        other_id = cable.b_interface_id if cable.a_interface_id == cur.id else cable.a_interface_id
        other = db.get(m.DeviceInterface, other_id)
        hops.append({"type": "cable", "cable_id": cable.id, "label": cable.label, "cable_type": cable.cable_type,
                     "status": cable.status, "intended_speed_mbps": cable.intended_speed_mbps, "length_m": cable.length_m})
        hops.append({"type": "endpoint", **_iface_ref(other)})
        if other.id in seen:
            note = "Loop detected in modeled cabling."
            break
        seen.add(other.id)
        if other.pass_through_id:
            pt = db.get(m.DeviceInterface, other.pass_through_id)
            hops.append({"type": "pass_through", "device": other.device.display_id, "from": other.name, "to": pt.name,
                         "note": "Modeled patch-panel pass-through"})
            hops.append({"type": "endpoint", **_iface_ref(pt)})
            seen.add(pt.id)
            cur = pt
            continue
        complete = other.device.role != "patch_panel"
        if not complete:
            note = f"Path stops at patch-panel port {other.name}; no pass-through is modeled for it."
        break
    text = " → ".join(
        (f"{h['device']}:{h['interface']}" if h["type"] == "endpoint" else
         (f"[{h['label'] or 'UNLABELED'} {h['cable_type']}]" if h["type"] == "cable" else "(pass-through)"))
        for h in hops)
    return {"hops": hops, "text": text, "complete": complete, "note": note, "basis": "Modeled lab topology"}


def cable_audit(db: Session) -> list[dict]:
    """Documentation defects across all modeled cables."""
    issues = []
    for c in db.scalars(select(m.CableConnection)).all():
        if not c.label:
            issues.append({"cable_id": c.id, "code": "unlabeled", "severity": "warning",
                           "message": f"Cable between {c.a_interface.device.display_id}:{c.a_interface.name} and "
                                      f"{c.b_interface.device.display_id}:{c.b_interface.name} has no label."})
        for iface in (c.a_interface, c.b_interface):
            allowed = CABLE_COMPAT.get(iface.connector_type)
            if allowed is not None and c.cable_type not in allowed:
                issues.append({"cable_id": c.id, "code": "incompatible_connector", "severity": "critical",
                               "message": f"{c.label or 'Unlabeled cable'} ({c.cable_type}) does not fit {iface.connector_type} on "
                                          f"{iface.device.display_id}:{iface.name}."})
        if c.intended_speed_mbps:
            for iface in (c.a_interface, c.b_interface):
                if iface.speed_capability_mbps and iface.speed_capability_mbps < c.intended_speed_mbps:
                    issues.append({"cable_id": c.id, "code": "speed_mismatch", "severity": "warning",
                                   "message": f"{c.label or 'Unlabeled cable'} intended for {c.intended_speed_mbps} Mb/s but "
                                              f"{iface.device.display_id}:{iface.name} supports {iface.speed_capability_mbps} Mb/s."})
    return issues


# --------------------------------------------------------------------------- power


def power_analysis(db: Session, device: m.Device) -> dict[str, Any]:
    inputs = []
    for pi in device.power_inputs:
        o = pi.outlet
        feed = o.feed if o else None
        inputs.append({
            "input": pi.name, "input_id": pi.id, "connector": pi.connector_type,
            "outlet": f"{o.pdu.display_id}/{o.name}" if o else None,
            "pdu": o.pdu.display_id if o else None,
            "feed": feed.display_id if feed else None,
            "upstream": feed.upstream_source if feed else None,
            "rated_w": pi.rated_w, "estimated_load_w": pi.estimated_load_w,
            "component_asset": pi.component_asset.display_id if pi.component_asset else None,
            "component_asset_id": pi.component_asset_id,
        })
    findings = []
    if device.role in ("server", "switch"):
        if not inputs:
            findings.append({"code": "no_inputs_modeled", "severity": "warning", "message": "No power inputs are modeled for this device."})
        for i in inputs:
            if i["outlet"] is None:
                findings.append({"code": "missing_power_connection", "severity": "critical",
                                 "message": f"{i['input']} has no modeled PDU outlet connection."})
        connected = [i for i in inputs if i["outlet"]]
        if len(connected) >= 2:
            ups = [i["upstream"] for i in connected]
            if any(u is None for u in ups):
                findings.append({"code": "upstream_unknown", "severity": "warning",
                                 "message": "Upstream source of at least one feed is unknown, so independence cannot be confirmed."})
            elif len(set(ups)) == 1:
                findings.append({"code": "shared_upstream", "severity": "critical",
                                 "message": f"All inputs trace to the same upstream source ({ups[0]}). Different PDU names do not provide independent power."})
        elif len(inputs) >= 2:
            pass  # missing connection already flagged
    independent = (len(inputs) >= 2 and not any(f["code"] in ("shared_upstream", "upstream_unknown", "missing_power_connection")
                                                for f in findings))
    return {"inputs": inputs, "findings": findings,
            "independence": "independent upstream sources (modeled)" if independent else
            ("not independent" if any(f["code"] == "shared_upstream" for f in findings) else "unconfirmed"),
            "disclaimer": "Documentation model only: not an electrical design certification. Loads are estimates."}


def power_overview(db: Session) -> dict[str, Any]:
    feeds = db.scalars(select(m.PowerFeed).order_by(m.PowerFeed.display_id)).all()
    out = []
    for f in feeds:
        outlets = db.scalars(select(m.PduOutlet).where(m.PduOutlet.feed_id == f.id)).all()
        load = 0.0
        n = 0
        for o in outlets:
            pi = db.scalar(select(m.PowerInput).where(m.PowerInput.outlet_id == o.id))
            if pi and pi.estimated_load_w is not None:
                load += pi.estimated_load_w
                n += 1
        out.append({"feed": f.display_id, "name": f.name, "upstream": f.upstream_source, "capacity_w": f.capacity_w,
                    "estimated_load_w": round(load, 1) if n else None, "connected_inputs": n,
                    "utilization_pct_estimate": round(100 * load / f.capacity_w, 1) if (n and f.capacity_w) else None})
    issues = []
    for d in db.scalars(select(m.Device).where(m.Device.role.in_(("server", "switch")))).all():
        for fnd in power_analysis(db, d)["findings"]:
            issues.append({"device": d.display_id, "device_id": d.id, **fnd})
    return {"feeds": out, "issues": issues, "basis": "Modeled lab topology. Loads are estimates."}
