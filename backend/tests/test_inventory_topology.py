import pytest
from sqlalchemy import select

from app import models as m
from app.services import common, inventory as inv, topology as topo


def _stock(db, pn):
    return db.scalar(select(m.SpareStock).join(m.PartType).where(m.PartType.part_number == pn))


def _dev(db, d):
    return db.scalar(select(m.Device).where(m.Device.display_id == d))


def test_reservations_cannot_exceed_stock(db):
    st, dev = _stock(db, "NL-PSU-800P"), _dev(db, "lab-srv-04")
    inv.reserve(db, stock=st, quantity=2, device=dev, incident=None, reason="t", actor="op")
    with pytest.raises(common.DomainError) as e:
        inv.reserve(db, stock=st, quantity=1, device=dev, incident=None, reason="t", actor="op")
    assert e.value.code == "insufficient_stock"
    v = inv.stock_view(db, st)
    assert v["on_hand"] == 2 and v["reserved"] == 2 and v["available"] == 0


def test_incompatible_part_requires_reviewed_exception(db):
    st, dev = _stock(db, "NL-PSU-550S"), _dev(db, "lab-srv-04")
    with pytest.raises(common.DomainError) as e:
        inv.reserve(db, stock=st, quantity=1, device=dev, incident=None, reason="t", actor="op")
    assert e.value.code == "incompatible_part"
    with pytest.raises(common.DomainError) as e:
        inv.reserve(db, stock=st, quantity=1, device=dev, incident=None, reason="t", actor="op", compatibility_exception=True)
    assert e.value.code == "exception_review_required"
    r = inv.reserve(db, stock=st, quantity=1, device=dev, incident=None, reason="t", actor="op", compatibility_exception=True,
                    exception_reviewed_by="lead", exception_note="Vendor bulletin permits as temporary measure")
    assert r.compatibility_exception


def test_consumption_is_atomic_and_not_repeatable(db):
    st, dev = _stock(db, "NL-PSU-800P"), _dev(db, "lab-srv-04")
    pi = db.scalar(select(m.PowerInput).where(m.PowerInput.device_id == dev.id, m.PowerInput.name == "PSU2"))
    failed_id = pi.component_asset_id
    r = inv.reserve(db, stock=st, quantity=1, device=dev, incident=None, reason="t", actor="op")
    db.commit()
    # A failing step (bad power input) must roll back everything, including the ledger row
    other = db.scalar(select(m.PowerInput).where(m.PowerInput.device_id == _dev(db, "lab-srv-01").id, m.PowerInput.name == "PSU1"))
    with pytest.raises(common.DomainError):
        inv.consume(db, r, actor="op", replacement_serial="SIM-X-1", power_input_id=other.id)
    db.rollback()
    db.refresh(r)
    assert r.status == "active" and inv.on_hand(db, st.id) == 2
    assert db.scalar(select(m.Asset).where(m.Asset.serial_number == "SIM-X-1")) is None
    out = inv.consume(db, r, actor="op", replacement_serial="SIM-X-1", power_input_id=pi.id)
    db.commit()
    assert inv.on_hand(db, st.id) == 1 and r.status == "consumed"
    assert db.get(m.Asset, failed_id).status == "quarantined"
    with pytest.raises(common.DomainError) as e:
        inv.consume(db, r, actor="op", replacement_serial="SIM-X-2", power_input_id=pi.id)
    assert e.value.code == "already_consumed"


def test_repeated_api_requests_do_not_double_consume(client, db):
    st, dev = _stock(db, "NL-PSU-800P"), _dev(db, "lab-srv-04")
    h = {"Idempotency-Key": "test-key-reserve-1"}
    body = {"stock_id": st.id, "quantity": 1, "device_id": dev.id, "reason": "psu"}
    a = client.post("/api/reservations", json=body, headers=h)
    b = client.post("/api/reservations", json=body, headers=h)
    assert a.status_code == b.status_code == 201 and a.json()["id"] == b.json()["id"]
    db.rollback()
    assert db.query(m.Reservation).count() == 1
    rid = a.json()["id"]
    c = {"replacement_serial": "SIM-IDEM-1"}
    h2 = {"Idempotency-Key": "test-key-consume-1"}
    r1 = client.post(f"/api/reservations/{rid}/consume", json=c, headers=h2)
    r2 = client.post(f"/api/reservations/{rid}/consume", json=c, headers=h2)
    assert r1.status_code == r2.status_code == 200 and r1.json() == r2.json()
    r3 = client.post(f"/api/reservations/{rid}/consume", json=c)  # no key → rejected, not duplicated
    assert r3.status_code == 409 and r3.json()["error"]["code"] == "already_consumed"
    db.rollback()
    assert inv.on_hand(db, st.id) == 1
    assert db.query(m.InventoryTransaction).filter_by(kind="consume").count() == 1
    r4 = client.post(f"/api/reservations/{rid}/consume", json={"replacement_serial": "DIFF"}, headers=h2)
    assert r4.status_code == 422  # key reused with different body


def test_asset_transitions_validated_and_audited(db):
    a = db.scalar(select(m.Asset).where(m.Asset.display_id == "NL-AST-0006"))  # received
    with pytest.raises(common.DomainError):
        inv.transition_asset(db, a, "active", "op")  # received → active not allowed
    with pytest.raises(common.DomainError) as e:
        inv.transition_asset(db, a, "stored", "op")
    assert e.value.code == "missing_information"
    inv.transition_asset(db, a, "stored", "op", location="Receiving cage")
    inv.transition_asset(db, a, "quarantined", "op", note="Shipping damage")
    with pytest.raises(common.DomainError) as e:
        inv.transition_asset(db, a, "pending_return", "op")
    assert e.value.code == "return_record_required"
    rr = inv.create_return(db, failed_asset=a, failure_summary="Bent rail", actor="op")
    assert a.status == "pending_return" and rr.warranty_status == "known_active"
    trail = db.query(m.AuditEvent).filter_by(entity_type="asset", entity_id=a.id).order_by(m.AuditEvent.id).all()
    assert [t.after["status"] for t in trail] == ["stored", "quarantined", "pending_return"]
    assert trail[0].before["status"] == "received"


def test_return_requires_reference_before_ship(db):
    a = db.scalar(select(m.Asset).where(m.Asset.display_id == "NL-AST-P04B"))
    inv.transition_asset(db, a, "quarantined", "op", note="failed")
    rr = inv.create_return(db, failed_asset=a, failure_summary="PSU fault", actor="op")
    with pytest.raises(common.DomainError):
        inv.update_return(db, rr, actor="op", shipping_status="ready_to_ship")
    inv.update_return(db, rr, actor="op", return_reference="RMA-REF-SAMPLE-1", shipping_status="ready_to_ship")
    with pytest.raises(common.DomainError):
        inv.update_return(db, rr, actor="op", shipping_status="closed")  # must follow flow


def test_rack_overlap_and_bounds_rejected(db):
    dev, rack = _dev(db, "lab-srv-01"), db.scalar(select(m.Rack).where(m.Rack.display_id == "NL-R01"))
    with pytest.raises(common.DomainError) as e:
        topo.place_device(db, dev, "NL-R01", 31, "op")  # lab-srv-04 occupies U30–31
    assert e.value.code == "rack_overlap" and e.value.detail["conflict_device"] == "lab-srv-04"
    with pytest.raises(common.DomainError) as e:
        topo.assert_space_free(db, rack, 42, 2, None)
    assert e.value.code == "out_of_bounds"
    topo.place_device(db, dev, "NL-R01", 10, "op")  # free space works
    assert dev.position_u == 10


def test_invalid_cable_endpoints_rejected(db):
    sw = _dev(db, "lab-sw-01")
    free = next(i for i in sw.interfaces if i.name == "Eth1/9")
    used = next(i for i in sw.interfaces if i.name == "Eth1/2")
    srv06_like = next(i for i in _dev(db, "lab-sw-02").interfaces if i.name == "Gi1/9")
    with pytest.raises(common.DomainError) as e:
        topo.validate_cable(db, free.id, 999999, "om4-lc-lc", "CBL-X")
    assert e.value.code == "missing_endpoint"
    with pytest.raises(common.DomainError) as e:
        topo.validate_cable(db, free.id, used.id, "om4-lc-lc", "CBL-X")
    assert e.value.code == "endpoint_occupied"
    with pytest.raises(common.DomainError) as e:
        topo.validate_cable(db, free.id, srv06_like.id, "cat6a", "CBL-X")
    assert e.value.code == "incompatible_connector"
    warn = topo.validate_cable(db, free.id, next(i for i in sw.interfaces if i.name == "Eth1/10").id, "om4-lc-lc", None)
    assert warn[0]["code"] == "unlabeled"


def test_trace_follows_only_modeled_links(db):
    eth1 = next(i for i in _dev(db, "lab-srv-05").interfaces if i.name == "eth1")
    t = topo.trace(db, eth1.id)
    assert t["complete"] and "nl-r01-pp-01:P01-R" in t["text"] and t["text"].endswith("lab-sw-01:Eth1/5")
    lone = next(i for i in _dev(db, "lab-sw-01").interfaces if i.name == "Eth1/11")
    t2 = topo.trace(db, lone.id)
    assert not t2["complete"] and "nothing beyond is inferred" in t2["note"]


def test_shared_upstream_power_flagged(db):
    codes = lambda d: {f["code"] for f in topo.power_analysis(db, _dev(db, d))["findings"]}
    assert "shared_upstream" in codes("lab-srv-05")  # different PDU names, same UPS-A
    assert "missing_power_connection" in codes("lab-srv-03")
    assert "upstream_unknown" in codes("lab-sw-02")
    assert codes("lab-srv-01") == set()
    assert topo.power_analysis(db, _dev(db, "lab-srv-01"))["independence"].startswith("independent")
    assert topo.power_analysis(db, _dev(db, "lab-srv-05"))["independence"] == "not independent"


def test_cable_audit_finds_seeded_defects(db):
    codes = {i["code"] for i in topo.cable_audit(db)}
    assert {"unlabeled", "incompatible_connector"} <= codes
