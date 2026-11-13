import pytest
from sqlalchemy import select

from app import models as m
from app.acceptance.checks import REGISTRY, disposition, effective_disposition
from app.services import acceptance as svc
from app.services import common


def _intake(db, disp="INT-0001"):
    return db.scalar(select(m.IntakeRecord).where(m.IntakeRecord.display_id == disp))


def test_hardware_mismatch_fails(db, clock):
    rec = _intake(db)
    run = svc.execute_all(db, svc.start_run(db, rec, "simulator", "op", clock()), clock())
    assert run.disposition == "FAIL"
    res = {r.check_key: r for r in run.results}
    assert res["memory_capacity"].result == "FAIL" and res["memory_capacity"].observed_value == "64" and res["memory_capacity"].unit == "GiB"
    assert res["link_speed"].result == "FAIL" and res["link_speed"].observed_value == "1000"
    assert res["nic_inventory"].result == "PASS"
    assert rec.status == "failed"


def test_missing_required_evidence_cannot_pass(db, clock):
    rec = _intake(db, "INT-0002")  # disk health unsupported, corrected AER line
    run = svc.execute_all(db, svc.start_run(db, rec, "simulator", "op", clock()), clock())
    res = {r.check_key: r for r in run.results}
    assert res["disk_health"].result == "UNSUPPORTED"
    assert res["disk_health"].observed_value == "Not collected"
    assert run.disposition == "MANUAL_REVIEW"
    # unresolved manual review keeps MANUAL_REVIEW; handoff refused
    with pytest.raises(common.DomainError):
        svc.handoff(db, rec, {k: True for k in svc.HANDOFF_CHECKLIST}, "op")
    svc.record_manual_review(db, run, "disk_health", "accept", "smartctl -H reviewed manually as root on bench: PASSED", "lead")
    assert svc.run_effective(run) == "MANUAL_REVIEW"  # kernel_errors still pending
    svc.record_manual_review(db, run, "kernel_errors", "accept", "Single corrected AER event at boot; within vendor guidance", "lead")
    assert svc.run_effective(run) == "PASS"
    assert run.disposition == "MANUAL_REVIEW"  # stored result is immutable


def test_disposition_rules():
    R = lambda k, req, res: {"check_key": k, "required": req, "result": res}
    assert disposition([R("a", True, "PASS"), R("b", False, "FAIL")]) == "PASS"  # optional never decides
    assert disposition([R("a", True, "PASS"), R("b", True, "SKIPPED")]) == "MANUAL_REVIEW"
    assert disposition([R("a", True, "ERROR"), R("b", True, "FAIL")]) == "FAIL"
    assert disposition([R("a", True, "UNSUPPORTED")]) == "MANUAL_REVIEW"
    assert effective_disposition([R("a", True, "UNSUPPORTED")], {"a": {"decision": "reject"}}) == "FAIL"


def test_missing_section_is_unsupported_not_zero():
    out = REGISTRY["memory_capacity"].run({"memory_gib": 128}, {})
    assert out.result == "UNSUPPORTED" and out.observed == "Not collected"


def test_retest_creates_new_immutable_run(db, clock):
    rec = _intake(db)
    r1 = svc.execute_all(db, svc.start_run(db, rec, "simulator", "op", clock()), clock())
    snap1 = {r.check_key: (r.result, r.observed_value) for r in r1.results}
    obs1 = dict(r1.observed_snapshot)
    for k in ("install_dimms", "replace_transceiver"):
        svc.apply_correction(db, rec, k, "op", clock.advance(5))
    r2 = svc.execute_all(db, svc.start_run(db, rec, "simulator", "op", clock.advance(5)), clock())
    assert r2.id != r1.id and r2.run_number == 2 and r2.disposition == "PASS"
    db.refresh(r1)
    assert {r.check_key: (r.result, r.observed_value) for r in r1.results} == snap1
    assert r1.observed_snapshot == obs1 and r1.disposition == "FAIL"
    diff = svc.compare(r1, r2)
    changed = {row["check_key"] for row in diff["rows"] if row["changed"]}
    assert changed == {"memory_capacity", "link_speed"}
    assert len(diff["corrections_between"]) == 2
    assert all(c["source_type"] == "SIMULATED" for c in r2.corrections_before_run)


def test_reports_preserve_source_and_timestamps(client, db):
    rec = _intake(db)
    r = client.post(f"/api/acceptance/intakes/{rec.id}/runs", json={"collector": "simulator"})
    assert r.status_code == 201, r.text
    db.rollback()  # end this session's read snapshot so it sees the API's commit
    run = db.get(m.AcceptanceRun, r.json()["id"])
    svc.execute_all(db, run)
    db.commit()
    rep = client.get(f"/api/acceptance/runs/{run.id}/report.json").json()
    assert rep["source_type"] == "SIMULATED" and rep["completed_at"] and rep["source_id"].startswith("sim:intake:")
    assert all(x["source_type"] == "SIMULATED" and x["executed_at"] for x in rep["results"])
    # Mutating the intake after the run does not change the report
    rec.expected = rec.expected | {"memory_gib": 64}
    db.commit()
    rep2 = client.get(f"/api/acceptance/runs/{run.id}/report.json").json()
    assert rep2["expected_snapshot"]["memory_gib"] == 128
    html = client.get(f"/api/acceptance/runs/{run.id}/report.html").text
    assert "SIMULATED" in html and run.display_id in html and "FAIL" in html


def test_redfish_fixture_mode_and_read_only():
    from app.collectors import redfish
    client = redfish.RedfishClient(None)
    obs = redfish.collect_observations(client)
    assert obs["memory"]["total_gib"] == 64 and len(obs["memory"]["dimms"]) == 4  # absent slot skipped
    assert "_unsupported" in obs["disk_health"]
    assert client.describe()["mode"] == "fixture" and "password" not in str(client.describe()).lower()
    public = [n for n in dir(redfish.RedfishClient) if not n.startswith("_")]
    assert not any(n in public for n in ("post", "patch", "put", "delete", "reset", "power"))
    with pytest.raises(redfish.RedfishError):
        client.get("/etc/passwd")


def test_upload_sanitized_and_size_limited(client, db):
    rec = _intake(db, "INT-0002")
    body = b'{"identity": {"serial_number": "SIM-NL1U-0007", "note": "password=hunter2"}, "_meta": {"host": "bench"}}'
    r = client.post(f"/api/acceptance/intakes/{rec.id}/upload", files={"file": ("o.json", body, "application/json")},
                    data={"source_type": "LOCAL_LAB"})
    assert r.status_code == 200, r.text
    db.rollback()
    db.refresh(rec)
    assert "hunter2" not in str(rec.uploaded_observations)
    big = b'{"identity": "' + b"x" * 600_000 + b'"}'
    r = client.post(f"/api/acceptance/intakes/{rec.id}/upload", files={"file": ("o.json", big, "application/json")},
                    data={"source_type": "LOCAL_LAB"})
    assert r.status_code == 413
    r = client.post(f"/api/acceptance/intakes/{rec.id}/upload", files={"file": ("o.json", b'{"evil": 1}', "application/json")},
                    data={"source_type": "LOCAL_LAB"})
    assert r.status_code == 422
