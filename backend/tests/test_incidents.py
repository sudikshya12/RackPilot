import pytest

from app import models as m
from app.services import common, incidents as svc, simulation

from .conftest import advance_probes, run_until_incident


def _open(db, clock, key="svc-stopped"):
    run = simulation.start(db, key, now=clock())
    inc = run_until_incident(db, run, clock)
    svc.acknowledge(db, inc, "op", clock.advance(5))
    svc.start_investigation(db, inc, "op", clock.advance(1))
    return run, inc


def test_detection_is_deterministic_and_after_two_failed_probes(db, clock):
    run = simulation.start(db, "svc-stopped", now=clock())
    inc = run_until_incident(db, run, clock)
    # baseline 4 probes (0..3), fault injected at probe 4, detected at probe 5 → 3 s after onset
    assert inc.fault_onset_at is not None
    assert (inc.detected_at - inc.fault_onset_at).total_seconds() == 3.0
    vals = db.query(m.MetricObservation).filter_by(simulation_run_id=run.id, metric="service_up").order_by(m.MetricObservation.id).all()
    assert [v.value for v in vals] == [1, 1, 1, 1, 0, 0]
    assert all(v.source_type == "SIMULATED" for v in vals)
    # latency is None (not zero) while the service is down
    lat = db.query(m.MetricObservation).filter_by(simulation_run_id=run.id, metric="http_latency_ms").all()
    assert lat[-1].value is None


def test_resolution_requires_successful_verification(db, clock):
    run, inc = _open(db, clock)
    with pytest.raises(common.DomainError) as e:
        svc.resolve(db, inc, "op", now=clock())
    assert e.value.code in ("invalid_transition", "verification_required")
    svc.apply_repair_action(db, inc, "restart_service", "op", clock.advance(1))
    # Immediately verifying: no post-repair probes yet → must not pass
    v = svc.verify(db, inc, "op", clock())
    assert not v.passed
    with pytest.raises(common.DomainError) as e:
        svc.resolve(db, inc, "op", now=clock())
    assert e.value.code == "verification_required"
    advance_probes(db, clock, 2)
    v = svc.verify(db, inc, "op", clock.advance(0.5))
    assert v.passed
    svc.resolve(db, inc, "op", now=clock.advance(1))
    assert inc.status == "resolved" and inc.verified_at is not None


def test_incorrect_hypothesis_does_not_resolve(db, clock):
    run, inc = _open(db, clock)
    svc.apply_repair_action(db, inc, "bounce_iface", "op", clock.advance(1))
    advance_probes(db, clock, 3)
    v = svc.verify(db, inc, "op", clock())
    assert not v.passed
    assert inc.status == "investigating"  # returned to investigation
    with pytest.raises(common.DomainError):
        svc.resolve(db, inc, "op", now=clock())


def test_unknown_onset_gives_unavailable_detection_latency(db, clock):
    run = simulation.start(db, "nic-down", now=clock())
    inc = run_until_incident(db, run, clock)
    assert inc.fault_onset_at is None
    mt = svc.incident_metrics(inc)
    assert mt["detection_latency_s"] is None
    assert "unknown" in mt["detection_latency_note"].lower()
    agg = svc.aggregate_metrics(db)["by_source"]["SIMULATED"]
    assert agg["detection_latency_s"]["count"] == 0
    assert agg["excluded_unknown_onset"] == 1


def test_reopening_preserves_history(db, clock):
    run, inc = _open(db, clock)
    svc.apply_repair_action(db, inc, "restart_service", "op", clock.advance(1))
    advance_probes(db, clock, 2)
    svc.verify(db, inc, "op", clock())
    svc.resolve(db, inc, "op", now=clock.advance(1))
    n_events, n_ver, n_rep = len(inc.events), len(inc.verifications), len(inc.repairs)
    svc.reopen(db, inc, "Probe flapped again after resolution", "op", clock.advance(10))
    assert inc.status == "investigating" and inc.reopen_count == 1 and inc.resolved_at is None
    assert len(inc.events) > n_events and len(inc.verifications) == n_ver and len(inc.repairs) == n_rep
    reopened = [e for e in inc.events if e.kind == "reopened"][0]
    assert reopened.detail["resolved_at"] is not None  # prior resolution kept in history
    # old passing verification no longer satisfies resolution once reopened (requires a new repair + verify)
    with pytest.raises(common.DomainError):
        svc.resolve(db, inc, "op", now=clock())


def test_simulated_and_real_results_are_separated(db, clock):
    run, inc = _open(db, clock)
    svc.apply_repair_action(db, inc, "restart_service", "op", clock.advance(1))
    advance_probes(db, clock, 2)
    svc.verify(db, inc, "op", clock())
    svc.resolve(db, inc, "op", now=clock.advance(1))
    # a LOCAL_LAB incident with different timings
    real = m.Incident(display_id="INC-9001", title="real", symptom="x", severity="major", status="resolved", source_type="LOCAL_LAB",
                      source_id="livelab:test", fault_onset_at=clock.advance(0), detected_at=clock.advance(100),
                      acknowledged_at=clock.advance(50), verified_at=clock.advance(300), resolved_at=clock.advance(1), origin="local_lab",
                      scenario_key="livelab-svc")
    db.add(real)
    db.flush()
    agg = svc.aggregate_metrics(db)["by_source"]
    assert agg["SIMULATED"]["mttr_s"]["count"] == 1
    assert agg["LOCAL_LAB"]["mttr_s"]["count"] == 1
    assert agg["LOCAL_LAB"]["detection_latency_s"]["median"] == 100.0
    assert agg["SIMULATED"]["detection_latency_s"]["median"] == 3.0
    assert "ALL" not in agg  # no combined aggregate exists


def test_evidence_has_provenance_and_tracks_state(db, clock):
    run, inc = _open(db, clock)
    before = svc.collect_evidence(db, inc, "systemctl_status", "op", clock())
    assert before.source_type == "SIMULATED" and before.source_id.startswith("sim:svc-stopped") and before.collected_at
    assert "inactive (dead)" in before.output and before.interpretation and before.limitations
    svc.apply_repair_action(db, inc, "restart_service", "op", clock.advance(1))
    after = svc.collect_evidence(db, inc, "systemctl_status", "op", clock.advance(1))
    assert "active (running)" in after.output


def test_invalid_transitions_rejected(db, clock):
    run = simulation.start(db, "fs-full", now=clock())
    inc = run_until_incident(db, run, clock)
    with pytest.raises(common.DomainError):
        svc.apply_repair_action(db, inc, "purge_debug_logs", "op", clock())  # must acknowledge + investigate first
    with pytest.raises(common.DomainError):
        svc.start_investigation(db, inc, "op", clock())  # must acknowledge first


@pytest.mark.parametrize("key,fix", [("fs-full", "purge_debug_logs"), ("cpu-contention", "stop_batch_job"), ("nic-down", "reseat_cable")])
def test_each_scenario_recovers_end_to_end(db, clock, key, fix):
    run, inc = _open(db, clock, key)
    svc.apply_repair_action(db, inc, fix, "op", clock.advance(1))
    advance_probes(db, clock, 2)
    assert svc.verify(db, inc, "op", clock()).passed
    svc.resolve(db, inc, "op", now=clock.advance(1))
    assert run.status == "completed"
