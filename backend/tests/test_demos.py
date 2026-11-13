from sqlalchemy import select

from app import models as m
from app.services import demos, inventory as inv, simulation

from .conftest import advance_probes


def _drive(db, key, clock, max_iter=80):
    for _ in range(max_iter):
        st = demos.status(db, key)
        if st["complete"]:
            return st
        step = st["steps"][st["current"]]
        if step.get("auto"):
            advance_probes(db, clock, 1)
        else:
            demos.next_step(db, key, "op", now=clock())
            db.flush()
            # pending acceptance runs are executed by the job runner
            from app.services import acceptance
            for r in db.scalars(select(m.AcceptanceRun).where(m.AcceptanceRun.status.in_(("queued", "running")))).all():
                acceptance.execute_all(db, r, clock())
            advance_probes(db, clock, 1)
    raise AssertionError(f"demo {key} did not complete: {demos.status(db, key)['current']}")


def test_restore_service_demo_end_to_end(db, clock):
    demos.start(db, "restore-service", "op", clock())
    st = _drive(db, "restore-service", clock)
    inc = db.get(m.Incident, st["run"]["incident_id"])
    assert inc.status == "resolved"
    assert any(not v.passed for v in inc.verifications)  # wrong hypothesis was tried and rejected
    assert inc.verifications[-1].passed


def test_acceptance_demo_end_to_end(db, clock):
    demos.start(db, "acceptance-retest", "op", clock())
    _drive(db, "acceptance-retest", clock)
    rec = db.scalar(select(m.IntakeRecord).where(m.IntakeRecord.display_id == "INT-0001"))
    assert [r.disposition for r in rec.runs] == ["FAIL", "PASS"]


def test_replace_component_demo_end_to_end(db, clock):
    st0 = inv.stock_view(db, db.scalar(select(m.SpareStock).join(m.PartType).where(m.PartType.part_number == "NL-PSU-800P")))
    demos.start(db, "replace-component", "op", clock())
    st = _drive(db, "replace-component", clock)
    inc = db.get(m.Incident, st["run"]["incident_id"])
    assert inc.status == "resolved"
    stock = db.scalar(select(m.SpareStock).join(m.PartType).where(m.PartType.part_number == "NL-PSU-800P"))
    assert inv.on_hand(db, stock.id) == st0["on_hand"] - 1
    failed = db.scalar(select(m.Asset).where(m.Asset.display_id == "NL-AST-P04B"))
    assert failed.status == "pending_return"
    actions = {a.action for a in db.query(m.AuditEvent).filter(m.AuditEvent.simulation_run_id.isnot(None)).all()}
    assert {"reservation.create", "reservation.consume", "asset.transition", "return.create", "incident.resolved"} <= actions


def test_reset_is_isolated_to_simulation_data(client, db, clock):
    # Imported sample + operator-recorded data must survive a reset
    assert client.post("/api/integrations/alertmanager/sample").status_code == 200
    db.rollback()
    imported = db.scalar(select(m.Incident).where(m.Incident.source_type == "IMPORTED_SAMPLE"))
    stock = db.scalar(select(m.SpareStock).join(m.PartType).where(m.PartType.part_number == "NL-DIMM-16G-D5"))
    inv.receive(db, stock, 4, "op", "operator delivery")
    db.add(m.MetricObservation(metric="service_up", value=1, unit="bool", observed_at=clock(), source_type="LOCAL_LAB", source_id="t"))
    db.commit()
    demos.start(db, "replace-component", "op", clock())
    _drive(db, "replace-component", clock)
    db.commit()
    r = client.post("/api/simulation/reset")
    assert r.status_code == 200
    db.rollback()
    assert db.get(m.Incident, imported.id) is not None
    assert db.query(m.Incident).filter_by(source_type="SIMULATED").count() == 0
    assert inv.on_hand(db, stock.id) == 10  # 6 seed + 4 operator, untouched
    psu = db.scalar(select(m.SpareStock).join(m.PartType).where(m.PartType.part_number == "NL-PSU-800P"))
    assert inv.on_hand(db, psu.id) == 2 and inv.reserved(db, psu.id) == 0  # demo consumption reverted
    failed = db.scalar(select(m.Asset).where(m.Asset.display_id == "NL-AST-P04B"))
    assert failed.status == "active"  # seed baseline restored
    assert db.query(m.MetricObservation).filter_by(source_type="LOCAL_LAB").count() == 1
    assert db.query(m.ReturnRecord).count() == 0


def test_demo_restart_is_repeatable(db, clock):
    demos.start(db, "acceptance-retest", "op", clock())
    _drive(db, "acceptance-retest", clock)
    demos.start(db, "acceptance-retest", "op", clock.advance(5))
    rec = db.scalar(select(m.IntakeRecord).where(m.IntakeRecord.display_id == "INT-0001"))
    db.refresh(rec)
    assert rec.runs == [] and rec.simulated_corrections == [] and rec.status == "awaiting_acceptance"
    _drive(db, "acceptance-retest", clock)
