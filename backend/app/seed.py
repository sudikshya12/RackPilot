"""Repeatable seed for the modeled North Lab.

All names, serial numbers and addresses are synthetic. Addresses use the RFC 5737 documentation
ranges, serials start with ``SIM-``, and the manufacturer is fictional.

Usage:
    uv run python -m app.seed            # seed an empty database (no-op if already seeded)
    uv run python -m app.seed --reset    # DROP all data and re-seed (asks for confirmation)
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .db import SessionLocal
from .runbooks_data import RUNBOOKS
from .services import common
from .services.acceptance import _latest_run, run_effective

MFR = "Northwind Lab Hardware (fictional)"
SEED_TIME = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)

SERVERS = [
    # display, rack, U, height, model, mgmt ip suffix
    ("lab-srv-01", "NL-R01", 38, 1, "NL-1U-Compute", 21),
    ("lab-srv-02", "NL-R01", 36, 1, "NL-1U-Compute", 22),
    ("lab-srv-03", "NL-R01", 34, 1, "NL-1U-Compute", 23),
    ("lab-srv-04", "NL-R01", 30, 2, "NL-2U-Storage", 24),
    ("lab-srv-05", "NL-R02", 36, 1, "NL-1U-Compute", 25),
]

# Power plan: (device, input) -> (pdu, outlet) ; None = deliberately missing connection
POWER_PLAN = {
    ("lab-srv-01", "PSU1"): ("nl-r01-pdu-a", "A01"), ("lab-srv-01", "PSU2"): ("nl-r01-pdu-b", "B03"),
    ("lab-srv-02", "PSU1"): ("nl-r01-pdu-a", "A02"), ("lab-srv-02", "PSU2"): ("nl-r01-pdu-b", "B02"),
    ("lab-srv-03", "PSU1"): ("nl-r01-pdu-a", "A03"), ("lab-srv-03", "PSU2"): None,  # DEFECT: missing connection
    ("lab-srv-04", "PSU1"): ("nl-r01-pdu-a", "A04"), ("lab-srv-04", "PSU2"): ("nl-r01-pdu-b", "B04"),
    ("lab-srv-05", "PSU1"): ("nl-r02-pdu-a", "A01"), ("lab-srv-05", "PSU2"): ("nl-r02-pdu-b", "B01"),  # DEFECT: shared upstream
    ("lab-sw-01", "PSU1"): ("nl-r01-pdu-a", "A08"), ("lab-sw-01", "PSU2"): ("nl-r01-pdu-b", "B08"),
    ("lab-sw-02", "PSU1"): ("nl-r02-pdu-a", "A08"), ("lab-sw-02", "PSU2"): ("nl-r02-pdu-t", "T01"),  # DEFECT: unknown upstream
}
LOADS = {"NL-1U-Compute": (210.0, 205.0), "NL-2U-Storage": (212.0, 206.0), "NL-TOR-48X": (95.0, 92.0), "NL-MGMT-24T": (28.0, 27.0)}


def _hw_srv06() -> dict:
    return {
        "identity": {"serial_number": "SIM-NL1U-0006", "manufacturer": MFR, "model": "NL-1U-Compute", "bios_version": "1.4.2-sim"},
        "cpu": {"count": 2, "model": "Northwind NX-16 (fictional) 16-core", "cores_total": 32},
        "memory": {"total_gib": 64.0, "basis": "dimm_inventory", "dimms": [
            {"slot": s, "size_gib": 16, "type": "DDR5 RDIMM", "serial": f"SIM-DIMM-{s}-00{i}"} for i, s in enumerate(("A1", "A2", "A3", "A4"), 1)]},
        "storage": [{"name": "nvme0n1", "size_gb": 960, "type": "nvme", "model": "NL-NVME-960 (fictional)"},
                    {"name": "nvme1n1", "size_gb": 960, "type": "nvme", "model": "NL-NVME-960 (fictional)"}],
        "disk_health": [{"name": "nvme0n1", "smart_passed": True, "media_errors": 0, "percentage_used": 0},
                        {"name": "nvme1n1", "smart_passed": True, "media_errors": 0, "percentage_used": 0}],
        "nics": [{"name": "eno1", "role": "mgmt", "mac": "02:00:5e:10:00:26", "speed_mbps": 1000, "link": True},
                 {"name": "eth1", "role": "data", "mac": "02:00:5e:10:01:26", "speed_mbps": 1000, "link": True,
                  "module": "1000BASE-SX SFP (SIM-SFP-1G-0007)"}],
        "connectivity": {"target": "203.0.113.1 (provisioning gateway, modeled)", "gateway_reachable": True, "rtt_ms": 0.3},
        "kernel_errors": {"lines": []},
        "redfish": {"system_health": "OK", "power_state": "On", "mode": "simulated"},
    }


def _hw_srv07() -> dict:
    hw = _hw_srv06()
    hw["identity"]["serial_number"] = "SIM-NL1U-0007"
    hw["memory"] = {"total_gib": 128.0, "basis": "dimm_inventory", "dimms": [
        {"slot": s, "size_gib": 16, "type": "DDR5 RDIMM"} for s in ("A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4")]}
    hw["nics"][1].update(speed_mbps=10000, module="10GBASE-SR SFP+ (SIM-SFP-10G-0011)", mac="02:00:5e:10:01:27")
    hw["nics"][0]["mac"] = "02:00:5e:10:00:27"
    hw["disk_health"] = {"_unsupported": "NVMe SMART log not readable: collector ran without root privileges"}
    hw["kernel_errors"] = {"lines": ["[  12.881] pcieport 0000:00:1c.0: AER: Corrected error received: 0000:03:00.0"]}
    return hw


EXPECTED_STD = {"cpu_count": 2, "cpu_model": "Northwind NX-16", "memory_gib": 128, "storage": [{"count": 2, "size_gb": 960, "type": "nvme"}],
                "nic_count": 2, "data_link_speed_mbps": 10000}

INTAKES = [
    {"display": "INT-0001", "hostname": "lab-srv-06", "asset": "NL-AST-0006", "serial": "SIM-NL1U-0006", "rack": "NL-R02", "u": 20,
     "hw": _hw_srv06},
    {"display": "INT-0002", "hostname": "lab-srv-07", "asset": "NL-AST-0007", "serial": "SIM-NL1U-0007", "rack": "NL-R02", "u": 18,
     "hw": _hw_srv07},
]

PROFILE_CHECKS = [
    {"check_key": "hardware_identity", "required": True},
    {"check_key": "cpu_inventory", "required": True},
    {"check_key": "memory_capacity", "required": True},
    {"check_key": "storage_inventory", "required": True},
    {"check_key": "disk_health", "required": True},
    {"check_key": "nic_inventory", "required": True},
    {"check_key": "link_speed", "required": True},
    {"check_key": "connectivity", "required": True},
    {"check_key": "kernel_errors", "required": True},
    {"check_key": "redfish_health", "required": False},
]

PART_TYPES = [
    # part number, name, category, form, compatible models, (location, qty, threshold)
    ("NL-PSU-800P", "800 W Platinum hot-swap PSU", "psu", "C14 hot-swap", ["NL-1U-Compute", "NL-2U-Storage"], ("Spares cage A / Bin 03", 2, 1)),
    ("NL-PSU-550S", "550 W switch PSU", "psu", "C14 hot-swap", ["NL-TOR-48X", "NL-MGMT-24T"], ("Spares cage A / Bin 04", 1, 1)),
    ("NL-DIMM-16G-D5", "16 GiB DDR5-4800 RDIMM", "dimm", "288-pin RDIMM", ["NL-1U-Compute", "NL-2U-Storage"], ("Spares cage B / ESD drawer 1", 6, 2)),
    ("NL-SFP-10G-SR", "10GBASE-SR SFP+ 850 nm", "transceiver", "SFP+ / LC", ["NL-1U-Compute", "NL-2U-Storage", "NL-TOR-48X"], ("Spares cage B / Optics tray", 3, 4)),
    ("NL-SFP-1G-SX", "1000BASE-SX SFP 850 nm", "transceiver", "SFP / LC", ["NL-MGMT-24T"], ("Spares cage B / Optics tray", 3, 1)),
    ("NL-NVME-960", "960 GB U.2 NVMe SSD", "disk", "U.2 2.5in", ["NL-1U-Compute", "NL-2U-Storage"], ("Spares cage B / Drive shelf", 1, 1)),
]


def _iface(dev: m.Device, name, kind, conn, speed, mac="", desc=""):
    i = m.DeviceInterface(device_id=dev.id, name=name, kind=kind, connector_type=conn, speed_capability_mbps=speed, mac_address=mac, description=desc)
    return i


def seed(db: Session) -> None:
    if db.scalar(select(m.Site).limit(1)):
        print("Database already seeded; use --reset to rebuild.")
        return
    site = m.Site(display_id="SITE-NL", name="North Lab", description="Fictional single-room lab. Modeled lab topology.")
    db.add(site)
    db.flush()
    racks = {}
    for rid, row in (("NL-R01", "Row A"), ("NL-R02", "Row A")):
        racks[rid] = m.Rack(display_id=rid, site_id=site.id, name=f"North Lab {rid}", row=row, u_height=42,
                            description="Modeled 42U rack (front and rear rails).")
        db.add(racks[rid])
    feeds = {
        "FEED-A": m.PowerFeed(display_id="FEED-A", name="Feed A — UPS-A distribution", upstream_source="UPS-A (modeled)", voltage_v=230, capacity_w=3680),
        "FEED-B": m.PowerFeed(display_id="FEED-B", name="Feed B — UPS-B distribution", upstream_source="UPS-B (modeled)", voltage_v=230, capacity_w=3680),
        "FEED-A2": m.PowerFeed(display_id="FEED-A2", name="Feed A2 — UPS-A secondary breaker", upstream_source="UPS-A (modeled)", voltage_v=230, capacity_w=3680),
        "FEED-X": m.PowerFeed(display_id="FEED-X", name="Temporary strip — wall receptacle", upstream_source=None, voltage_v=230, capacity_w=None),
    }
    for f in feeds.values():
        db.add(f)
    db.flush()

    devices: dict[str, m.Device] = {}

    def add_device(display, role, model, rack, u, h, face="front", mgmt=""):
        d = m.Device(display_id=display, hostname=display, role=role, manufacturer=MFR, model=model, rack_id=racks[rack].id if rack else None,
                     position_u=u, u_height=h, face=face, mgmt_address=mgmt, health="healthy", health_source="SIMULATED",
                     health_updated_at=SEED_TIME, origin="seed")
        db.add(d)
        db.flush()
        devices[display] = d
        return d

    # PDUs (0U, rear vertical) — outlets carry their feed
    pdus = {"nl-r01-pdu-a": ("NL-R01", "FEED-A", "A"), "nl-r01-pdu-b": ("NL-R01", "FEED-B", "B"),
            "nl-r02-pdu-a": ("NL-R02", "FEED-A", "A"), "nl-r02-pdu-b": ("NL-R02", "FEED-A2", "B"),
            "nl-r02-pdu-t": ("NL-R02", "FEED-X", "T")}
    outlets: dict[tuple[str, str], m.PduOutlet] = {}
    for name, (rack, feed, letter) in pdus.items():
        d = add_device(name, "pdu", "NL-PDU-8C13" if letter != "T" else "Generic 4-way strip (temporary)", rack, None, 0, "rear")
        d.notes = "Zero-U vertical PDU (modeled)." if letter != "T" else "Temporary power strip. Upstream circuit not documented."
        for n in range(1, (9 if letter != "T" else 5)):
            o = m.PduOutlet(pdu_device_id=d.id, name=f"{letter}{n:02d}", feed_id=feeds[feed].id)
            db.add(o)
            outlets[(name, o.name)] = o
    db.flush()

    # Network gear and patch panel
    sw1 = add_device("lab-sw-01", "switch", "NL-TOR-48X", "NL-R01", 40, 1, mgmt="198.51.100.2")
    sw2 = add_device("lab-sw-02", "switch", "NL-MGMT-24T", "NL-R02", 40, 1, mgmt="198.51.100.3")
    pp = add_device("nl-r01-pp-01", "patch_panel", "NL-PP-12LC", "NL-R01", 42, 1)
    pp.notes = "12-port LC fiber patch panel. Front ports pass through to rear ports (modeled)."
    for n in range(1, 13):
        db.add(_iface(sw1, f"Eth1/{n}", "data", "SFP+", 10000))
        db.add(_iface(sw2, f"Gi1/{n}", "data", "RJ45", 1000))
    db.add(_iface(sw1, "mgmt0", "mgmt", "RJ45", 1000))
    db.add(_iface(sw2, "mgmt0", "mgmt", "RJ45", 1000))
    db.flush()
    for n in range(1, 7):
        f = _iface(pp, f"P{n:02d}-F", "patch_front", "LC", 10000)
        r = _iface(pp, f"P{n:02d}-R", "patch_rear", "LC", 10000)
        db.add_all([f, r])
        db.flush()
        f.pass_through_id, r.pass_through_id = r.id, f.id

    # Assets for racked gear
    asset_n = 0

    def add_asset(serial, atype, model, status, location, device=None, part_type=None, warranty="known_active", display=None):
        nonlocal asset_n
        asset_n += 1
        a = m.Asset(display_id=display or f"NL-AST-{asset_n:04d}", serial_number=serial, asset_type=atype, manufacturer=MFR, model=model,
                    status=status, location=location, installed_in_device_id=device.id if device else None,
                    warranty_status=warranty, part_type_id=part_type.id if part_type else None,
                    warranty_end=datetime(2028, 6, 30, tzinfo=timezone.utc) if warranty == "known_active" else None, origin="seed")
        db.add(a)
        db.flush()
        return a

    # Part types first (PSU assets reference them)
    pts: dict[str, m.PartType] = {}
    for pn, name, cat, form, models, _ in PART_TYPES:
        pt = m.PartType(part_number=pn, name=name, category=cat, connector_or_form=form, description=f"{name} (fictional part)")
        db.add(pt)
        db.flush()
        for model in models:
            db.add(m.PartCompatibility(part_type_id=pt.id, device_model=model))
        pts[pn] = pt
    db.flush()

    for i, (disp, rack, u, h, model, ip) in enumerate(SERVERS, 1):
        d = add_device(disp, "server", model, rack, u, h, mgmt=f"198.51.100.{ip}")
        a = add_asset(f"SIM-{'NL1U' if h == 1 else 'NL2U'}-{i:04d}", "server", model, "active", f"{rack} U{u}", d,
                      warranty="unknown" if disp == "lab-srv-03" else "known_active", display=f"NL-AST-{i:04d}")
        d.asset_id = a.id
        db.add(_iface(d, "eno1", "mgmt", "RJ45", 1000, f"02:00:5e:10:00:{ip}", "Management / provisioning"))
        db.add(_iface(d, "eth1", "data", "SFP+", 10000, f"02:00:5e:10:01:{ip}", "Lab data network"))
    asset_n = 10
    for disp in ("lab-sw-01", "lab-sw-02", "nl-r01-pp-01"):
        d = devices[disp]
        a = add_asset(f"SIM-{d.model}-{asset_n + 1:04d}", "switch" if d.role == "switch" else "patch_panel", d.model, "active",
                      f"{d.rack.display_id} U{d.position_u}", d)
        d.asset_id = a.id
    db.flush()

    # Power inputs (+ tracked PSU component assets for servers)
    for (disp, inp), target in POWER_PLAN.items():
        d = devices[disp]
        load = LOADS[d.model][0 if inp == "PSU1" else 1]
        comp = None
        if d.role == "server":
            nn = disp[-2:]
            letter = "A" if inp == "PSU1" else "B"
            idx = (int(nn) - 1) * 2 + (1 if inp == "PSU1" else 2)
            comp = add_asset(f"SIM-PSU-{nn}{letter}-{idx:04d}", "psu", "NL-PSU-800P", "active", f"{disp} {inp}", d, pts["NL-PSU-800P"],
                             display=f"NL-AST-P{nn}{letter}")
        db.add(m.PowerInput(device_id=d.id, name=inp, outlet_id=outlets[target].id if target else None, rated_w=800 if d.role == "server" else 550,
                            estimated_load_w=load, component_asset_id=comp.id if comp else None))
    db.flush()

    # Cables
    ifc = {(i.device.display_id, i.name): i for i in db.scalars(select(m.DeviceInterface)).all()}

    def cable(label, ctype, a, b, speed, length, status="connected", notes=""):
        db.add(m.CableConnection(label=label, cable_type=ctype, a_interface_id=ifc[a].id, b_interface_id=ifc[b].id,
                                 intended_speed_mbps=speed, length_m=length, status=status, notes=notes, origin="seed"))

    cable("CBL-0107", "om4-lc-lc", ("lab-srv-01", "eth1"), ("lab-sw-01", "Eth1/7"), 10000, 2.0)
    cable("CBL-0102", "om4-lc-lc", ("lab-srv-02", "eth1"), ("lab-sw-01", "Eth1/2"), 10000, 2.0)
    cable(None, "dac-sfp+", ("lab-srv-03", "eth1"), ("lab-sw-01", "Eth1/3"), 10000, 1.0, notes="DEFECT (seeded): no label recorded.")
    cable("CBL-0104", "om4-lc-lc", ("lab-srv-04", "eth1"), ("lab-sw-01", "Eth1/4"), 10000, 3.0)
    cable("CBL-0205", "om4-lc-lc", ("lab-srv-05", "eth1"), ("nl-r01-pp-01", "P01-R"), 10000, 6.0, notes="Cross-rack trunk R02 → R01 patch panel rear.")
    cable("CBL-0105", "om4-lc-lc", ("nl-r01-pp-01", "P01-F"), ("lab-sw-01", "Eth1/5"), 10000, 0.5)
    for n, srv in enumerate(("lab-srv-01", "lab-srv-02", "lab-srv-03", "lab-srv-04", "lab-srv-05"), 1):
        cable(f"CBL-M2{n:02d}", "cat6a", (srv, "eno1"), ("lab-sw-02", f"Gi1/{n}"), 1000, 3.0 if n < 5 else 1.5)
    cable("CBL-0199", "cat6a", ("lab-sw-01", "Eth1/12"), ("lab-sw-02", "Gi1/12"), 1000, 5.0,
          notes="DEFECT (seeded, imported from legacy spreadsheet): copper cable recorded on an SFP+ port.")
    db.flush()

    # Intake assets + records
    profile = m.AcceptanceProfile(key="nl-compute-standard", name="North Lab compute — standard acceptance", version="1.3",
                                  description="Required checks gate provisioning handoff. Optional checks are reported but do not change the disposition.",
                                  checks=PROFILE_CHECKS)
    db.add(profile)
    db.flush()
    for spec in INTAKES:
        a = add_asset(spec["serial"], "server", "NL-1U-Compute", "received", "Receiving bench", display=spec["asset"])
        db.add(m.IntakeRecord(display_id=spec["display"], asset_id=a.id, asset_tag=spec["asset"], serial_number=spec["serial"],
                              hostname=spec["hostname"], expected=dict(EXPECTED_STD), intended_rack_id=racks[spec["rack"]].id,
                              intended_position_u=spec["u"], profile_id=profile.id, source_type="SIMULATED", operator="operator",
                              simulated_hardware=spec["hw"](), simulated_corrections=[], origin="seed"))
    db.flush()

    # Spare stock via ledger
    for pn, name, cat, form, models, (loc, qty, thr) in PART_TYPES:
        s = m.SpareStock(display_id=f"STK-{pn.removeprefix('NL-')}", part_type_id=pts[pn].id, location=loc, reorder_threshold=thr)
        db.add(s)
        db.flush()
        db.add(m.InventoryTransaction(display_id=common.next_display_id(db, "TXN", 5), stock_id=s.id, kind="receive", quantity_delta=qty,
                                      note="Opening balance (seed)", actor="seed", origin="seed", occurred_at=SEED_TIME))

    for rb in RUNBOOKS:
        db.add(m.Runbook(**rb))
    db.add(m.CandidateProfile(
        name="[Candidate Name]", headline="Data Center Operations Technician — interview portfolio",
        summary="[Edit in Settings → Candidate profile. Describe your background in your own words.]",
        links=[{"label": "[GitHub / repository link]", "url": ""}], operator_name="operator"))
    for slug in ("incident-recovery", "server-acceptance", "rack-lifecycle"):
        db.add(m.ProjectNote(slug=slug, candidate_contribution="", lessons_learned=""))
    common.set_setting(db, "livelab_enabled", False)
    # Counters start after seeded display IDs
    for prefix, val in (("INT", 2), ("NL-AST", 100)):
        db.merge(m.DisplayCounter(prefix=prefix, value=val))
    common.audit(db, actor="seed", action="lab.seed", entity_type="site", entity_id=site.id, entity_display=site.display_id,
                 summary="Seeded modeled North Lab topology (synthetic data)", origin="seed", at=SEED_TIME)
    db.commit()
    print("Seeded North Lab: 2 racks, 5 racked servers + 2 intake servers, 2 switches, 1 patch panel, 5 PDUs, 4 feeds.")


def restore_seed_baseline(db: Session) -> None:
    """Re-apply seed values to seed-owned mutable fields. Keeps IDs stable; never touches non-seed rows."""
    for d in db.scalars(select(m.Device).where(m.Device.origin == "seed")).all():
        d.health, d.health_source, d.health_updated_at = "healthy", "SIMULATED", SEED_TIME
    devices = {d.display_id: d for d in db.scalars(select(m.Device)).all()}
    for a in db.scalars(select(m.Asset).where(m.Asset.origin == "seed")).all():
        if a.asset_type == "psu" and a.display_id.startswith("NL-AST-P"):
            nn, letter = a.display_id[-3:-1], a.display_id[-1]
            dev = devices.get(f"lab-srv-{nn}")
            a.status, a.location, a.installed_in_device_id = "active", f"lab-srv-{nn} PSU{1 if letter == 'A' else 2}", dev.id if dev else None
    for pi in db.scalars(select(m.PowerInput)).all():
        dev = db.get(m.Device, pi.device_id)
        if dev.role == "server" and dev.origin == "seed":
            nn = dev.display_id[-2:]
            letter = "A" if pi.name == "PSU1" else "B"
            comp = db.scalar(select(m.Asset).where(m.Asset.display_id == f"NL-AST-P{nn}{letter}"))
            pi.component_asset_id = comp.id if comp else None
    for spec in INTAKES:
        rec = db.scalar(select(m.IntakeRecord).where(m.IntakeRecord.display_id == spec["display"]))
        if rec is None or rec.origin != "seed":
            continue
        rec.simulated_hardware = spec["hw"]()
        rec.simulated_corrections = []
        last = _latest_run(db, rec)
        eff = run_effective(last) if last else None
        rec.status = {"PASS": "accepted", "FAIL": "failed", "MANUAL_REVIEW": "manual_review", None: "awaiting_acceptance"}[eff]
    db.flush()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="Drop ALL data (including imported and local-lab records) and re-seed")
    ap.add_argument("--yes", action="store_true", help="Skip confirmation for --reset")
    args = ap.parse_args()
    from .db import Base, engine
    if args.reset:
        if not args.yes:
            ans = input("This deletes ALL records including imported and local-lab evidence. Type 'reset' to continue: ")
            if ans.strip() != "reset":
                print("Aborted.")
                sys.exit(1)
        Base.metadata.drop_all(engine)
        from alembic import command
        from alembic.config import Config
        from .config import BASE_DIR
        cfg = Config(str(BASE_DIR / "alembic.ini"))
        with engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
        command.upgrade(cfg, "head")
    with SessionLocal() as db:
        seed(db)


if __name__ == "__main__":
    main()
